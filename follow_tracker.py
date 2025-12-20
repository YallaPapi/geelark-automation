"""
Follow Progress Tracker - tracks follow jobs with file-locked CSV.

Mirrors progress_tracker.py for posting. Tracks:
- Follow jobs in campaigns/{campaign}/follow_progress.csv
- Already-followed accounts in all_followed_accounts.txt

This module provides process-safe job tracking for multi-worker following.
"""

import os
import csv
import time
import logging
import tempfile
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Set

import portalocker

logger = logging.getLogger(__name__)


# Error classification - mirrors progress_tracker.py exactly
ACCOUNT_ERRORS = {
    'terminated', 'suspended', 'disabled', 'verification',
    'logged_out', 'action_blocked', 'banned', 'captcha',
    'id_verification', 'app_update'
}

INFRASTRUCTURE_ERRORS = {
    'adb_timeout', 'appium_crash', 'connection_dropped',
    'claude_stuck', 'glogin_expired', 'phone_error',
    'max_steps', 'loop_stuck', 'unknown'
}


class FollowTracker:
    """
    Process-safe follow job tracker using file-locked CSV.

    Mirrors ProgressTracker from progress_tracker.py for posting.
    """

    # CSV columns for follow_progress.csv
    FIELDNAMES = [
        'job_id',           # Unique ID: {account}_{target}
        'account',          # Campaign account doing the follow
        'target',           # Target username to follow
        'status',           # pending/claimed/success/failed/retrying
        'worker_id',        # Which worker processed this
        'claimed_at',       # Timestamp when claimed
        'completed_at',     # Timestamp when completed
        'error',            # Error message if failed
        'attempts',         # Retry attempt count
        'max_attempts',     # Max retry attempts
        'retry_at',         # When to retry (ISO timestamp)
        'error_type',       # Specific error type (adb_timeout, action_blocked, etc.)
        'error_category',   # account or infrastructure
    ]

    def __init__(
        self,
        progress_file: str,
        followed_file: str = "all_followed_accounts.txt",
        lock_timeout: float = 30.0,
        max_attempts: int = 3
    ):
        """
        Initialize the follow tracker.

        Args:
            progress_file: Path to follow_progress.csv
            followed_file: Path to all_followed_accounts.txt
            lock_timeout: Timeout for file lock acquisition
            max_attempts: Default max retry attempts per job
        """
        self.progress_file = progress_file
        self.followed_file = followed_file
        self.lock_timeout = lock_timeout
        self.default_max_attempts = max_attempts

        # Cached set of already-followed accounts
        self._followed_accounts: Optional[Set[str]] = None

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(progress_file) or '.', exist_ok=True)

        # Initialize files if they don't exist
        self._ensure_files_exist()

    def _ensure_files_exist(self) -> None:
        """Create empty files with headers if they don't exist."""
        # Create progress CSV with header if missing
        if not os.path.exists(self.progress_file):
            with open(self.progress_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writeheader()

        # Create followed accounts file if missing
        if not os.path.exists(self.followed_file):
            with open(self.followed_file, 'w', encoding='utf-8') as f:
                pass  # Empty file

    def exists(self) -> bool:
        """Check if progress file exists and has jobs (beyond header)."""
        if not os.path.exists(self.progress_file):
            return False

        with open(self.progress_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for _ in reader:
                return True  # Has at least one job
        return False

    def _load_followed_accounts(self) -> Set[str]:
        """Load already-followed accounts from file."""
        if self._followed_accounts is not None:
            return self._followed_accounts

        self._followed_accounts = set()

        if os.path.exists(self.followed_file):
            with open(self.followed_file, 'r', encoding='utf-8') as f:
                for line in f:
                    username = line.strip()
                    if username:
                        self._followed_accounts.add(username.lower())

        return self._followed_accounts

    def is_already_followed(self, target: str) -> bool:
        """Check if target has already been followed."""
        followed = self._load_followed_accounts()
        return target.lower() in followed

    def mark_followed(self, target: str) -> None:
        """Mark a target as followed (add to all_followed_accounts.txt)."""
        target_lower = target.lower()

        # Update in-memory cache
        followed = self._load_followed_accounts()
        if target_lower in followed:
            return  # Already marked

        followed.add(target_lower)

        # Append to file with lock
        lock_file = self.followed_file + '.lock'
        with portalocker.Lock(lock_file, timeout=self.lock_timeout):
            with open(self.followed_file, 'a', encoding='utf-8') as f:
                f.write(f"{target_lower}\n")

    def seed_from_targets(
        self,
        targets_file: str,
        accounts: List[str],
        max_follows_per_account: int = 1
    ) -> int:
        """
        Seed follow jobs from targets file, distributing evenly across accounts.

        Args:
            targets_file: Path to followers.txt (one username per line)
            accounts: List of campaign account names
            max_follows_per_account: Max jobs to assign per account

        Returns:
            Number of jobs created
        """
        if not accounts:
            logger.warning("No accounts provided for seeding")
            return 0

        # Load targets
        targets = []
        if os.path.exists(targets_file):
            with open(targets_file, 'r', encoding='utf-8') as f:
                for line in f:
                    target = line.strip().lstrip('@')
                    if target and not target.startswith('#'):
                        targets.append(target)

        if not targets:
            logger.warning(f"No targets found in {targets_file}")
            return 0

        # Filter out already-followed targets
        followed = self._load_followed_accounts()
        targets = [t for t in targets if t.lower() not in followed]

        if not targets:
            logger.info("All targets have already been followed")
            return 0

        # Also filter out targets already in progress file
        existing_targets = set()
        if os.path.exists(self.progress_file):
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_targets.add(row.get('target', '').lower())

        targets = [t for t in targets if t.lower() not in existing_targets]

        if not targets:
            logger.info("All new targets are already in progress file")
            return 0

        # Distribute targets evenly across accounts (round-robin)
        jobs = []
        account_caps = {acc: max_follows_per_account for acc in accounts}
        account_idx = 0

        for target in targets:
            # Find an account with remaining capacity
            attempts = 0
            while attempts < len(accounts):
                account = accounts[account_idx]
                if account_caps[account] > 0:
                    job_id = f"{account}_{target}"
                    jobs.append({
                        'job_id': job_id,
                        'account': account,
                        'target': target,
                        'status': 'pending',
                        'worker_id': '',
                        'claimed_at': '',
                        'completed_at': '',
                        'error': '',
                        'attempts': '0',
                        'max_attempts': str(self.default_max_attempts),
                        'retry_at': '',
                        'error_type': '',
                        'error_category': '',
                    })
                    account_caps[account] -= 1
                    account_idx = (account_idx + 1) % len(accounts)
                    break

                account_idx = (account_idx + 1) % len(accounts)
                attempts += 1

            # Check if we've hit capacity for all accounts
            if all(cap == 0 for cap in account_caps.values()):
                break

        if not jobs:
            logger.info("No jobs to seed (all accounts at capacity)")
            return 0

        # Write jobs to CSV with lock
        lock_file = self.progress_file + '.lock'
        with portalocker.Lock(lock_file, timeout=self.lock_timeout):
            with open(self.progress_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                for job in jobs:
                    writer.writerow(job)

        logger.info(f"Seeded {len(jobs)} follow jobs across {len(accounts)} accounts")
        return len(jobs)

    def _read_all_jobs(self) -> List[Dict[str, Any]]:
        """Read all jobs from CSV."""
        jobs = []
        if os.path.exists(self.progress_file):
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    jobs.append(dict(row))
        return jobs

    def _write_all_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        """Write all jobs to CSV atomically."""
        # Write to temp file first
        fd, temp_path = tempfile.mkstemp(
            suffix='.csv',
            dir=os.path.dirname(self.progress_file) or '.'
        )
        try:
            with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writeheader()
                for job in jobs:
                    writer.writerow(job)

            # Atomic rename
            os.replace(temp_path, self.progress_file)
        except Exception:
            # Clean up temp file on error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def claim_next_job(
        self,
        worker_id: int,
        max_follows_per_account: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Claim the next available pending job for this worker.

        Args:
            worker_id: ID of the worker claiming the job
            max_follows_per_account: Max follows per account per day

        Returns:
            Job dict if claimed, None if no jobs available
        """
        lock_file = self.progress_file + '.lock'
        now = datetime.now()
        today = now.date().isoformat()

        with portalocker.Lock(lock_file, timeout=self.lock_timeout):
            jobs = self._read_all_jobs()

            # Count successful follows per account today
            account_follows_today = {}
            for job in jobs:
                if job.get('status') == 'success':
                    completed = job.get('completed_at', '')
                    if completed and completed.startswith(today):
                        account = job.get('account', '')
                        account_follows_today[account] = account_follows_today.get(account, 0) + 1

            # Find next claimable job
            for job in jobs:
                if job.get('status') not in ('pending', 'retrying'):
                    continue

                # Check retry_at for retrying jobs
                if job.get('status') == 'retrying':
                    retry_at = job.get('retry_at', '')
                    if retry_at:
                        try:
                            retry_time = datetime.fromisoformat(retry_at)
                            if now < retry_time:
                                continue  # Not time to retry yet
                        except ValueError:
                            pass  # Invalid timestamp, allow retry

                # Check per-account daily limit
                account = job.get('account', '')
                if account_follows_today.get(account, 0) >= max_follows_per_account:
                    continue  # Account at daily limit

                # Claim this job
                job['status'] = 'claimed'
                job['worker_id'] = str(worker_id)
                job['claimed_at'] = now.isoformat()
                job['attempts'] = str(int(job.get('attempts', 0)) + 1)

                self._write_all_jobs(jobs)

                logger.debug(f"Worker {worker_id} claimed job: {job['job_id']}")
                return job

            return None  # No jobs available

    def update_job_status(
        self,
        job_id: str,
        status: str,
        worker_id: int,
        error: Optional[str] = None,
        retry_delay_minutes: int = 5
    ) -> bool:
        """
        Update job status after processing.

        Args:
            job_id: Job identifier
            status: New status (success/failed)
            worker_id: Worker that processed the job
            error: Error message if failed
            retry_delay_minutes: Minutes to wait before retry

        Returns:
            True if updated, False if job not found
        """
        lock_file = self.progress_file + '.lock'
        now = datetime.now()

        with portalocker.Lock(lock_file, timeout=self.lock_timeout):
            jobs = self._read_all_jobs()

            for job in jobs:
                if job.get('job_id') != job_id:
                    continue

                # Verify worker owns this job
                if job.get('worker_id') != str(worker_id):
                    logger.warning(
                        f"Worker {worker_id} tried to update job {job_id} "
                        f"owned by worker {job.get('worker_id')}"
                    )
                    return False

                if status == 'success':
                    job['status'] = 'success'
                    job['completed_at'] = now.isoformat()
                    job['error'] = ''
                    job['error_type'] = ''
                    job['error_category'] = ''

                    # Mark target as followed
                    self.mark_followed(job.get('target', ''))

                elif status == 'failed':
                    # Classify error
                    error_type, error_category = self._classify_error(error or '')

                    job['error'] = error or ''
                    job['error_type'] = error_type
                    job['error_category'] = error_category

                    attempts = int(job.get('attempts', 0))
                    max_attempts = int(job.get('max_attempts', self.default_max_attempts))

                    # Account errors are never retried
                    if error_category == 'account':
                        job['status'] = 'failed'
                        job['completed_at'] = now.isoformat()
                        logger.info(f"Job {job_id} permanently failed: {error_type}")

                    # Infrastructure errors can be retried
                    elif attempts < max_attempts:
                        job['status'] = 'retrying'
                        retry_time = now + timedelta(minutes=retry_delay_minutes)
                        job['retry_at'] = retry_time.isoformat()
                        logger.info(
                            f"Job {job_id} scheduled for retry "
                            f"(attempt {attempts}/{max_attempts})"
                        )

                    else:
                        job['status'] = 'failed'
                        job['completed_at'] = now.isoformat()
                        logger.info(
                            f"Job {job_id} failed after {attempts} attempts"
                        )

                self._write_all_jobs(jobs)
                return True

            logger.warning(f"Job {job_id} not found for update")
            return False

    def _classify_error(self, error: str) -> Tuple[str, str]:
        """
        Classify error into type and category.

        Returns:
            Tuple of (error_type, error_category)
        """
        error_lower = error.lower()

        # Check for account errors (non-retryable)
        account_patterns = {
            'terminated': ['terminated', 'permanently disabled', 'no longer have access'],
            'suspended': ['suspended', 'disabled', 'account was disabled'],
            'verification': ['verify your identity', 'upload a photo', 'id verification'],
            'logged_out': ['log in to instagram', 'create new account', 'logged out'],
            'action_blocked': ['action blocked', 'try again later', 'temporarily blocked'],
            'captcha': ['confirm it\'s you', 'security check', 'unusual activity'],
            'banned': ['banned', 'violating'],
        }

        for error_type, patterns in account_patterns.items():
            for pattern in patterns:
                if pattern in error_lower:
                    return (error_type, 'account')

        # Check for infrastructure errors (retryable)
        infra_patterns = {
            'adb_timeout': ['adb', 'timeout', 'never appeared', 'device not found'],
            'appium_crash': ['appium', 'crash', 'session', 'proxy'],
            'connection_dropped': ['connection', 'dropped', 'lost', 'disconnect'],
            'claude_stuck': ['max steps', 'loop', 'stuck'],
            'glogin_expired': ['glogin', 'expired', 'authentication'],
            'phone_error': ['phone', 'boot', 'start'],
        }

        for error_type, patterns in infra_patterns.items():
            for pattern in patterns:
                if pattern in error_lower:
                    return (error_type, 'infrastructure')

        # Default to infrastructure (retryable)
        return ('unknown', 'infrastructure')

    def release_stale_claims(self, max_age_seconds: int = 600) -> int:
        """
        Release jobs that have been claimed for too long.

        Args:
            max_age_seconds: Max time a job can be claimed (default 10 min)

        Returns:
            Number of claims released
        """
        lock_file = self.progress_file + '.lock'
        now = datetime.now()
        released = 0

        with portalocker.Lock(lock_file, timeout=self.lock_timeout):
            jobs = self._read_all_jobs()

            for job in jobs:
                if job.get('status') != 'claimed':
                    continue

                claimed_at = job.get('claimed_at', '')
                if not claimed_at:
                    continue

                try:
                    claim_time = datetime.fromisoformat(claimed_at)
                    age = (now - claim_time).total_seconds()

                    if age > max_age_seconds:
                        attempts = int(job.get('attempts', 0))
                        max_attempts = int(job.get('max_attempts', self.default_max_attempts))

                        if attempts < max_attempts:
                            job['status'] = 'retrying'
                            job['retry_at'] = now.isoformat()
                            job['error'] = 'Stale claim released'
                            job['error_type'] = 'stale_claim'
                            job['error_category'] = 'infrastructure'
                        else:
                            job['status'] = 'failed'
                            job['completed_at'] = now.isoformat()
                            job['error'] = 'Stale claim - max attempts reached'
                            job['error_type'] = 'stale_claim'
                            job['error_category'] = 'infrastructure'

                        released += 1
                        logger.info(
                            f"Released stale claim: {job['job_id']} "
                            f"(age: {age:.0f}s)"
                        )

                except ValueError:
                    pass  # Invalid timestamp

            if released > 0:
                self._write_all_jobs(jobs)

        return released

    def verify_job_before_follow(
        self,
        job_id: str,
        worker_id: int
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify job is still valid and claimed by this worker.

        Args:
            job_id: Job identifier
            worker_id: Worker ID to verify

        Returns:
            Tuple of (is_valid, error_message)
        """
        lock_file = self.progress_file + '.lock'

        with portalocker.Lock(lock_file, timeout=self.lock_timeout):
            jobs = self._read_all_jobs()

            for job in jobs:
                if job.get('job_id') != job_id:
                    continue

                if job.get('status') != 'claimed':
                    return (False, f"Job status is {job.get('status')}, not claimed")

                if job.get('worker_id') != str(worker_id):
                    return (False, f"Job claimed by worker {job.get('worker_id')}")

                return (True, None)

            return (False, "Job not found")

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about follow jobs."""
        stats = {
            'pending': 0,
            'claimed': 0,
            'success': 0,
            'failed': 0,
            'retrying': 0,
            'total': 0,
        }

        if os.path.exists(self.progress_file):
            with open(self.progress_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    status = row.get('status', 'pending')
                    if status in stats:
                        stats[status] += 1
                    stats['total'] += 1

        return stats

    def reset(self) -> None:
        """Reset progress file (delete all jobs)."""
        lock_file = self.progress_file + '.lock'

        with portalocker.Lock(lock_file, timeout=self.lock_timeout):
            with open(self.progress_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
                writer.writeheader()

        logger.info("Reset follow progress file")


if __name__ == "__main__":
    # Quick test
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        progress = os.path.join(tmpdir, "test_progress.csv")
        followed = os.path.join(tmpdir, "test_followed.txt")
        targets = os.path.join(tmpdir, "test_targets.txt")

        # Create test targets
        with open(targets, 'w') as f:
            f.write("user1\nuser2\nuser3\nuser4\nuser5\n")

        tracker = FollowTracker(progress, followed)

        # Seed jobs
        accounts = ['acc1', 'acc2']
        seeded = tracker.seed_from_targets(targets, accounts, max_follows_per_account=2)
        print(f"Seeded {seeded} jobs")

        # Get stats
        stats = tracker.get_stats()
        print(f"Stats: {stats}")

        # Claim a job
        job = tracker.claim_next_job(worker_id=0, max_follows_per_account=2)
        if job:
            print(f"Claimed: {job['job_id']}")

            # Update as success
            tracker.update_job_status(job['job_id'], 'success', worker_id=0)
            print("Marked as success")

        # Final stats
        stats = tracker.get_stats()
        print(f"Final stats: {stats}")

        # Check followed
        print(f"user1 followed: {tracker.is_already_followed('user1')}")
