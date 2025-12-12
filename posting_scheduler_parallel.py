"""
Parallel Posting Scheduler - TEST VERSION

This is a test version that runs multiple posts concurrently.
Uses a SEPARATE state file to avoid interfering with main scheduler.

Usage:
    python posting_scheduler_parallel.py --test-accounts acc1 acc2 acc3 --workers 2
    python posting_scheduler_parallel.py --status
    python posting_scheduler_parallel.py --run --workers 3
"""
import os
import sys

# Set ANDROID_HOME early for Appium
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'
os.environ['ANDROID_SDK_ROOT'] = r'C:\Users\asus\Downloads\android-sdk'

import csv
import json
import time
import glob
import logging
import threading
import traceback
import atexit
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Set
from enum import Enum
from geelark_client import GeelarkClient

# === CONFIGURATION ===
STATE_FILE = "scheduler_state_parallel.json"  # SEPARATE from main scheduler!
LOCK_FILE = "scheduler_parallel.lock"
LIVE_LOG_FILE = "scheduler_parallel_live.log"
BATCH_LOG_FILE = "geelark_parallel_batch.log"

# Default settings
DEFAULT_WORKERS = 3
DEFAULT_POSTS_PER_ACCOUNT = 1
DEFAULT_DELAY_BETWEEN_POSTS = 10
STALE_JOB_TIMEOUT_MINUTES = 5  # Jobs in_progress longer than this are considered stale
CLEANUP_INTERVAL_SECONDS = 60  # How often to check for stale jobs

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# === LOGGING ===
class WorkerLogger:
    """Thread-safe logger with worker ID prefix"""
    def __init__(self, log_file: str):
        self.log_file = log_file
        self.lock = threading.Lock()
        self.worker_id = threading.local()

    def set_worker_id(self, wid: int):
        self.worker_id.id = wid

    def log(self, msg: str):
        wid = getattr(self.worker_id, 'id', 0)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = f"[W{wid}]" if wid > 0 else "[MAIN]"
        line = f"[{ts}] {prefix} {msg}"

        print(line)

        with self.lock:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(line + "\n")
                    f.flush()
            except:
                pass

logger = WorkerLogger(LIVE_LOG_FILE)

# Setup file logging
logging.basicConfig(
    filename=BATCH_LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
file_logger = logging.getLogger("geelark_parallel")


# === LOCK MECHANISM ===
def is_process_running(pid: int) -> bool:
    if sys.platform == 'win32':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

def acquire_lock() -> bool:
    current_pid = os.getpid()

    # Check if MAIN scheduler is running (scheduler.lock)
    if os.path.exists("scheduler.lock"):
        try:
            with open("scheduler.lock", 'r') as f:
                main_lock = json.load(f)
            main_pid = main_lock.get('pid')
            if main_pid and is_process_running(main_pid):
                print(f"[LOCK ERROR] Main scheduler is running (PID {main_pid})")
                print(f"[LOCK ERROR] Stop it first: taskkill //F //PID {main_pid}")
                return False
        except:
            pass

    # Check if another parallel scheduler is running
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                lock_data = json.load(f)
            old_pid = lock_data.get('pid')

            if old_pid and is_process_running(old_pid):
                print(f"[LOCK ERROR] Another parallel scheduler is running (PID {old_pid})")
                return False
            else:
                print(f"[LOCK] Stale lock found, taking over")
        except:
            pass

    lock_data = {
        'pid': current_pid,
        'started': datetime.now().isoformat(),
    }
    with open(LOCK_FILE, 'w') as f:
        json.dump(lock_data, f)

    print(f"[LOCK] Acquired (PID {current_pid})")
    return True

def release_lock():
    current_pid = os.getpid()
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                lock_data = json.load(f)
            if lock_data.get('pid') == current_pid:
                os.remove(LOCK_FILE)
                print(f"[LOCK] Released")
        except:
            pass

atexit.register(release_lock)


# === APPIUM HEALTH ===
def check_appium_health(port: int = 4723) -> bool:
    import urllib.request
    import urllib.error
    try:
        url = f"http://127.0.0.1:{port}/status"
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data.get('value', {}).get('ready', False)
    except:
        return False


# === DATA CLASSES ===
class PostStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class PostJob:
    id: str
    video_path: str
    caption: str
    account: str = ""
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = 3
    last_error: str = ""
    last_attempt: str = ""
    completed_at: str = ""
    source_folder: str = ""
    # Heartbeat tracking for stale job detection
    last_heartbeat: str = ""  # ISO timestamp, updated during execution
    worker_id: int = 0  # Which worker is processing this job (0 = none)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def update_heartbeat(self, worker_id: int = 0):
        """Update heartbeat timestamp"""
        self.last_heartbeat = datetime.now().isoformat()
        if worker_id > 0:
            self.worker_id = worker_id

    def is_stale(self, timeout_minutes: int = STALE_JOB_TIMEOUT_MINUTES) -> bool:
        """Check if job is stale (no heartbeat for too long)"""
        if self.status != PostStatus.IN_PROGRESS.value:
            return False
        if not self.last_heartbeat:
            # No heartbeat at all - use last_attempt as fallback
            if self.last_attempt:
                try:
                    last = datetime.fromisoformat(self.last_attempt)
                    return datetime.now() > last + timedelta(minutes=timeout_minutes)
                except:
                    return True  # Can't parse, assume stale
            return True  # No timestamps at all, assume stale
        try:
            hb_time = datetime.fromisoformat(self.last_heartbeat)
            return datetime.now() > hb_time + timedelta(minutes=timeout_minutes)
        except:
            return True


@dataclass
class AccountState:
    name: str
    posts_today: int = 0
    last_post_date: str = ""
    consecutive_failures: int = 0
    cooldown_until: str = ""
    in_use: bool = False  # NEW: Track if worker is using this account

    def can_post_today(self, max_per_day: int = 1) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        if self.last_post_date != today:
            return True
        return self.posts_today < max_per_day

    def is_on_cooldown(self) -> bool:
        if not self.cooldown_until:
            return False
        try:
            cooldown_end = datetime.fromisoformat(self.cooldown_until)
            return datetime.now() < cooldown_end
        except:
            return False

    def record_post(self, success: bool):
        today = datetime.now().strftime("%Y-%m-%d")
        if self.last_post_date != today:
            self.posts_today = 0
            self.last_post_date = today

        if success:
            self.posts_today += 1
            self.consecutive_failures = 0
            self.cooldown_until = ""
        else:
            self.consecutive_failures += 1
            if self.consecutive_failures >= 2:
                cooldown_minutes = min(10 * self.consecutive_failures, 60)
                self.cooldown_until = (datetime.now() + timedelta(minutes=cooldown_minutes)).isoformat()


# === DUPLICATE PROTECTION ===
def get_already_posted() -> Set[str]:
    """
    Get all video shortcodes that have already been posted.
    Checks BOTH main scheduler CSV logs AND main scheduler state.
    """
    posted = set()

    # 1. Check batch_results_*.csv files (main scheduler logs)
    for filepath in glob.glob("batch_results_*.csv"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'success':
                        shortcode = row.get('shortcode') or list(row.values())[0]
                        if shortcode:
                            posted.add(shortcode)
        except:
            pass

    # 2. Check main scheduler_state.json
    if os.path.exists("scheduler_state.json"):
        try:
            with open("scheduler_state.json", 'r', encoding='utf-8') as f:
                state = json.load(f)
            for job in state.get('jobs', []):
                if job.get('status') == 'success':
                    posted.add(job.get('id', ''))
        except:
            pass

    # 3. Check our own parallel state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            for job in state.get('jobs', []):
                if job.get('status') == 'success':
                    posted.add(job.get('id', ''))
        except:
            pass

    return posted


def get_accounts_already_posted() -> Set[str]:
    """
    Get all account names that have already received a successful post.
    Checks batch_results_*.csv files - the PRIMARY tracking source.

    This is used to ensure each account only gets 1 post per run.
    """
    posted_accounts = set()

    # Check all batch_results_*.csv files
    for filepath in glob.glob("batch_results_*.csv"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'success':
                        account = row.get('phone', '')
                        if account:
                            posted_accounts.add(account)
        except:
            pass

    return posted_accounts


# === PARALLEL SCHEDULER ===
class ParallelScheduler:
    def __init__(self, num_workers: int = DEFAULT_WORKERS):
        self.num_workers = num_workers
        self.jobs: Dict[str, PostJob] = {}
        self.accounts: Dict[str, AccountState] = {}
        self.running = False
        self.executor: Optional[ThreadPoolExecutor] = None

        # Thread-safe locks
        self.state_lock = threading.Lock()
        self.account_lock = threading.Lock()

        # Settings
        self.posts_per_account_per_day = DEFAULT_POSTS_PER_ACCOUNT
        self.delay_between_posts = DEFAULT_DELAY_BETWEEN_POSTS
        self.humanize = True

        self.load_state()

    def load_state(self):
        """Load state from file"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Load jobs
                for job_data in data.get('jobs', []):
                    job = PostJob.from_dict(job_data)
                    self.jobs[job.id] = job

                # Load accounts
                for acc_data in data.get('accounts', []):
                    acc = AccountState(**{k: v for k, v in acc_data.items() if k != 'in_use'})
                    self.accounts[acc.name] = acc

                # Load settings (but NEVER num_workers - that comes from CLI only)
                settings = data.get('settings', {}) or {}
                settings.pop('num_workers', None)  # HARD STRIP - never let this leak back in

                self.posts_per_account_per_day = settings.get('posts_per_account_per_day', DEFAULT_POSTS_PER_ACCOUNT)
                self.delay_between_posts = settings.get('delay_between_posts', DEFAULT_DELAY_BETWEEN_POSTS)
                self.humanize = settings.get('humanize', True)
                # num_workers is NEVER loaded from state - CLI is the single source of truth

                logger.log(f"Loaded state: {len(self.jobs)} jobs, {len(self.accounts)} accounts")
            except Exception as e:
                logger.log(f"Error loading state: {e}")

    def save_state(self):
        """Save state to file (thread-safe)"""
        with self.state_lock:
            data = {
                'jobs': [j.to_dict() for j in self.jobs.values()],
                'accounts': [asdict(a) for a in self.accounts.values()],
                'settings': {
                    'posts_per_account_per_day': self.posts_per_account_per_day,
                    'delay_between_posts': self.delay_between_posts,
                    'humanize': self.humanize,
                    # NOTE: num_workers is intentionally NOT saved - it must come from CLI
                    # This prevents stale values from being loaded on restart
                },
                'last_saved': datetime.now().isoformat(),
            }
            try:
                with open(STATE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.log(f"Error saving state: {e}")

    def cleanup_stale_jobs(self, timeout_minutes: int = STALE_JOB_TIMEOUT_MINUTES) -> int:
        """
        Clean up stale jobs that are stuck in 'in_progress' status.
        Returns the number of jobs cleaned up.

        This prevents jobs from being permanently stuck when workers crash/timeout.
        Similar to stopping phones - stale resources cost money and block progress.
        """
        cleaned = 0
        stale_accounts = set()

        with self.state_lock:
            for job in self.jobs.values():
                if job.is_stale(timeout_minutes):
                    old_status = job.status
                    old_worker = job.worker_id
                    old_account = job.account

                    # Reset job to retrying (or pending if max attempts not reached)
                    if job.attempts < job.max_attempts:
                        job.status = PostStatus.RETRYING.value
                    else:
                        job.status = PostStatus.FAILED.value

                    job.worker_id = 0
                    job.last_heartbeat = ""
                    job.last_error = f"Stale job cleanup (was {old_status} on worker {old_worker})"

                    # Track which accounts need to be released
                    if old_account:
                        stale_accounts.add(old_account)

                    logger.log(f"[CLEANUP] Reset stale job {job.id}: {old_status} -> {job.status} "
                             f"(worker {old_worker}, last heartbeat: {job.last_heartbeat or 'never'})")
                    cleaned += 1

        # Release any accounts that were held by stale jobs
        if stale_accounts:
            with self.account_lock:
                for acc_name in stale_accounts:
                    if acc_name in self.accounts:
                        self.accounts[acc_name].in_use = False
                        logger.log(f"[CLEANUP] Released account {acc_name} from stale job")

        if cleaned > 0:
            self.save_state()
            logger.log(f"[CLEANUP] Cleaned {cleaned} stale jobs")

        return cleaned

    def _cleanup_loop(self):
        """Background thread that periodically cleans up stale jobs"""
        logger.log("[CLEANUP] Stale job cleanup thread started")
        while self.running:
            try:
                time.sleep(CLEANUP_INTERVAL_SECONDS)
                if self.running:
                    self.cleanup_stale_jobs()
            except Exception as e:
                logger.log(f"[CLEANUP] Error in cleanup loop: {e}")
        logger.log("[CLEANUP] Stale job cleanup thread stopped")

    def add_account(self, name: str):
        """Add an account"""
        with self.account_lock:
            if name not in self.accounts:
                self.accounts[name] = AccountState(name=name)
                logger.log(f"Added account: {name}")
                self.save_state()

    def add_accounts_from_file(self, filepath: str) -> int:
        """
        Load accounts from a file (one per line) and add only those that
        haven't already received a successful post.

        This is the ONE-CLICK solution: it automatically checks batch_results_*.csv
        and skips accounts that already posted.

        Returns: number of accounts added
        """
        if not os.path.exists(filepath):
            logger.log(f"Accounts file not found: {filepath}")
            return 0

        # Read all accounts from file
        with open(filepath, 'r', encoding='utf-8') as f:
            all_accounts = [line.strip() for line in f if line.strip()]

        logger.log(f"Loaded {len(all_accounts)} accounts from {filepath}")

        # Get accounts that already have successful posts
        already_posted = get_accounts_already_posted()
        logger.log(f"Found {len(already_posted)} accounts already posted (from batch_results_*.csv)")

        # Filter and add only remaining accounts
        added = 0
        skipped = 0
        with self.account_lock:
            for acc in all_accounts:
                if acc in already_posted:
                    skipped += 1
                    continue
                if acc not in self.accounts:
                    self.accounts[acc] = AccountState(name=acc)
                    added += 1

        logger.log(f"Added {added} accounts, skipped {skipped} already-posted")
        logger.log(f"Total accounts ready to post: {len(self.accounts)}")

        if added > 0:
            self.save_state()

        return added

    def add_video_folder(self, folder_path: str):
        """Add videos from a folder"""
        if not os.path.isdir(folder_path):
            logger.log(f"Folder not found: {folder_path}")
            return 0

        # Find CSV with captions
        csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
        if not csv_files:
            logger.log(f"No CSV found in {folder_path}")
            return 0

        csv_path = csv_files[0]

        # Build video lookup
        videos = {}
        for root, dirs, files in os.walk(folder_path):
            for f in files:
                if f.endswith('.mp4'):
                    shortcode = f.replace('.mp4', '')
                    videos[shortcode] = os.path.join(root, f)

        # Get already posted videos (from main scheduler AND our state)
        already_posted = get_already_posted()
        logger.log(f"Found {len(already_posted)} already-posted videos to skip")

        added = 0
        skipped = 0
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                caption = row.get('Text', '')
                # Support both column names
                video_ref = row.get('Image/Video link 1 (shortcode)', '') or \
                           row.get('Image/Video link 1 (file path or URL(works only for images))', '')

                if not video_ref or not caption:
                    continue

                shortcode = video_ref.strip()
                video_path = videos.get(shortcode)

                if video_path and os.path.exists(video_path):
                    # Skip if already posted (main scheduler or us)
                    if shortcode in already_posted:
                        skipped += 1
                        continue
                    # Skip if already in our jobs queue
                    if shortcode not in self.jobs:
                        job = PostJob(
                            id=shortcode,
                            video_path=video_path,
                            caption=caption,
                            source_folder=folder_path
                        )
                        self.jobs[shortcode] = job
                        added += 1

        logger.log(f"Added {added} videos from {os.path.basename(folder_path)} (skipped {skipped} already-posted)")
        self.save_state()
        return added

    def get_next_job_and_account(self, worker_id: int) -> Optional[tuple]:
        """
        Thread-safe: Get next job AND reserve an account atomically.
        Returns (job, account_name) or None if nothing available.
        """
        with self.account_lock:
            # Find available accounts (not in use, can post, not on cooldown)
            available = [
                acc for acc in self.accounts.values()
                if not acc.in_use
                and acc.can_post_today(self.posts_per_account_per_day)
                and not acc.is_on_cooldown()
            ]

            if not available:
                return None

            # Find pending job
            for job in self.jobs.values():
                if job.status == PostStatus.PENDING.value:
                    # Reserve account
                    account = available[0]
                    account.in_use = True
                    job.account = account.name
                    job.status = PostStatus.IN_PROGRESS.value
                    logger.log(f"Worker {worker_id} reserved {account.name} for job {job.id}")
                    self.save_state()
                    return (job, account.name)

            # Check retrying jobs
            for job in self.jobs.values():
                if job.status == PostStatus.RETRYING.value:
                    if job.last_attempt:
                        last = datetime.fromisoformat(job.last_attempt)
                        if datetime.now() < last + timedelta(minutes=5):
                            continue

                    account = available[0]
                    account.in_use = True
                    job.account = account.name
                    job.status = PostStatus.IN_PROGRESS.value
                    logger.log(f"Worker {worker_id} reserved {account.name} for retry job {job.id}")
                    self.save_state()
                    return (job, account.name)

        return None

    def release_account(self, account_name: str):
        """Release account after worker is done"""
        with self.account_lock:
            if account_name in self.accounts:
                self.accounts[account_name].in_use = False

    def execute_job(self, job: PostJob, worker_id: int) -> bool:
        """Execute a posting job"""
        import random
        from post_reel_smart import SmartInstagramPoster

        logger.set_worker_id(worker_id)
        logger.log(f"Starting job {job.id} on {job.account}")

        job.attempts += 1
        job.last_attempt = datetime.now().isoformat()

        # HEARTBEAT: Track that this worker is actively processing this job
        # This allows stale job cleanup to detect crashed workers
        job.update_heartbeat(worker_id)
        self.save_state()  # Persist heartbeat immediately

        poster = None
        success = False

        # CRITICAL: Assign unique systemPort per worker to avoid Appium conflicts
        # Default is 8200, worker 1 gets 8201, worker 2 gets 8202, etc.
        system_port = 8200 + worker_id
        logger.log(f"Using systemPort {system_port} for worker {worker_id}")

        try:
            poster = SmartInstagramPoster(job.account, system_port=system_port)

            # Update heartbeat after connection attempt
            job.update_heartbeat(worker_id)
            poster.connect()

            # Update heartbeat before posting
            job.update_heartbeat(worker_id)
            success = poster.post(job.video_path, job.caption, humanize=self.humanize)

            if success:
                job.status = PostStatus.SUCCESS.value
                job.completed_at = datetime.now().isoformat()
                job.last_error = ""
                job.worker_id = 0  # Clear worker since job is done
                job.last_heartbeat = ""  # Clear heartbeat since job is done

                with self.account_lock:
                    if job.account in self.accounts:
                        self.accounts[job.account].record_post(True)

                logger.log(f"SUCCESS: {job.id} posted to {job.account}")
            else:
                raise Exception("Post returned False")

        except Exception as e:
            error_msg = str(e)
            job.last_error = error_msg
            job.worker_id = 0  # Clear worker since job is no longer being processed
            job.last_heartbeat = ""  # Clear heartbeat
            logger.log(f"FAILED: {job.id} - {error_msg[:100]}")

            # TASK 32: Appium errors = single failure, no tight retry loops
            # The job will be marked failed and can be retried in a future run
            appium_error_patterns = [
                "appium" in error_msg.lower(),
                "HTTPConnectionPool" in error_msg,
                "instrumentation" in error_msg.lower(),
                "could not proxy command" in error_msg.lower(),
                "invalid session id" in error_msg.lower(),
                "socket hang up" in error_msg.lower(),
                "AdbReadinessError" in error_msg,
                "GloginReadinessError" in error_msg,
            ]
            if any(appium_error_patterns):
                # Single health check with bounded timeout (5s) - no retry loop
                if not check_appium_health():
                    logger.log(f"[WARNING] Appium may be down. Job failed - will not retry immediately.")
                    logger.log(f"[WARNING] Consider restarting Appium before next run.")

            with self.account_lock:
                if job.account in self.accounts:
                    self.accounts[job.account].record_post(False)

            if job.attempts < job.max_attempts:
                job.status = PostStatus.RETRYING.value
            else:
                job.status = PostStatus.FAILED.value

        finally:
            if poster:
                try:
                    poster.cleanup()
                except:
                    pass

            self.release_account(job.account)
            self.save_state()

        return success

    def worker_loop(self, worker_id: int):
        """Worker thread main loop"""
        logger.set_worker_id(worker_id)
        logger.log(f"Worker {worker_id} started")

        while self.running:
            try:
                # Check Appium health
                if not check_appium_health():
                    logger.log("Appium not healthy, waiting...")
                    time.sleep(10)
                    continue

                # Get next job
                result = self.get_next_job_and_account(worker_id)

                if result:
                    job, account = result
                    # Startup jitter: random delay (0-3s) to prevent simultaneous Appium connections
                    # This helps avoid 'instrumentation process cannot be initialized' errors
                    import random
                    jitter = random.uniform(0, 3)
                    logger.log(f"Jitter delay: {jitter:.1f}s before connecting")
                    time.sleep(jitter)
                    self.execute_job(job, worker_id)

                    # Delay before next
                    if self.running:
                        time.sleep(self.delay_between_posts)
                else:
                    # No work available
                    time.sleep(5)

            except Exception as e:
                logger.log(f"Worker error: {e}")
                time.sleep(10)

        logger.log(f"Worker {worker_id} stopped")

    def start(self):
        """Start the parallel scheduler"""
        if self.running:
            return

        # IMPORTANT: num_workers is ALWAYS from CLI, never loaded from state file
        logger.log(f"Starting parallel scheduler with {self.num_workers} workers (from CLI argument)")

        # TASK 32: Deprecation warning for multi-worker mode sharing one Appium
        if self.num_workers > 1:
            logger.log("[DEPRECATION WARNING] Multi-worker mode with shared Appium is deprecated!")
            logger.log("[DEPRECATION WARNING] Consider using posting_lane.py with separate Appium instances per lane.")
            logger.log("[DEPRECATION WARNING] See lane_config.py for multi-lane setup.")

        # CRITICAL: Clean up stale jobs from previous crashed runs BEFORE starting
        # This is like stopping phones - stale resources cost money and block progress
        logger.log("[STARTUP] Checking for stale jobs from previous runs...")
        cleaned = self.cleanup_stale_jobs()
        if cleaned > 0:
            logger.log(f"[STARTUP] Cleaned {cleaned} stale jobs from previous run")
        else:
            logger.log("[STARTUP] No stale jobs found")

        self.running = True

        # Start cleanup thread for periodic stale job detection
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

        # Start worker threads
        self.executor = ThreadPoolExecutor(max_workers=self.num_workers)
        self.futures = []

        for i in range(1, self.num_workers + 1):
            system_port = 8200 + i
            logger.log(f"[STARTUP] Creating Worker {i} with systemPort {system_port}")
            future = self.executor.submit(self.worker_loop, i)
            self.futures.append(future)
            # Stagger worker startup by 2s to avoid simultaneous Appium connections
            if i < self.num_workers:
                time.sleep(2)

        logger.log(f"All workers started (total: {self.num_workers})")

    def stop(self):
        """Stop the scheduler"""
        logger.log("Stopping scheduler...")
        self.running = False

        if self.executor:
            self.executor.shutdown(wait=True, cancel_futures=False)

        # Close any running phones
        try:
            client = GeelarkClient()
            for page in range(1, 5):
                result = client.list_phones(page=page, page_size=100)
                for phone in result.get('items', []):
                    if phone.get('status') == 1:
                        serial = phone.get('serialName', '')
                        if serial in self.accounts:
                            client.stop_phone(phone['id'])
                            logger.log(f"Stopped phone: {serial}")
                if len(result.get('items', [])) < 100:
                    break
        except:
            pass

        logger.log("Scheduler stopped")

    def get_stats(self) -> dict:
        """Get current statistics"""
        counts = {'pending': 0, 'in_progress': 0, 'success': 0, 'failed': 0, 'retrying': 0}
        for job in self.jobs.values():
            status = job.status
            counts[status] = counts.get(status, 0) + 1

        available_accounts = [
            a.name for a in self.accounts.values()
            if not a.in_use and a.can_post_today(self.posts_per_account_per_day) and not a.is_on_cooldown()
        ]

        in_use_accounts = [a.name for a in self.accounts.values() if a.in_use]

        return {
            'jobs': counts,
            'total_jobs': len(self.jobs),
            'accounts': len(self.accounts),
            'available_accounts': available_accounts,
            'in_use_accounts': in_use_accounts,
            'workers': self.num_workers,
            'appium_healthy': check_appium_health(),
        }

    def print_status(self):
        """Print current status"""
        stats = self.get_stats()

        print(f"\n=== Parallel Scheduler Status ===")
        print(f"Workers: {stats['workers']}")
        print(f"Jobs: {stats['total_jobs']} total")
        for status, count in stats['jobs'].items():
            print(f"  - {status}: {count}")
        print(f"Accounts: {stats['accounts']}")
        print(f"  Available: {len(stats['available_accounts'])}")
        print(f"  In use: {stats['in_use_accounts']}")
        print(f"Appium: {'HEALTHY' if stats['appium_healthy'] else 'DOWN'}")


def main():
    parser = argparse.ArgumentParser(description='''
Parallel Posting Scheduler

ONE-CLICK USAGE:
  python posting_scheduler_parallel.py --accounts-file accounts_list.txt --add-folder chunk_01c --workers 3 --run

This will:
  1. Load accounts from file
  2. Automatically skip accounts that already posted (checks batch_results_*.csv)
  3. Load videos from folder
  4. Run with specified workers until all accounts have posted
''', formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('--status', action='store_true', help='Show status')
    parser.add_argument('--run', action='store_true', help='Run the scheduler')
    parser.add_argument('--workers', type=int, default=DEFAULT_WORKERS, help='Number of workers (default: 3)')
    parser.add_argument('--accounts-file', type=str, help='Load accounts from file (auto-skips already-posted)')
    parser.add_argument('--add-accounts', nargs='+', help='Add specific accounts manually')
    parser.add_argument('--add-folder', type=str, help='Add video folder')
    parser.add_argument('--fresh-state', action='store_true', help='Clear scheduler state and start fresh')

    args = parser.parse_args()

    # Fresh state option - clears the parallel scheduler state
    if args.fresh_state:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
            print(f"Cleared {STATE_FILE}")

    scheduler = ParallelScheduler(num_workers=args.workers)

    # Load accounts from file (auto-filters already-posted)
    if args.accounts_file:
        scheduler.add_accounts_from_file(args.accounts_file)

    # Manual account addition
    if args.add_accounts:
        for acc in args.add_accounts:
            scheduler.add_account(acc)

    if args.add_folder:
        scheduler.add_video_folder(args.add_folder)

    if args.status:
        scheduler.print_status()
        return

    if args.run:
        if not acquire_lock():
            sys.exit(1)

        try:
            scheduler.start()

            # Wait for Ctrl+C
            print("\nScheduler running. Press Ctrl+C to stop.\n")
            while scheduler.running:
                time.sleep(1)

        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            scheduler.stop()
            release_lock()
    else:
        scheduler.print_status()


if __name__ == "__main__":
    main()
