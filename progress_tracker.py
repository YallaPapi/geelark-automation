"""
CSV-Based Progress Tracker with File Locking and Retry Support.

This module provides thread-safe and process-safe job tracking for parallel workers.
It uses file locking to ensure only one worker can claim a job at a time, preventing
duplicate posts across multiple worker processes.

Key features:
- File-based locking using portalocker (cross-platform)
- Atomic writes via temp file + rename
- Claim jobs with worker_id tracking
- Resume support - unclaimed jobs stay pending across restarts
- Status transitions: pending -> claimed -> success/failed/retrying
- Automatic retry with configurable max_attempts and retry_delay
- Non-retryable error classification (suspended, captcha, loggedout, actionblocked)

Usage:
    tracker = ProgressTracker("progress.csv")

    # Seed from input jobs (orchestrator does this once)
    tracker.seed_from_scheduler_state("scheduler_state.json")

    # Workers claim and process jobs
    job = tracker.claim_next_job(worker_id=0)
    if job:
        # ... process job ...
        tracker.update_job_status(job['job_id'], 'success', worker_id=0)
        # Or on failure with retry:
        tracker.update_job_status(job['job_id'], 'failed', worker_id=0, error='...',
                                  max_attempts=3, retry_delay_minutes=5)
"""

import os
import csv
import json
import time
import shutil
import tempfile
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

# Cross-platform file locking
try:
    import portalocker
    HAS_PORTALOCKER = True
except ImportError:
    HAS_PORTALOCKER = False
    # Fallback for Windows without portalocker
    import msvcrt

logger = logging.getLogger(__name__)


class FileLockError(Exception):
    """Raised when file lock cannot be acquired."""
    pass


class ProgressTracker:
    """
    Process-safe progress tracker using CSV with file locking.

    The progress CSV has columns:
        - job_id: Unique identifier (typically the video shortcode)
        - account: Account name to post with
        - video_path: Path to video file
        - caption: Caption text
        - status: pending/claimed/success/failed/skipped
        - worker_id: Which worker claimed/processed this job
        - claimed_at: Timestamp when claimed
        - completed_at: Timestamp when completed
        - error: Error message if failed
    """

    # CSV columns (extended for retry support)
    COLUMNS = [
        'job_id', 'account', 'video_path', 'caption', 'status',
        'worker_id', 'claimed_at', 'completed_at', 'error',
        'attempts', 'max_attempts', 'retry_at', 'error_type'
    ]

    # Valid status values
    STATUS_PENDING = 'pending'
    STATUS_CLAIMED = 'claimed'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED = 'skipped'
    STATUS_RETRYING = 'retrying'

    # Non-retryable error types - these failures should not be retried
    NON_RETRYABLE_ERRORS = {'suspended', 'captcha', 'loggedout', 'actionblocked', 'banned'}

    # Default retry settings
    DEFAULT_MAX_ATTEMPTS = 3
    DEFAULT_RETRY_DELAY_MINUTES = 5

    def __init__(self, progress_file: str, lock_timeout: float = 30.0):
        """
        Initialize the progress tracker.

        Args:
            progress_file: Path to the progress CSV file
            lock_timeout: Maximum seconds to wait for file lock
        """
        self.progress_file = progress_file
        self.lock_file = progress_file + '.lock'
        self.lock_timeout = lock_timeout

    def _acquire_lock(self, file_handle) -> None:
        """Acquire exclusive lock on the file."""
        if HAS_PORTALOCKER:
            portalocker.lock(file_handle, portalocker.LOCK_EX)
        else:
            # Windows fallback
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _release_lock(self, file_handle) -> None:
        """Release the file lock."""
        if HAS_PORTALOCKER:
            portalocker.unlock(file_handle)
        else:
            # Windows fallback
            try:
                file_handle.seek(0)
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
            except:
                pass

    def _read_all_jobs(self) -> List[Dict[str, Any]]:
        """Read all jobs from the progress file."""
        if not os.path.exists(self.progress_file):
            return []

        jobs = []
        with open(self.progress_file, 'r', encoding='utf-8', newline='') as f:
            self._acquire_lock(f)
            try:
                reader = csv.DictReader(f)
                for row in reader:
                    jobs.append(row)
            finally:
                self._release_lock(f)
        return jobs

    def _write_all_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        """
        Write all jobs to the progress file atomically.

        Uses temp file + rename for atomic write.
        """
        # Write to temp file first
        fd, temp_path = tempfile.mkstemp(suffix='.csv', dir=os.path.dirname(self.progress_file) or '.')

        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                writer.writeheader()
                for job in jobs:
                    # Ensure all columns exist
                    row = {col: job.get(col, '') for col in self.COLUMNS}
                    writer.writerow(row)

            # Atomic rename (works on Windows if destination doesn't exist)
            if os.path.exists(self.progress_file):
                os.remove(self.progress_file)
            shutil.move(temp_path, self.progress_file)

        except Exception as e:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except:
                pass
            raise e

    def _locked_operation(self, operation):
        """
        Execute an operation with file locking.

        Args:
            operation: Callable that takes (jobs) and returns (jobs, result)

        Returns:
            The result from the operation
        """
        # Use a separate lock file for coordination
        os.makedirs(os.path.dirname(self.lock_file) or '.', exist_ok=True)

        with open(self.lock_file, 'w') as lock_handle:
            self._acquire_lock(lock_handle)
            try:
                jobs = self._read_all_jobs() if os.path.exists(self.progress_file) else []
                jobs, result = operation(jobs)
                if jobs is not None:
                    self._write_all_jobs(jobs)
                return result
            finally:
                self._release_lock(lock_handle)

    def exists(self) -> bool:
        """Check if progress file exists."""
        return os.path.exists(self.progress_file)

    def _load_success_counts(self) -> Dict[str, int]:
        """
        Load success counts per account from existing progress file.

        Returns:
            Dict mapping account name to number of successful posts
        """
        success_counts = {}
        if not os.path.exists(self.progress_file):
            return success_counts

        with open(self.progress_file, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('status') == self.STATUS_SUCCESS:
                    acc = row.get('account', '')
                    if acc:
                        success_counts[acc] = success_counts.get(acc, 0) + 1
        return success_counts

    def seed_from_scheduler_state(
        self,
        state_file: str,
        account_list: List[str] = None,
        redistribute: bool = True,
        max_posts_per_account_per_day: int = 1
    ) -> int:
        """
        Seed progress file from scheduler_state.json.

        CRITICAL: Enforces per-account daily posting limits!
        - Builds success_count_by_account dict from existing progress file
        - Only assigns jobs to accounts with success_count < max_posts_per_account_per_day
        - Tracks in-memory counts during seeding to prevent exceeding limits
        - Each account can be assigned at most 1 job per seeding pass (no reuse in same batch)

        Args:
            state_file: Path to scheduler_state.json
            account_list: Optional list of accounts to use (overrides state file accounts)
            redistribute: If True, redistribute jobs evenly across accounts
            max_posts_per_account_per_day: Max successful posts per account per day (default 1)

        Returns:
            Number of NEW jobs seeded (not counting existing jobs)
        """
        if not os.path.exists(state_file):
            raise FileNotFoundError(f"Scheduler state file not found: {state_file}")

        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)

        jobs_data = state.get('jobs', [])
        accounts = account_list or [acc['name'] for acc in state.get('accounts', [])]

        # CRITICAL: Build success_count_by_account from existing progress file
        # This tracks how many successful posts each account has TODAY
        success_count_by_account = self._load_success_counts()
        existing_job_ids = set()
        existing_jobs = []

        if os.path.exists(self.progress_file):
            existing_jobs = self._read_all_jobs()
            for job in existing_jobs:
                existing_job_ids.add(job.get('job_id', ''))

        # Log accounts that are at or over the daily limit
        accounts_at_limit = [acc for acc in accounts if success_count_by_account.get(acc, 0) >= max_posts_per_account_per_day]
        if accounts_at_limit:
            logger.info(f"EXCLUDING {len(accounts_at_limit)} accounts at daily limit ({max_posts_per_account_per_day}): {sorted(accounts_at_limit)}")

        # Filter accounts - only those with success_count < max_posts_per_account_per_day
        available_accounts = [
            acc for acc in accounts
            if success_count_by_account.get(acc, 0) < max_posts_per_account_per_day
        ]
        logger.info(f"Available accounts for new jobs: {len(available_accounts)} (excluded {len(accounts_at_limit)} at daily limit)")

        # Filter to pending/retrying jobs that haven't been added yet
        pending_jobs = [
            j for j in jobs_data
            if j.get('status') in ('pending', 'retrying') and j.get('id', '') not in existing_job_ids
        ]

        if not pending_jobs:
            logger.info("No new pending jobs to seed")
            return 0

        if not available_accounts:
            logger.info(f"No available accounts - all {len(accounts)} have hit daily limit of {max_posts_per_account_per_day}")
            return 0

        # CRITICAL: Assign jobs with daily limit tracking
        # Copy success counts to track in-memory during this seeding pass
        seeding_success_counts = dict(success_count_by_account)
        new_jobs = []
        accounts_used_this_batch = set()  # Each account gets at most 1 job per batch

        for job in pending_jobs:
            # Find an account that:
            # 1. Is not already used in this batch
            # 2. Has success_count < max_posts_per_account_per_day
            assigned_account = ''
            for acc in available_accounts:
                if acc in accounts_used_this_batch:
                    continue
                if seeding_success_counts.get(acc, 0) >= max_posts_per_account_per_day:
                    continue
                assigned_account = acc
                accounts_used_this_batch.add(acc)
                # Increment in-memory count (as if this will succeed)
                # This prevents assigning more than max_posts_per_account_per_day jobs
                # even when max > 1
                seeding_success_counts[acc] = seeding_success_counts.get(acc, 0) + 1
                break

            new_jobs.append({
                'job_id': job.get('id', ''),
                'account': assigned_account,  # Empty string if no account available
                'video_path': job.get('video_path', ''),
                'caption': job.get('caption', ''),
                'status': self.STATUS_PENDING,
                'worker_id': '',
                'claimed_at': '',
                'completed_at': '',
                'error': '',
                'attempts': '0',
                'max_attempts': str(self.DEFAULT_MAX_ATTEMPTS),
                'retry_at': '',
                'error_type': ''
            })

        # Combine existing jobs with new jobs
        all_jobs = existing_jobs + new_jobs

        # Log distribution for visibility
        assigned_count = sum(1 for j in new_jobs if j['account'])
        unassigned_count = sum(1 for j in new_jobs if not j['account'])
        logger.info(f"Seeded {len(new_jobs)} NEW jobs: {assigned_count} assigned to accounts, {unassigned_count} unassigned")
        logger.info(f"Using {len(accounts_used_this_batch)} accounts this batch (max {max_posts_per_account_per_day} posts/account/day)")
        logger.info(f"Total jobs in progress file: {len(all_jobs)}")

        self._write_all_jobs(all_jobs)
        return len(new_jobs)

    def seed_from_jobs(self, jobs: List[Dict[str, Any]]) -> int:
        """
        Seed progress file from a list of job dictionaries.

        Args:
            jobs: List of dicts with keys: job_id, account, video_path, caption

        Returns:
            Number of jobs seeded
        """
        progress_jobs = []
        for job in jobs:
            progress_jobs.append({
                'job_id': job.get('job_id', job.get('id', '')),
                'account': job.get('account', ''),
                'video_path': job.get('video_path', ''),
                'caption': job.get('caption', ''),
                'status': self.STATUS_PENDING,
                'worker_id': '',
                'claimed_at': '',
                'completed_at': '',
                'error': ''
            })

        self._write_all_jobs(progress_jobs)
        logger.info(f"Seeded {len(progress_jobs)} jobs")
        return len(progress_jobs)

    def _within_daily_limit(self, account: str, success_counts: Dict[str, int], max_per_day: int) -> bool:
        """
        Check if an account is within its daily posting limit.

        Args:
            account: Account name to check
            success_counts: Dict of account -> success count
            max_per_day: Maximum posts allowed per day

        Returns:
            True if account can still post, False if at/over limit
        """
        return success_counts.get(account, 0) < max_per_day

    def claim_next_job(self, worker_id: int, max_posts_per_account_per_day: int = 1) -> Optional[Dict[str, Any]]:
        """
        Claim the next pending job for a worker.

        This operation is atomic - only one worker can claim a job even if
        multiple workers call this simultaneously.

        IMPORTANT (Defense in Depth):
        1. Jobs without an assigned account are SKIPPED (waiting for account)
        2. Account-level locking - a worker will NOT claim a job if
           another worker already has a job claimed for the same account.
        3. Daily limit check - a worker will NOT claim a job if the account
           has already hit max_posts_per_account_per_day successful posts.

        Args:
            worker_id: ID of the worker claiming the job
            max_posts_per_account_per_day: Max successful posts per account per day (default 1)

        Returns:
            The claimed job dict, or None if no pending jobs available
        """
        def _claim_operation(jobs):
            # First, find all accounts currently being processed (claimed by any worker)
            accounts_in_use = set()

            # DEFENSE IN DEPTH: Build success counts to check daily limits
            success_counts = {}
            for job in jobs:
                if job.get('status') == self.STATUS_CLAIMED:
                    account = job.get('account', '')
                    if account:
                        accounts_in_use.add(account)
                elif job.get('status') == self.STATUS_SUCCESS:
                    account = job.get('account', '')
                    if account:
                        success_counts[account] = success_counts.get(account, 0) + 1

            if accounts_in_use:
                logger.debug(f"Accounts currently in use: {accounts_in_use}")

            # Find accounts at daily limit
            accounts_at_limit = {acc for acc, cnt in success_counts.items() if cnt >= max_posts_per_account_per_day}
            if accounts_at_limit:
                logger.debug(f"Accounts at daily limit ({max_posts_per_account_per_day}): {accounts_at_limit}")

            # Find a pending job that:
            # 1. HAS an account assigned
            # 2. Account is NOT currently in use
            # 3. Account has NOT hit daily limit (defense in depth)
            for job in jobs:
                if job.get('status') == self.STATUS_PENDING:
                    account = job.get('account', '')

                    # Skip jobs without an assigned account (waiting for one to be freed)
                    if not account:
                        continue

                    if account in accounts_in_use:
                        # Skip - another worker is already processing this account
                        logger.debug(f"Skipping job {job['job_id']} - account {account} in use")
                        continue

                    # DEFENSE IN DEPTH: Check daily limit
                    if account in accounts_at_limit:
                        logger.warning(f"Skipping job {job['job_id']} - account {account} at daily limit of {max_posts_per_account_per_day}")
                        continue

                    # Claim this job
                    job['status'] = self.STATUS_CLAIMED
                    job['worker_id'] = str(worker_id)
                    job['claimed_at'] = datetime.now().isoformat()
                    logger.info(f"Worker {worker_id} claimed job {job['job_id']} (account: {account})")
                    return jobs, dict(job)

            # No available jobs (either none pending, all have accounts in use, or all waiting for accounts)
            return jobs, None

        return self._locked_operation(_claim_operation)

    def verify_job_before_post(self, job_id: str, worker_id: int) -> tuple:
        """
        Verify a job is still valid before actually posting.

        This is a safety check to prevent duplicate posts. Call this right before
        the actual Instagram posting to ensure:
        1. The job is still claimed by this worker (not stolen/completed)
        2. No duplicate success exists for this exact job

        Args:
            job_id: The job ID to verify
            worker_id: The worker attempting to post

        Returns:
            (is_valid: bool, error_message: str)
        """
        def _verify_operation(jobs):
            for job in jobs:
                if job.get('job_id') == job_id:
                    status = job.get('status', '')
                    claimed_by = job.get('worker_id', '')

                    if status == 'success':
                        return None, (False, f"Job already completed successfully")

                    if status == 'claimed':
                        if str(claimed_by) == str(worker_id):
                            return None, (True, "")
                        else:
                            return None, (False, f"Job claimed by worker {claimed_by}, not {worker_id}")

                    if status == 'pending':
                        return None, (False, f"Job is pending, not claimed")

                    return None, (False, f"Unexpected status: {status}")

            return None, (False, f"Job {job_id} not found")

        return self._locked_operation(_verify_operation)

    def _classify_error(self, error: str) -> str:
        """
        Classify an error message into an error type.

        Returns one of the NON_RETRYABLE_ERRORS or empty string for retryable errors.
        """
        error_lower = error.lower() if error else ''

        if 'suspended' in error_lower or 'account has been suspended' in error_lower:
            return 'suspended'
        elif 'captcha' in error_lower or 'verify' in error_lower:
            return 'captcha'
        elif 'log in' in error_lower or 'logged out' in error_lower or 'sign up' in error_lower:
            return 'loggedout'
        elif 'action blocked' in error_lower or 'try again later' in error_lower:
            return 'actionblocked'
        elif 'banned' in error_lower or 'disabled' in error_lower:
            return 'banned'
        else:
            return ''  # Retryable

    def update_job_status(
        self,
        job_id: str,
        status: str,
        worker_id: int,
        error: str = '',
        retry_delay_minutes: float = None
    ) -> bool:
        """
        Update the status of a job with automatic retry logic.

        RETRY BEHAVIOR:
        - On success: marks job as success
        - On failure:
          - Increments attempts counter
          - If error is non-retryable (suspended, captcha, loggedout, actionblocked, banned):
            marks as failed immediately
          - If attempts < max_attempts: marks as retrying with retry_at timestamp
          - If attempts >= max_attempts: marks as failed (permanent)

        Args:
            job_id: The job ID to update
            status: New status (success/failed/skipped)
            worker_id: Worker that processed the job
            error: Error message if failed
            retry_delay_minutes: Minutes before retry (default: DEFAULT_RETRY_DELAY_MINUTES)

        Returns:
            True if job was found and updated
        """
        if retry_delay_minutes is None:
            retry_delay_minutes = self.DEFAULT_RETRY_DELAY_MINUTES

        def _update_operation(jobs):
            for job in jobs:
                if job.get('job_id') == job_id:
                    job['worker_id'] = str(worker_id)
                    job['completed_at'] = datetime.now().isoformat()
                    job['error'] = error[:500] if error else ''  # Truncate long errors

                    if status == self.STATUS_SUCCESS:
                        # Success - job is done
                        job['status'] = self.STATUS_SUCCESS
                        logger.info(f"Worker {worker_id} completed job {job_id} successfully")

                    elif status == self.STATUS_FAILED:
                        # Failure - check if we should retry
                        attempts = int(job.get('attempts', 0)) + 1
                        max_attempts = int(job.get('max_attempts', self.DEFAULT_MAX_ATTEMPTS))
                        job['attempts'] = str(attempts)

                        # Classify the error
                        error_type = self._classify_error(error)
                        job['error_type'] = error_type

                        if error_type in self.NON_RETRYABLE_ERRORS:
                            # Non-retryable error - fail permanently
                            job['status'] = self.STATUS_FAILED
                            logger.warning(f"Worker {worker_id} job {job_id} FAILED (non-retryable: {error_type})")

                        elif attempts >= max_attempts:
                            # Max attempts reached - fail permanently
                            job['status'] = self.STATUS_FAILED
                            logger.warning(f"Worker {worker_id} job {job_id} FAILED (max attempts {max_attempts} reached)")

                        else:
                            # Retryable - set to retrying with delay
                            job['status'] = self.STATUS_RETRYING
                            from datetime import timedelta
                            retry_at = datetime.now() + timedelta(minutes=retry_delay_minutes)
                            job['retry_at'] = retry_at.isoformat()
                            logger.info(f"Worker {worker_id} job {job_id} will RETRY in {retry_delay_minutes} min (attempt {attempts}/{max_attempts})")

                    else:
                        # Other status (skipped, etc.)
                        job['status'] = status
                        logger.info(f"Worker {worker_id} updated job {job_id} to {status}")

                    return jobs, True

            logger.warning(f"Job {job_id} not found in progress file")
            return jobs, False

        return self._locked_operation(_update_operation)

    def get_retry_jobs(self) -> List[Dict[str, Any]]:
        """
        Get all jobs that are in RETRYING status and ready to be retried.

        A job is ready for retry if:
        - status == RETRYING
        - retry_at timestamp has passed (or is empty)

        Returns:
            List of job dicts ready for retry
        """
        if not os.path.exists(self.progress_file):
            return []

        jobs = self._read_all_jobs()
        ready_jobs = []
        now = datetime.now()

        for job in jobs:
            if job.get('status') == self.STATUS_RETRYING:
                retry_at_str = job.get('retry_at', '')
                if retry_at_str:
                    try:
                        retry_at = datetime.fromisoformat(retry_at_str)
                        if now >= retry_at:
                            ready_jobs.append(job)
                    except ValueError:
                        # Invalid timestamp, allow retry
                        ready_jobs.append(job)
                else:
                    # No retry_at set, allow immediately
                    ready_jobs.append(job)

        return ready_jobs

    def claim_retry_job(self, worker_id: int, max_posts_per_account_per_day: int = 1) -> Optional[Dict[str, Any]]:
        """
        Claim a job that is ready to be retried.

        Similar to claim_next_job but only looks at RETRYING jobs whose
        retry_at timestamp has passed.

        Args:
            worker_id: ID of the worker claiming the job
            max_posts_per_account_per_day: Max successful posts per account per day

        Returns:
            The claimed job dict, or None if no retry jobs available
        """
        def _claim_retry_operation(jobs):
            now = datetime.now()

            # Build success counts for daily limit check
            success_counts = {}
            accounts_in_use = set()

            for job in jobs:
                acc = job.get('account', '')
                if not acc:
                    continue
                if job.get('status') == self.STATUS_CLAIMED:
                    accounts_in_use.add(acc)
                elif job.get('status') == self.STATUS_SUCCESS:
                    success_counts[acc] = success_counts.get(acc, 0) + 1

            # Find a RETRYING job ready to retry
            for job in jobs:
                if job.get('status') != self.STATUS_RETRYING:
                    continue

                acc = job.get('account', '')
                if not acc:
                    continue

                # Check retry_at
                retry_at_str = job.get('retry_at', '')
                if retry_at_str:
                    try:
                        retry_at = datetime.fromisoformat(retry_at_str)
                        if now < retry_at:
                            continue  # Not ready yet
                    except ValueError:
                        pass  # Invalid timestamp, allow retry

                # Check account not in use
                if acc in accounts_in_use:
                    continue

                # Check daily limit
                if success_counts.get(acc, 0) >= max_posts_per_account_per_day:
                    continue

                # Claim this job
                job['status'] = self.STATUS_CLAIMED
                job['worker_id'] = str(worker_id)
                job['claimed_at'] = now.isoformat()
                job['retry_at'] = ''  # Clear retry_at
                logger.info(f"Worker {worker_id} claimed RETRY job {job['job_id']} (account: {acc}, attempt {job.get('attempts', '?')})")
                return jobs, dict(job)

            return jobs, None

        return self._locked_operation(_claim_retry_operation)

    def release_claimed_job(self, job_id: str, worker_id: int) -> bool:
        """
        Release a claimed job back to pending status.

        Useful if a worker crashes or is interrupted before completing.

        Args:
            job_id: The job ID to release
            worker_id: Worker that had claimed the job

        Returns:
            True if job was found and released
        """
        def _release_operation(jobs):
            for job in jobs:
                if job.get('job_id') == job_id and job.get('worker_id') == str(worker_id):
                    if job.get('status') == self.STATUS_CLAIMED:
                        job['status'] = self.STATUS_PENDING
                        job['worker_id'] = ''
                        job['claimed_at'] = ''
                        logger.info(f"Released job {job_id} back to pending")
                        return jobs, True
            return jobs, False

        return self._locked_operation(_release_operation)

    def release_stale_claims(self, max_age_seconds: int = 600) -> int:
        """
        Release jobs that have been claimed for too long without completing.

        Args:
            max_age_seconds: Maximum age of claim before releasing (default 10 min)

        Returns:
            Number of jobs released
        """
        def _release_stale_operation(jobs):
            released = 0
            now = datetime.now()
            for job in jobs:
                if job.get('status') == self.STATUS_CLAIMED:
                    claimed_at = job.get('claimed_at', '')
                    if claimed_at:
                        try:
                            claim_time = datetime.fromisoformat(claimed_at)
                            age = (now - claim_time).total_seconds()
                            if age > max_age_seconds:
                                job['status'] = self.STATUS_PENDING
                                job['worker_id'] = ''
                                job['claimed_at'] = ''
                                logger.info(f"Released stale claim on {job['job_id']} (age: {age:.0f}s)")
                                released += 1
                        except:
                            pass
            return jobs, released

        return self._locked_operation(_release_stale_operation)

    def get_stats(self) -> Dict[str, int]:
        """Get job status statistics."""
        jobs = self._read_all_jobs()
        stats = {
            'total': len(jobs),
            'pending': 0,
            'claimed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'retrying': 0
        }
        for job in jobs:
            status = job.get('status', '')
            if status in stats:
                stats[status] += 1
        return stats

    def get_worker_stats(self) -> Dict[int, Dict[str, int]]:
        """Get statistics per worker."""
        jobs = self._read_all_jobs()
        worker_stats = {}
        for job in jobs:
            worker_id = job.get('worker_id', '')
            if worker_id:
                try:
                    wid = int(worker_id)
                    if wid not in worker_stats:
                        worker_stats[wid] = {'success': 0, 'failed': 0, 'claimed': 0}
                    status = job.get('status', '')
                    if status in worker_stats[wid]:
                        worker_stats[wid][status] += 1
                except ValueError:
                    pass
        return worker_stats

    def is_complete(self) -> bool:
        """Check if all jobs are complete (no pending, claimed, or retrying)."""
        stats = self.get_stats()
        return stats['pending'] == 0 and stats['claimed'] == 0 and stats['retrying'] == 0


if __name__ == "__main__":
    # Demo/test
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    # Create a test progress file
    test_file = "test_progress.csv"
    tracker = ProgressTracker(test_file)

    print("\n1. Seeding with test jobs...")
    test_jobs = [
        {'job_id': 'video1', 'account': 'account_a', 'video_path': '/path/to/v1.mp4', 'caption': 'Test 1'},
        {'job_id': 'video2', 'account': 'account_b', 'video_path': '/path/to/v2.mp4', 'caption': 'Test 2'},
        {'job_id': 'video3', 'account': 'account_a', 'video_path': '/path/to/v3.mp4', 'caption': 'Test 3'},
    ]
    tracker.seed_from_jobs(test_jobs)
    print(f"   Stats: {tracker.get_stats()}")

    print("\n2. Worker 0 claims a job...")
    job = tracker.claim_next_job(worker_id=0)
    print(f"   Claimed: {job['job_id']} for account {job['account']}")
    print(f"   Stats: {tracker.get_stats()}")

    print("\n3. Worker 1 claims a job...")
    job = tracker.claim_next_job(worker_id=1)
    print(f"   Claimed: {job['job_id']} for account {job['account']}")
    print(f"   Stats: {tracker.get_stats()}")

    print("\n4. Worker 0 completes job as success...")
    tracker.update_job_status('video1', 'success', worker_id=0)
    print(f"   Stats: {tracker.get_stats()}")

    print("\n5. Worker 1 fails job...")
    tracker.update_job_status('video2', 'failed', worker_id=1, error='Test error')
    print(f"   Stats: {tracker.get_stats()}")

    print("\n6. Worker 0 claims another job...")
    job = tracker.claim_next_job(worker_id=0)
    if job:
        print(f"   Claimed: {job['job_id']}")
    else:
        print("   No more pending jobs!")
    print(f"   Stats: {tracker.get_stats()}")

    print("\n7. Checking worker stats...")
    print(f"   {tracker.get_worker_stats()}")

    print("\n8. Cleanup test file...")
    os.remove(test_file)
    if os.path.exists(test_file + '.lock'):
        os.remove(test_file + '.lock')
    print("   Done!")
