"""
Posting Scheduler - Core queue/retry/state management system.

Features:
- Load videos from multiple folders
- Track posting state (posted, pending, failed, retrying)
- Auto-retry failed posts with configurable attempts/delay
- Schedule: one post per account per day
- State persistence to survive restarts
"""
import os
import sys
import csv
import json
import time
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Callable
from enum import Enum

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


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
                    # Only add if not already in jobs
                    if shortcode not in self.jobs:
                        job = PostJob(
                            id=shortcode,
                            video_path=video_path,
                            caption=caption,
                            source_folder=folder_path
                        )
                        self.jobs[shortcode] = job
                        added += 1

        self._log(f"Added {added} videos from {os.path.basename(folder_path)}")
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
        """Execute a single posting job"""
        from post_reel_smart import SmartInstagramPoster

        job.status = PostStatus.IN_PROGRESS.value
        job.attempts += 1
        job.last_attempt = datetime.now().isoformat()
        self.save_state()

        self._log(f"Posting {job.id} to {job.account} (attempt {job.attempts}/{job.max_attempts})")

        try:
            # TEST MODE: Force failure on first attempt
            if self.test_retry_mode and job.attempts == 1:
                self._log(f"[TEST MODE] Simulating failure on first attempt")
                raise Exception("TEST MODE: Simulated failure for retry testing")

            poster = SmartInstagramPoster(job.account)
            poster.connect()
            success = poster.post(job.video_path, job.caption, humanize=self.humanize)
            poster.cleanup()

            if success:
                job.status = PostStatus.SUCCESS.value
                job.completed_at = datetime.now().isoformat()
                job.last_error = ""
                self.accounts[job.account].record_post(True)
                self._log(f"[OK] {job.id} posted successfully")

                if self.on_job_complete:
                    self.on_job_complete(job, True)

                self.save_state()
                return True
            else:
                raise Exception("Post returned False")

        except Exception as e:
            error_msg = str(e)
            job.last_error = error_msg
            self._log(f"[FAIL] {job.id}: {error_msg}")

            # Capture error details from poster if available
            if 'poster' in locals():
                if poster.last_error_type:
                    job.error_type = poster.last_error_type
                    self._log(f"[ERROR TYPE] {poster.last_error_type}: {poster.last_error_message}")
                if poster.last_screenshot_path:
                    job.screenshot_path = poster.last_screenshot_path
                    self._log(f"[SCREENSHOT] {poster.last_screenshot_path}")

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
