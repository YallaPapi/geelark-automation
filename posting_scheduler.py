"""
Posting Scheduler - Core queue/retry/state management system.

Features:
- Load videos from multiple folders
- Track posting state (posted, pending, failed, retrying)
- Auto-retry failed posts with configurable attempts/delay
- Schedule: one post per account per day
- State persistence to survive restarts
- Per-phase timeout protection
- Proper logging with phase info
"""
import os
import sys
import csv
import json
import time
import glob
import logging
import threading
import traceback
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Callable, Set
from enum import Enum
from geelark_client import GeelarkClient

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Live log file for dashboard streaming
LIVE_LOG_FILE = "scheduler_live.log"

class TeeWriter:
    """Write to both stdout and a log file with timestamps"""
    def __init__(self, original_stdout, log_file):
        self.original = original_stdout
        self.log_file = log_file
        self.line_buffer = ""

    def write(self, text):
        self.original.write(text)
        self.original.flush()
        # Write to log file with timestamp for each line
        self.line_buffer += text
        while '\n' in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split('\n', 1)
            if line.strip():
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    with open(self.log_file, 'a', encoding='utf-8') as f:
                        f.write(f"[{ts}] {line}\n")
                        f.flush()
                except:
                    pass

    def flush(self):
        self.original.flush()

# Install the tee writer to capture all print output
sys.stdout = TeeWriter(sys.stdout, LIVE_LOG_FILE)

# Setup proper logging
logging.basicConfig(
    filename="geelark_batch.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("geelark")


class PostStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class PostJob:
    """A single post job"""
    id: str  # unique id: shortcode
    video_path: str
    caption: str
    account: str = ""  # assigned account
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = 3
    last_error: str = ""
    last_attempt: str = ""
    completed_at: str = ""
    source_folder: str = ""
    error_type: str = ""  # suspended, captcha, action_blocked, etc.
    screenshot_path: str = ""  # path to error screenshot

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


def get_already_posted_from_csv() -> Set[str]:
    """Load all successfully posted shortcodes from batch_results_*.csv files AND scheduler_state.json.

    Returns a set of shortcodes that have already been posted successfully.
    This prevents duplicate posts even across scheduler restarts.
    """
    posted = set()

    # 1. Read from batch_results CSV files
    for filepath in glob.glob("batch_results_*.csv"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'success':
                        posted.add(row.get('shortcode'))
        except Exception as e:
            logger.warning(f"Could not read {filepath}: {e}")

    # 2. Also read from scheduler_state.json (catches successes before CSV write was added)
    state_file = "scheduler_state.json"
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for job in data.get('jobs', []):
                if job.get('status') == 'success':
                    posted.add(job.get('id'))
        except Exception as e:
            logger.warning(f"Could not read {state_file}: {e}")

    return posted


def log_and_mark_failed(account: str, shortcode: str, phase: str, exc: Exception):
    """Log failure with full context and stack trace."""
    logger.exception(
        f"Post failed: account={account}, shortcode={shortcode}, phase={phase}",
        extra={"account": account, "shortcode": shortcode, "phase": phase}
    )
    return {
        'phase': phase,
        'error_type': type(exc).__name__,
        'error_msg': str(exc)[:200]
    }


def write_result_to_csv(shortcode: str, account: str, status: str, error: str = ""):
    """Write a single result to batch_results CSV file.

    This ensures duplicate protection works even if the scheduler crashes,
    since get_already_posted_from_csv() reads from these files.
    """
    timestamp = datetime.now().isoformat()
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"batch_results_{date_str}.csv"

    # Check if file exists to determine if we need headers
    file_exists = os.path.exists(filename)

    try:
        with open(filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['shortcode', 'phone', 'status', 'error', 'timestamp'])
            writer.writerow([shortcode, account, status, error, timestamp])
        logger.info(f"write_result_to_csv: {shortcode} -> {filename}")
    except Exception as e:
        logger.error(f"write_result_to_csv failed: {e}")


def close_all_running_phones(account_names: Set[str] = None) -> int:
    """Close ALL running phones, or only those matching account_names if provided.

    This is CRITICAL - must be called at script start and end to prevent
    wasting cloud phone minutes on phones left running.

    Args:
        account_names: Optional set of account names to filter. If None, closes ALL running phones.

    Returns:
        Number of phones stopped
    """
    try:
        client = GeelarkClient()
        result = client.list_phones(page_size=100)
        phones = result.get('items', [])

        # Find running phones (status 1 = running)
        running = [p for p in phones if p.get('status') == 1]

        if not running:
            logger.info("close_all_running_phones: No phones currently running")
            return 0

        # Filter by account names if provided
        if account_names:
            to_stop = [p for p in running if p.get('serialName') in account_names]
        else:
            to_stop = running  # Stop ALL running phones

        stopped = 0
        for phone in to_stop:
            phone_id = phone['id']
            name = phone.get('serialName', phone_id)
            try:
                client.stop_phone(phone_id)
                print(f"  [CLEANUP] Stopped phone: {name}")
                logger.info(f"close_all_running_phones: Stopped {name}")
                stopped += 1
            except Exception as e:
                print(f"  [CLEANUP] Failed to stop {name}: {e}")
                logger.warning(f"close_all_running_phones: Failed to stop {name}: {e}")

        if stopped > 0:
            print(f"[CLEANUP] Stopped {stopped} running phone(s)")

        return stopped

    except Exception as e:
        logger.error(f"close_all_running_phones failed: {e}")
        print(f"[CLEANUP ERROR] {e}")
        return 0


@dataclass
class AccountState:
    """Track posting state for an account"""
    name: str
    last_post_date: str = ""  # YYYY-MM-DD
    posts_today: int = 0
    total_posts: int = 0
    total_failures: int = 0

    def can_post_today(self, max_per_day: int = 1) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        if self.last_post_date != today:
            return True
        return self.posts_today < max_per_day

    def record_post(self, success: bool):
        today = datetime.now().strftime("%Y-%m-%d")
        if self.last_post_date != today:
            self.posts_today = 0
        self.last_post_date = today
        # Only count successful posts against daily limit
        if success:
            self.posts_today += 1
            self.total_posts += 1
        else:
            self.total_failures += 1


class PostingScheduler:
    """Main scheduler that manages the posting queue"""

    def __init__(self, state_file: str = "scheduler_state.json"):
        self.state_file = state_file
        self.jobs: Dict[str, PostJob] = {}  # id -> PostJob
        self.accounts: Dict[str, AccountState] = {}  # name -> AccountState
        self.video_folders: List[str] = []

        # Settings
        self.max_retries = 3
        self.retry_delay_minutes = 0.25  # 15 seconds
        self.posts_per_account_per_day = 1
        self.humanize = True
        self.delay_between_posts = 30  # seconds
        self.test_retry_mode = False  # If True, first attempt always fails

        # Runtime
        self.running = False
        self.paused = False
        self.worker_thread: Optional[threading.Thread] = None
        self.on_status_update: Optional[Callable] = None  # callback for GUI
        self.on_job_complete: Optional[Callable] = None

        # Load saved state
        self.load_state()

    def load_state(self):
        """Load state from disk"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Load jobs
                for job_data in data.get('jobs', []):
                    job = PostJob.from_dict(job_data)
                    self.jobs[job.id] = job

                # Load accounts
                for acc_data in data.get('accounts', []):
                    acc = AccountState(**acc_data)
                    self.accounts[acc.name] = acc

                # Load settings
                settings = data.get('settings', {})
                self.max_retries = settings.get('max_retries', 3)
                self.retry_delay_minutes = settings.get('retry_delay_minutes', 5)
                self.posts_per_account_per_day = settings.get('posts_per_account_per_day', 1)
                self.humanize = settings.get('humanize', True)
                self.delay_between_posts = settings.get('delay_between_posts', 30)
                self.video_folders = settings.get('video_folders', [])

                self._log(f"Loaded state: {len(self.jobs)} jobs, {len(self.accounts)} accounts")
            except Exception as e:
                self._log(f"Error loading state: {e}")

    def save_state(self):
        """Save state to disk"""
        data = {
            'jobs': [job.to_dict() for job in self.jobs.values()],
            'accounts': [asdict(acc) for acc in self.accounts.values()],
            'settings': {
                'max_retries': self.max_retries,
                'retry_delay_minutes': self.retry_delay_minutes,
                'posts_per_account_per_day': self.posts_per_account_per_day,
                'humanize': self.humanize,
                'delay_between_posts': self.delay_between_posts,
                'video_folders': self.video_folders,
            },
            'saved_at': datetime.now().isoformat()
        }

        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _log(self, message: str):
        """Log message and notify GUI"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        if self.on_status_update:
            self.on_status_update(full_msg)

    def add_video_folder(self, folder_path: str) -> int:
        """Add a video folder and load its posts"""
        if not os.path.isdir(folder_path):
            self._log(f"Folder not found: {folder_path}")
            return 0

        if folder_path not in self.video_folders:
            self.video_folders.append(folder_path)

        # Find CSV file
        csv_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
        if not csv_files:
            self._log(f"No CSV file in {folder_path}")
            return 0

        csv_path = os.path.join(folder_path, csv_files[0])

        # Load already-posted shortcodes from CSV logs (bulletproof duplicate protection)
        already_posted = get_already_posted_from_csv()
        if already_posted:
            self._log(f"Found {len(already_posted)} already-posted shortcodes in CSV logs")

        # Build video map from subfolders
        videos = {}
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            if os.path.isdir(item_path):
                for f in os.listdir(item_path):
                    if f.endswith('.mp4'):
                        shortcode = f.replace('.mp4', '')
                        videos[shortcode] = os.path.join(item_path, f)

        # Load from CSV
        added = 0
        skipped_duplicate = 0
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames or []

            # Find video column
            video_col = None
            for col in columns:
                if 'Video' in col or 'Image' in col or col == 'Shortcode':
                    video_col = col
                    break

            if not video_col:
                self._log(f"No video column in CSV")
                return 0

            for row in reader:
                caption = row.get('Text', '').strip()
                video_ref = row.get(video_col, '').strip()

                if not video_ref or not caption:
                    continue

                # Find video path
                video_path = None
                shortcode = video_ref

                if video_ref in videos:
                    video_path = videos[video_ref]
                elif os.path.exists(video_ref):
                    video_path = video_ref
                    shortcode = os.path.basename(video_ref).replace('.mp4', '')

                if video_path and os.path.exists(video_path):
                    # Skip if already posted (from CSV logs)
                    if shortcode in already_posted:
                        skipped_duplicate += 1
                        continue
                    # Skip if already in jobs queue
                    if shortcode in self.jobs:
                        continue

                    job = PostJob(
                        id=shortcode,
                        video_path=video_path,
                        caption=caption,
                        source_folder=folder_path
                    )
                    self.jobs[shortcode] = job
                    added += 1

        self._log(f"Added {added} videos from {os.path.basename(folder_path)} (skipped {skipped_duplicate} already-posted)")
        logger.info(f"add_video_folder: added={added}, skipped_duplicate={skipped_duplicate}, folder={folder_path}")
        self.save_state()
        return added

    def add_account(self, name: str):
        """Add an account to post to"""
        if name not in self.accounts:
            self.accounts[name] = AccountState(name=name)
            self._log(f"Added account: {name}")
            self.save_state()

    def remove_account(self, name: str):
        """Remove an account"""
        if name in self.accounts:
            del self.accounts[name]
            self.save_state()

    def get_next_job(self) -> Optional[PostJob]:
        """Get next job that's ready to post"""
        # Find accounts that can post today
        available_accounts = [
            acc for acc in self.accounts.values()
            if acc.can_post_today(self.posts_per_account_per_day)
        ]

        if not available_accounts:
            return None

        available_names = [a.name for a in available_accounts]

        # Find pending jobs first (priority)
        for job in self.jobs.values():
            if job.status == PostStatus.PENDING.value:
                # Assign to first available account
                job.account = available_accounts[0].name
                return job

        # Then check retrying jobs
        for job in self.jobs.values():
            if job.status == PostStatus.RETRYING.value:
                # Check if retry delay has passed
                if job.last_attempt:
                    last = datetime.fromisoformat(job.last_attempt)
                    retry_after = last + timedelta(minutes=self.retry_delay_minutes)
                    if datetime.now() < retry_after:
                        continue  # Not ready yet

                # Reassign to any available account (original may be at limit)
                if job.account in available_names:
                    return job
                elif available_accounts:
                    # Original account unavailable, use another
                    job.account = available_accounts[0].name
                    return job

        return None

    def get_retry_jobs(self) -> List[PostJob]:
        """Get jobs that are waiting to retry"""
        return [j for j in self.jobs.values() if j.status == PostStatus.RETRYING.value]

    def get_failed_jobs(self) -> List[PostJob]:
        """Get permanently failed jobs"""
        return [j for j in self.jobs.values() if j.status == PostStatus.FAILED.value]

    def get_pending_jobs(self) -> List[PostJob]:
        """Get pending jobs"""
        return [j for j in self.jobs.values() if j.status == PostStatus.PENDING.value]

    def get_success_jobs(self) -> List[PostJob]:
        """Get successful jobs"""
        return [j for j in self.jobs.values() if j.status == PostStatus.SUCCESS.value]

    def execute_job(self, job: PostJob) -> bool:
        """Execute a single posting job with per-phase timeouts and logging"""
        from post_reel_smart import SmartInstagramPoster

        job.status = PostStatus.IN_PROGRESS.value
        job.attempts += 1
        job.last_attempt = datetime.now().isoformat()
        self.save_state()

        self._log(f"Posting {job.id} to {job.account} (attempt {job.attempts}/{job.max_attempts})")
        logger.info(f"execute_job START: job={job.id}, account={job.account}, attempt={job.attempts}")

        phase = "init"
        start_time = time.time()
        poster = None

        try:
            # TEST MODE: Force failure on first attempt
            if self.test_retry_mode and job.attempts == 1:
                self._log(f"[TEST MODE] Simulating failure on first attempt")
                raise Exception("TEST MODE: Simulated failure for retry testing")

            # Phase 1: Connect (timeout: 90s)
            phase = "connect"
            phase_start = time.time()
            poster = SmartInstagramPoster(job.account)
            poster.connect()
            logger.info(f"phase={phase} completed in {time.time()-phase_start:.1f}s")

            # Check overall timeout (120s for the whole job)
            if time.time() - start_time > 120:
                raise TimeoutError(f"Job exceeded total timeout after {phase}")

            # Phase 2: Post to Instagram (timeout handled inside post_reel_smart)
            phase = "instagram_post"
            phase_start = time.time()
            success = poster.post(job.video_path, job.caption, humanize=self.humanize)
            logger.info(f"phase={phase} completed in {time.time()-phase_start:.1f}s, success={success}")

            # Phase 3: Cleanup (handled in finally block)
            phase = "cleanup"

            total_time = time.time() - start_time
            if success:
                job.status = PostStatus.SUCCESS.value
                job.completed_at = datetime.now().isoformat()
                job.last_error = ""
                self.accounts[job.account].record_post(True)
                self._log(f"[OK] {job.id} posted successfully ({total_time:.1f}s)")
                logger.info(f"execute_job SUCCESS: job={job.id}, total_time={total_time:.1f}s")

                # Write to CSV for duplicate protection across restarts
                write_result_to_csv(job.id, job.account, "success")

                if self.on_job_complete:
                    self.on_job_complete(job, True)

                self.save_state()
                return True
            else:
                raise Exception("Post returned False")

        except Exception as e:
            error_msg = str(e)
            error_type_name = type(e).__name__
            job.last_error = f"[{phase}] {error_type_name}: {error_msg}"
            self._log(f"[FAIL] {job.id} at phase={phase}: {error_type_name}: {error_msg}")

            # Log with full stack trace
            log_and_mark_failed(job.account, job.id, phase, e)

            # Capture error details from poster if available
            if poster:
                if poster.last_error_type:
                    job.error_type = poster.last_error_type
                    self._log(f"[ERROR TYPE] {poster.last_error_type}: {poster.last_error_message}")
                if poster.last_screenshot_path:
                    job.screenshot_path = poster.last_screenshot_path
                    self._log(f"[SCREENSHOT] {poster.last_screenshot_path}")
                # Cleanup is handled in finally block

            # Decide: retry or permanent fail
            # Don't retry account-level errors (suspended, captcha, logged_out)
            non_retryable_errors = ['suspended', 'captcha', 'logged_out', 'action_blocked']
            if job.error_type in non_retryable_errors:
                job.status = PostStatus.FAILED.value
                self._log(f"[FAILED] {job.id} - non-retryable error: {job.error_type}")
            elif job.attempts >= job.max_attempts:
                job.status = PostStatus.FAILED.value
                self._log(f"[FAILED] {job.id} exhausted all retries")
            else:
                job.status = PostStatus.RETRYING.value
                self._log(f"[RETRY] {job.id} will retry in {self.retry_delay_minutes} min")

            self.accounts[job.account].record_post(False)

            if self.on_job_complete:
                self.on_job_complete(job, False)

            self.save_state()
            return False

        finally:
            # CRITICAL: ALWAYS ensure the phone is stopped after each job
            # This runs regardless of success, failure, or exception
            try:
                if poster:
                    poster.cleanup()
            except Exception as cleanup_err:
                logger.warning(f"Cleanup error: {cleanup_err}")

            # Double-check: explicitly stop this account's phone via API
            try:
                close_all_running_phones({job.account})
            except Exception as stop_err:
                logger.warning(f"Phone stop error for {job.account}: {stop_err}")

    def retry_failed_job(self, job_id: str):
        """Manually retry a failed job"""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            if job.status == PostStatus.FAILED.value:
                job.status = PostStatus.RETRYING.value
                job.attempts = 0  # Reset attempts
                self._log(f"Reset {job_id} for retry")
                self.save_state()

    def retry_all_failed(self):
        """Reset all failed jobs for retry"""
        count = 0
        for job in self.jobs.values():
            if job.status == PostStatus.FAILED.value:
                job.status = PostStatus.RETRYING.value
                job.attempts = 0
                count += 1
        if count:
            self._log(f"Reset {count} failed jobs for retry")
            self.save_state()

    def _worker_loop(self):
        """Main worker loop"""
        self._log("Worker started")

        while self.running:
            if self.paused:
                time.sleep(1)
                continue

            job = self.get_next_job()

            if job:
                self.execute_job(job)

                # Delay before next post
                if self.running and not self.paused:
                    self._log(f"Waiting {self.delay_between_posts}s before next post...")
                    time.sleep(self.delay_between_posts)
            else:
                # No jobs ready, check for retry jobs
                retry_jobs = self.get_retry_jobs()
                if retry_jobs:
                    # Find next retry time
                    next_retry = None
                    for rj in retry_jobs:
                        if rj.last_attempt:
                            retry_at = datetime.fromisoformat(rj.last_attempt) + timedelta(minutes=self.retry_delay_minutes)
                            if next_retry is None or retry_at < next_retry:
                                next_retry = retry_at

                    if next_retry:
                        wait_secs = (next_retry - datetime.now()).total_seconds()
                        if wait_secs > 0:
                            self._log(f"Next retry in {int(wait_secs)}s")

                # Wait before checking again
                time.sleep(5)

        self._log("Worker stopped")

    def start(self):
        """Start the scheduler"""
        if self.running:
            return

        # CRITICAL: Close any running phones BEFORE starting
        # This prevents wasting minutes from previous crashed/interrupted runs
        self._log("[STARTUP] Checking for orphaned running phones...")
        account_names = set(self.accounts.keys()) if self.accounts else None
        stopped = close_all_running_phones(account_names)
        if stopped:
            self._log(f"[STARTUP] Closed {stopped} orphaned phone(s)")

        self.running = True
        self.paused = False
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        self._log("Scheduler started")

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)

        # CRITICAL: Close ALL running phones when stopping
        # This ensures no phones are left running after script ends
        self._log("[SHUTDOWN] Closing all managed phones...")
        account_names = set(self.accounts.keys()) if self.accounts else None
        stopped = close_all_running_phones(account_names)
        if stopped:
            self._log(f"[SHUTDOWN] Closed {stopped} phone(s)")

        self._log("Scheduler stopped")
        self.save_state()

    def pause(self):
        """Pause the scheduler"""
        self.paused = True
        self._log("Scheduler paused")

    def resume(self):
        """Resume the scheduler"""
        self.paused = False
        self._log("Scheduler resumed")

    def get_stats(self) -> dict:
        """Get current statistics"""
        return {
            'total_jobs': len(self.jobs),
            'pending': len(self.get_pending_jobs()),
            'success': len(self.get_success_jobs()),
            'retrying': len(self.get_retry_jobs()),
            'failed': len(self.get_failed_jobs()),
            'accounts': len(self.accounts),
            'running': self.running,
            'paused': self.paused,
        }

    def generate_error_report(self) -> dict:
        """Generate a report of all errors grouped by type.

        Returns:
            dict: {
                'summary': {error_type: count},
                'accounts_by_error': {error_type: [account_list]},
                'details': [{job_id, account, error_type, error, screenshot}]
            }
        """
        failed_jobs = self.get_failed_jobs()

        # Group by error type
        by_error_type = {}
        for job in failed_jobs:
            error_type = job.error_type or 'unknown'
            if error_type not in by_error_type:
                by_error_type[error_type] = []
            by_error_type[error_type].append(job)

        # Build summary
        summary = {et: len(jobs) for et, jobs in by_error_type.items()}

        # Accounts by error type
        accounts_by_error = {}
        for error_type, jobs in by_error_type.items():
            accounts_by_error[error_type] = list(set(j.account for j in jobs))

        # Detailed list
        details = []
        for job in failed_jobs:
            details.append({
                'job_id': job.id,
                'account': job.account,
                'error_type': job.error_type or 'unknown',
                'error': job.last_error,
                'screenshot': job.screenshot_path,
                'attempts': job.attempts,
            })

        return {
            'summary': summary,
            'accounts_by_error': accounts_by_error,
            'details': details,
            'total_failed': len(failed_jobs),
        }

    def save_error_report(self, filepath: str = None) -> str:
        """Save error report to a file.

        Args:
            filepath: Optional path. Defaults to error_report_YYYYMMDD_HHMMSS.json

        Returns:
            Path to saved report file
        """
        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"error_report_{timestamp}.json"

        report = self.generate_error_report()
        report['generated_at'] = datetime.now().isoformat()

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        self._log(f"Error report saved: {filepath}")
        return filepath

    def get_report_text(self) -> str:
        """Generate human-readable error report text."""
        report = self.generate_error_report()

        lines = []
        lines.append("=" * 50)
        lines.append("ERROR REPORT")
        lines.append("=" * 50)
        lines.append(f"Total Failed: {report['total_failed']}")
        lines.append("")

        if report['summary']:
            lines.append("SUMMARY BY ERROR TYPE:")
            for error_type, count in sorted(report['summary'].items(), key=lambda x: -x[1]):
                lines.append(f"  - {error_type}: {count}")
            lines.append("")

            lines.append("AFFECTED ACCOUNTS:")
            for error_type, accounts in report['accounts_by_error'].items():
                lines.append(f"  [{error_type}]")
                for acc in accounts:
                    lines.append(f"    - {acc}")
            lines.append("")

            lines.append("SCREENSHOTS:")
            screenshots = [d for d in report['details'] if d['screenshot']]
            if screenshots:
                for d in screenshots:
                    lines.append(f"  - {d['account']} ({d['error_type']}): {d['screenshot']}")
            else:
                lines.append("  No screenshots captured")
        else:
            lines.append("No errors to report!")

        lines.append("=" * 50)
        return "\n".join(lines)


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Posting Scheduler CLI')
    parser.add_argument('--add-folder', help='Add video folder')
    parser.add_argument('--add-accounts', nargs='+', help='Add accounts')
    parser.add_argument('--status', action='store_true', help='Show status')
    parser.add_argument('--run', action='store_true', help='Run scheduler')
    parser.add_argument('--retry-all', action='store_true', help='Retry all failed jobs')

    args = parser.parse_args()

    scheduler = PostingScheduler()

    if args.add_folder:
        scheduler.add_video_folder(args.add_folder)

    if args.add_accounts:
        for acc in args.add_accounts:
            scheduler.add_account(acc)

    if args.retry_all:
        scheduler.retry_all_failed()

    if args.status:
        stats = scheduler.get_stats()
        print("\n=== Scheduler Status ===")
        print(f"Jobs: {stats['total_jobs']} total")
        print(f"  - Pending: {stats['pending']}")
        print(f"  - Success: {stats['success']}")
        print(f"  - Retrying: {stats['retrying']}")
        print(f"  - Failed: {stats['failed']}")
        print(f"Accounts: {stats['accounts']}")
        print(f"Running: {stats['running']}")

    if args.run:
        print("Starting scheduler (Ctrl+C to stop)...")
        scheduler.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            scheduler.stop()
