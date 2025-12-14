"""
Retry Pass Manager - Orchestrates multi-pass retry logic for parallel posting.

This module implements the core retry loop logic:
1. First pass: Run all pending jobs across workers
2. After pass: Categorize failures into account vs infrastructure
3. Retry passes: Only retry infrastructure failures
4. Repeat until done or max passes reached

Pass Flow:
    PASS 1: Try all pending jobs
              ↓
          CATEGORIZE FAILURES
              ↓
          account broken? → mark failed forever
          infrastructure hiccup? → queue for retry
              ↓
    PASS 2: Retry infrastructure failures only
              ↓
          REPEAT until:
            - All jobs succeeded, OR
            - Only non-retryable remain, OR
            - Max passes reached

Usage:
    from retry_manager import RetryPassManager, RetryConfig
    from progress_tracker import ProgressTracker

    tracker = ProgressTracker("progress.csv")
    config = RetryConfig(max_passes=3, retry_delay_seconds=30)
    retry_mgr = RetryPassManager(tracker, config)

    result = PassResult.RETRYABLE_REMAINING
    while result == PassResult.RETRYABLE_REMAINING:
        retry_mgr.start_new_pass()
        # ... run workers ...
        result = retry_mgr.end_pass()
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Optional, Any

from progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)


class PassResult(Enum):
    """Result of a retry pass, determines what to do next."""
    ALL_COMPLETE = "all_complete"  # All jobs succeeded
    ONLY_NON_RETRYABLE = "only_non_retryable"  # Only account issues remain
    MAX_PASSES_REACHED = "max_passes_reached"  # Hit max retry attempts
    RETRYABLE_REMAINING = "retryable_remaining"  # Infrastructure failures to retry


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_passes: int = 3  # Maximum number of retry passes
    retry_delay_seconds: int = 30  # Delay between passes
    infrastructure_retry_limit: int = 3  # Max retries per job for infra errors
    unknown_error_is_retryable: bool = True  # Treat unclassified errors as retryable


@dataclass
class PassStats:
    """Statistics for a single pass."""
    pass_number: int
    total_jobs: int
    succeeded: int = 0
    failed_account: int = 0  # Non-retryable (account issues)
    failed_infrastructure: int = 0  # Retryable
    failed_unknown: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_jobs == 0:
            return 0.0
        return self.succeeded / self.total_jobs * 100

    @property
    def duration(self) -> Optional[timedelta]:
        """Get pass duration."""
        if self.end_time:
            return self.end_time - self.start_time
        return None


class RetryPassManager:
    """
    Manages multi-pass retry logic for job processing.

    Key responsibilities:
    1. Track which pass we're on
    2. Categorize failures after each pass
    3. Determine which jobs should be retried
    4. Decide when to stop retrying

    The manager separates "what went wrong" (classification) from
    "what to do about it" (retry policy), allowing flexible error handling.
    """

    def __init__(
        self,
        tracker: ProgressTracker,
        config: RetryConfig = None
    ):
        """
        Initialize the retry manager.

        Args:
            tracker: ProgressTracker instance for reading/updating jobs
            config: RetryConfig for retry behavior (uses defaults if None)
        """
        self.tracker = tracker
        self.config = config or RetryConfig()
        self.current_pass = 0
        self.pass_history: List[PassStats] = []

    def start_new_pass(self) -> int:
        """
        Start a new retry pass.

        For pass 1: Processes all pending jobs
        For pass 2+: Only processes retryable failures from previous pass

        Returns:
            Pass number (1-indexed)
        """
        self.current_pass += 1

        logger.info("=" * 60)
        logger.info(f"STARTING PASS {self.current_pass}")
        logger.info("=" * 60)

        # Get jobs for this pass
        if self.current_pass == 1:
            jobs = self._get_pending_jobs()
        else:
            jobs = self._get_retryable_failed_jobs()

        stats = PassStats(
            pass_number=self.current_pass,
            total_jobs=len(jobs),
            start_time=datetime.now()
        )
        self.pass_history.append(stats)

        logger.info(f"Pass {self.current_pass}: {len(jobs)} jobs to process")
        return self.current_pass

    def end_pass(self) -> PassResult:
        """
        End current pass, categorize failures, and determine next action.

        This method:
        1. Gathers stats from the tracker
        2. Counts successes and categorizes failures
        3. Logs a pass summary
        4. Decides whether to continue retrying

        Returns:
            PassResult indicating what should happen next
        """
        if not self.pass_history:
            return PassResult.ALL_COMPLETE

        stats = self.pass_history[-1]
        stats.end_time = datetime.now()

        # Gather stats from tracker
        tracker_stats = self.tracker.get_stats()
        failure_stats = self.tracker.get_failure_stats()

        stats.succeeded = tracker_stats['success']
        stats.failed_account = failure_stats['account_failures']
        stats.failed_infrastructure = failure_stats['infrastructure_failures']
        stats.failed_unknown = failure_stats['unknown_failures']

        # Log pass summary
        logger.info("=" * 60)
        logger.info(f"PASS {self.current_pass} COMPLETE")
        logger.info(f"  Succeeded: {stats.succeeded}")
        logger.info(f"  Failed (account issues): {stats.failed_account}")
        logger.info(f"  Failed (infrastructure): {stats.failed_infrastructure}")
        logger.info(f"  Failed (unknown): {stats.failed_unknown}")
        logger.info(f"  Duration: {stats.duration}")
        logger.info("=" * 60)

        # Determine what to do next
        retryable_count = stats.failed_infrastructure
        if self.config.unknown_error_is_retryable:
            retryable_count += stats.failed_unknown

        # Check remaining pending/retrying jobs
        pending_remaining = tracker_stats['pending'] + tracker_stats['retrying']

        if pending_remaining > 0:
            # Still have jobs to process - shouldn't happen normally
            logger.warning(f"Pass ended with {pending_remaining} pending/retrying jobs")
            return PassResult.RETRYABLE_REMAINING

        if retryable_count == 0:
            if stats.failed_account > 0:
                logger.info("Only non-retryable failures remain - stopping")
                return PassResult.ONLY_NON_RETRYABLE
            else:
                logger.info("All jobs complete!")
                return PassResult.ALL_COMPLETE

        if self.current_pass >= self.config.max_passes:
            logger.warning(f"Max passes ({self.config.max_passes}) reached - stopping")
            return PassResult.MAX_PASSES_REACHED

        # Reset retryable jobs for next pass
        reset_count = self._reset_retryable_jobs_for_retry()
        logger.info(f"Reset {reset_count} jobs for retry pass {self.current_pass + 1}")

        return PassResult.RETRYABLE_REMAINING

    def _get_pending_jobs(self) -> List[Dict[str, Any]]:
        """Get all pending jobs for first pass."""
        jobs = self.tracker._read_all_jobs()
        return [j for j in jobs if j.get('status') == self.tracker.STATUS_PENDING]

    def _get_retryable_failed_jobs(self) -> List[Dict[str, Any]]:
        """
        Get jobs that failed with retryable errors.

        Filters to jobs where:
        - Status is 'failed'
        - Error category is 'infrastructure' or 'unknown' (not 'account')
        - Attempts haven't exceeded infrastructure_retry_limit
        """
        jobs = self.tracker._read_all_jobs()
        retryable = []

        for job in jobs:
            if job.get('status') != self.tracker.STATUS_FAILED:
                continue

            category = job.get('error_category', 'unknown') or 'unknown'
            attempts = int(job.get('attempts', 0) or 0)

            # Never retry account issues
            if category in self.tracker.NON_RETRYABLE_CATEGORIES:
                continue

            # Check retry limits
            if category == 'infrastructure':
                if attempts < self.config.infrastructure_retry_limit:
                    retryable.append(job)
            elif self.config.unknown_error_is_retryable:
                # Unknown errors get limited retries
                if attempts < 2:
                    retryable.append(job)

        return retryable

    def _reset_retryable_jobs_for_retry(self) -> int:
        """
        Reset retryable failed jobs to pending for next pass.

        Returns:
            Number of jobs reset
        """
        def _reset_operation(jobs):
            reset_count = 0
            next_pass = self.current_pass + 1

            for job in jobs:
                if job.get('status') != self.tracker.STATUS_FAILED:
                    continue

                category = job.get('error_category', 'unknown') or 'unknown'
                attempts = int(job.get('attempts', 0) or 0)

                should_retry = False
                if category == 'infrastructure':
                    should_retry = attempts < self.config.infrastructure_retry_limit
                elif category == 'unknown' and self.config.unknown_error_is_retryable:
                    should_retry = attempts < 2
                # 'account' category is never retried

                if should_retry:
                    job['status'] = self.tracker.STATUS_PENDING
                    job['pass_number'] = str(next_pass)
                    job['worker_id'] = ''
                    job['claimed_at'] = ''
                    reset_count += 1

            return jobs, reset_count

        return self.tracker._locked_operation(_reset_operation)

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of all passes.

        Returns:
            Dict with total_passes and per-pass statistics
        """
        return {
            'total_passes': len(self.pass_history),
            'current_pass': self.current_pass,
            'config': {
                'max_passes': self.config.max_passes,
                'retry_delay_seconds': self.config.retry_delay_seconds,
                'infrastructure_retry_limit': self.config.infrastructure_retry_limit,
                'unknown_error_is_retryable': self.config.unknown_error_is_retryable
            },
            'passes': [
                {
                    'pass_number': s.pass_number,
                    'total_jobs': s.total_jobs,
                    'succeeded': s.succeeded,
                    'failed_account': s.failed_account,
                    'failed_infrastructure': s.failed_infrastructure,
                    'failed_unknown': s.failed_unknown,
                    'success_rate': f"{s.success_rate:.1f}%",
                    'duration': str(s.duration) if s.duration else 'in_progress'
                }
                for s in self.pass_history
            ]
        }

    def get_final_stats(self) -> Dict[str, Any]:
        """
        Get final statistics after all passes are complete.

        Returns:
            Dict with final job counts and pass summary
        """
        tracker_stats = self.tracker.get_stats()
        failure_stats = self.tracker.get_failure_stats()

        return {
            'total_jobs': tracker_stats['total'],
            'success': tracker_stats['success'],
            'failed': tracker_stats['failed'],
            'failed_account': failure_stats['account_failures'],
            'failed_infrastructure': failure_stats['infrastructure_failures'],
            'failed_unknown': failure_stats['unknown_failures'],
            'pending': tracker_stats['pending'],
            'retrying': tracker_stats['retrying'],
            'total_passes': len(self.pass_history),
            'summary': self.get_summary()
        }


if __name__ == "__main__":
    # Demo/test
    import os
    import tempfile

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    print("\n=== RetryPassManager Demo ===\n")

    # Create test progress file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        test_file = f.name

    try:
        tracker = ProgressTracker(test_file)
        config = RetryConfig(max_passes=3, retry_delay_seconds=5)
        manager = RetryPassManager(tracker, config)

        # Seed test jobs
        test_jobs = [
            {'job_id': 'v1', 'account': 'acc1', 'video_path': '/v1.mp4', 'caption': 'Test 1'},
            {'job_id': 'v2', 'account': 'acc2', 'video_path': '/v2.mp4', 'caption': 'Test 2'},
            {'job_id': 'v3', 'account': 'acc3', 'video_path': '/v3.mp4', 'caption': 'Test 3'},
        ]
        tracker.seed_from_jobs(test_jobs)

        print("1. Starting pass 1...")
        pass_num = manager.start_new_pass()
        print(f"   Pass {pass_num} started with {len(manager._get_pending_jobs())} jobs")

        print("\n2. Simulating job results...")
        tracker.update_job_status('v1', 'success', worker_id=0)
        tracker.update_job_status('v2', 'failed', worker_id=0, error='Account suspended')
        tracker.update_job_status('v3', 'failed', worker_id=0, error='ADB timeout')

        print("\n3. Ending pass 1...")
        result = manager.end_pass()
        print(f"   Result: {result.value}")

        print("\n4. Summary:")
        summary = manager.get_summary()
        for pass_info in summary['passes']:
            print(f"   Pass {pass_info['pass_number']}: {pass_info['succeeded']} success, "
                  f"{pass_info['failed_account']} account, {pass_info['failed_infrastructure']} infra")

        print("\n5. Final stats:")
        final = manager.get_final_stats()
        print(f"   Success: {final['success']}, Failed: {final['failed']}")
        print(f"   - Account failures: {final['failed_account']}")
        print(f"   - Infrastructure failures: {final['failed_infrastructure']}")

    finally:
        # Cleanup
        os.unlink(test_file)
        lock_file = test_file + '.lock'
        if os.path.exists(lock_file):
            os.unlink(lock_file)

    print("\n=== Demo Complete ===")
