"""
Follow Worker Process for Multi-Appium Following.

Mirrors parallel_worker.py for posting.

This module implements a single worker process that:
1. Starts its own dedicated Appium server
2. Claims and processes follow jobs from the shared progress tracker
3. Uses SmartInstagramFollower for actual following
4. Handles clean shutdown on signals

Usage (typically called by follow_orchestrator):
    python follow_worker.py --worker-id 0 --num-workers 3 --campaign podcast
"""

import os
import sys
import time
import signal
import logging
import argparse
import traceback
import json
from datetime import datetime
from typing import Optional, Tuple
from urllib.request import Request, urlopen

# Import centralized config and set up environment FIRST
from config import Config, CampaignConfig, setup_environment
setup_environment()

# Import parallel config for worker configuration
from parallel_config import ParallelConfig, WorkerConfig, get_config
# Import Appium server manager - don't modify
from appium_server_manager import AppiumServerManager, AppiumServerError
# Import follow-specific modules
from follow_tracker import FollowTracker
from follow_single import SmartInstagramFollower
# Import Geelark client for phone management
from geelark_client import GeelarkClient

# Global flag for clean shutdown
_shutdown_requested = False


def setup_signal_handlers():
    """Set up signal handlers for clean shutdown."""
    global _shutdown_requested

    def handle_signal(signum, frame):
        global _shutdown_requested
        _shutdown_requested = True
        logging.info(f"Received signal {signum}, requesting shutdown...")

    if sys.platform == 'win32':
        signal.signal(signal.SIGBREAK, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)


def setup_worker_logging(worker_config: WorkerConfig, campaign: str) -> logging.Logger:
    """Set up logging for this worker.

    Mirrors parallel_worker.py logging setup.
    """
    log_dir = f"campaigns/{campaign}/logs"
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"follow_worker_{worker_config.worker_id}.log")

    logger = logging.getLogger(f"follow_worker_{worker_config.worker_id}")
    logger.setLevel(logging.INFO)

    # Clear existing handlers
    logger.handlers = []

    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(logging.Formatter(
        f'%(asctime)s [FW{worker_config.worker_id}] %(levelname)s %(message)s'
    ))
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(
        f'%(asctime)s [FollowWorker {worker_config.worker_id}] %(levelname)s %(message)s'
    ))
    logger.addHandler(ch)

    return logger


def kill_appium_sessions(appium_url: str, logger: logging.Logger) -> None:
    """Kill any existing sessions on this Appium server to prevent orphaned sessions.

    Copied from parallel_worker.py - don't modify the source.
    """
    try:
        # Get all sessions
        req = Request(f"{appium_url}/sessions", method='GET')
        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            sessions = data.get('value', [])

            for session in sessions:
                session_id = session.get('id')
                if session_id:
                    try:
                        # Delete this session
                        del_req = Request(
                            f"{appium_url}/session/{session_id}",
                            method='DELETE'
                        )
                        urlopen(del_req, timeout=5)
                        logger.info(f"Killed orphaned Appium session: {session_id[:8]}...")
                    except Exception as e:
                        logger.debug(f"Failed to kill session {session_id[:8]}: {e}")
    except Exception as e:
        logger.debug(f"Could not check Appium sessions: {e}")


def stop_phone_by_name(phone_name: str, logger: logging.Logger) -> bool:
    """Stop a phone by its name.

    Copied from parallel_worker.py - don't modify the source.
    """
    try:
        client = GeelarkClient()
        result = client.list_phones(page_size=100)
        for phone in result.get('items', []):
            if phone.get('serialName') == phone_name and phone.get('status') != 0:  # 0=stopped, 1=starting, 2=running
                client.stop_phone(phone['id'])
                logger.info(f"Stopped phone: {phone_name}")
                return True
        return False
    except Exception as e:
        logger.warning(f"Error stopping phone {phone_name}: {e}")
        return False


def execute_follow_job(
    job: dict,
    worker_config: WorkerConfig,
    config: ParallelConfig,
    logger: logging.Logger,
    tracker: Optional[FollowTracker] = None,
    worker_id: Optional[int] = None
) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Execute a single follow job.

    Mirrors execute_posting_job from parallel_worker.py.

    Args:
        job: Job dict with account, target, job_id
        worker_config: Worker configuration
        config: Parallel configuration
        logger: Logger instance
        tracker: Optional tracker for job verification
        worker_id: Worker ID for verification

    Returns:
        Tuple: (success, error_message, error_category, error_type)
    """
    account = job['account']
    target = job['target']
    job_id = job['job_id']

    logger.info(f"Starting follow job: {account} -> @{target}")

    # Kill any orphaned Appium sessions before starting
    kill_appium_sessions(worker_config.appium_url, logger)

    # Verify job is still valid (if tracker provided)
    if tracker and worker_id is not None:
        is_valid, error = tracker.verify_job_before_follow(job_id, worker_id)
        if not is_valid:
            logger.warning(f"Job verification failed: {error}")
            return False, error or "Job verification failed", 'infrastructure', 'verification_failed'

    follower = None
    try:
        # Create follower with this worker's Appium URL and systemPort
        # NOTE: use_hybrid=True enables rule-based navigation (100% coverage validated Dec 2024)
        # Set use_hybrid=False for AI-only mode if needed for debugging
        follower = SmartInstagramFollower(
            phone_name=account,
            system_port=worker_config.system_port,
            appium_url=worker_config.appium_url,
            use_hybrid=True  # Hybrid mode: rule-based + AI fallback
        )

        # Connect to device (same pattern as posting)
        logger.info(f"Connecting to device via {worker_config.appium_url}...")
        follower.connect()

        # Execute the follow
        success = follower.follow_account(target)

        if success:
            logger.info(f"Successfully followed @{target}")
            return True, "", None, None
        else:
            error = follower.last_error_message or "Follow returned False"
            error_type = follower.last_error_type or "unknown"
            logger.error(f"Failed to follow @{target}: {error}")

            # Classify error
            error_lower = error.lower()
            if any(x in error_lower for x in ['action blocked', 'try again later', 'temporarily blocked']):
                return False, error, 'account', 'action_blocked'
            elif any(x in error_lower for x in ['logged out', 'log in']):
                return False, error, 'account', 'logged_out'
            elif any(x in error_lower for x in ['captcha', 'confirm it']):
                return False, error, 'account', 'captcha'
            elif any(x in error_lower for x in ['suspended', 'disabled']):
                return False, error, 'account', 'suspended'
            elif any(x in error_lower for x in ['verification', 'verify']):
                return False, error, 'account', 'verification'
            elif any(x in error_lower for x in ['max steps', 'stuck']):
                return False, error, 'infrastructure', 'claude_stuck'
            else:
                return False, error, 'infrastructure', error_type

    except TimeoutError as e:
        error_msg = f"TimeoutError: {str(e)}"
        logger.error(f"Follow timeout: {error_msg}")
        return False, error_msg, 'infrastructure', 'adb_timeout'

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Follow exception: {error_msg}")
        logger.debug(traceback.format_exc())
        return False, error_msg, 'infrastructure', 'unknown'

    finally:
        # Always clean up
        try:
            if follower:
                follower.cleanup()
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")

        # Always stop the phone
        stop_phone_by_name(account, logger)


def run_worker(
    worker_id: int,
    config: ParallelConfig,
    campaign: str,
    progress_file: str,
    followed_file: str,
    max_follows_per_account: int = 1,
    delay_between_jobs: int = 10
) -> dict:
    """
    Main worker loop.

    Mirrors parallel_worker.run_worker.

    Args:
        worker_id: Worker ID (0-indexed)
        config: Parallel configuration
        campaign: Campaign name
        progress_file: Path to follow_progress.csv
        followed_file: Path to all_followed_accounts.txt
        max_follows_per_account: Max follows per account per day
        delay_between_jobs: Seconds to wait between jobs

    Returns:
        Dict with worker stats
    """
    global _shutdown_requested

    worker_config = config.get_worker(worker_id)
    logger = setup_worker_logging(worker_config, campaign)

    logger.info("=" * 60)
    logger.info(f"FOLLOW WORKER {worker_id} STARTING")
    logger.info(f"  Campaign: {campaign}")
    logger.info(f"  Appium port: {worker_config.appium_port}")
    logger.info(f"  System port: {worker_config.system_port}")
    logger.info(f"  Progress file: {progress_file}")
    logger.info(f"  Max follows/account: {max_follows_per_account}")
    logger.info("=" * 60)

    # Stats tracking
    stats = {
        'worker_id': worker_id,
        'follows_completed': 0,
        'follows_failed': 0,
        'start_time': datetime.now().isoformat(),
        'end_time': None,
        'exit_reason': None
    }

    # Initialize progress tracker
    tracker = FollowTracker(progress_file, followed_file)

    # Start Appium server
    appium_manager = AppiumServerManager(worker_config, config)

    try:
        logger.info("Starting Appium server...")
        appium_manager.start(timeout=60)
        logger.info(f"Appium ready at {worker_config.appium_url}")

    except AppiumServerError as e:
        logger.error(f"Failed to start Appium: {e}")
        stats['exit_reason'] = f"Appium start failed: {e}"
        return stats

    try:
        # Main job processing loop
        while not _shutdown_requested:
            # Check if there are any remaining jobs
            progress_stats = tracker.get_stats()
            remaining = progress_stats['pending'] + progress_stats['retrying']
            claimed = progress_stats['claimed']

            if remaining == 0 and claimed == 0:
                logger.info("No more follow jobs to process, exiting")
                stats['exit_reason'] = "all_jobs_complete"
                break

            # Ensure Appium is healthy
            try:
                appium_manager.ensure_healthy()
            except AppiumServerError as e:
                logger.error(f"Appium health check failed: {e}")
                stats['exit_reason'] = f"Appium unhealthy: {e}"
                break

            # Release stale claims
            released = tracker.release_stale_claims(max_age_seconds=600)
            if released > 0:
                logger.info(f"Released {released} stale job claims")

            # Claim a job
            job = tracker.claim_next_job(worker_id, max_follows_per_account)

            if job is None:
                # No jobs available right now
                if claimed > 0:
                    # Other workers have jobs, wait for them
                    logger.debug("Waiting for jobs...")
                    time.sleep(5)
                    continue
                else:
                    # No jobs anywhere
                    logger.info("No more jobs, exiting")
                    stats['exit_reason'] = "all_jobs_complete"
                    break

            # Execute the job
            job_id = job['job_id']
            logger.info(f"Processing follow job: {job['account']} -> @{job['target']}")

            try:
                success, error, error_category, error_type = execute_follow_job(
                    job, worker_config, config, logger,
                    tracker=tracker, worker_id=worker_id
                )

                if success:
                    tracker.update_job_status(job_id, 'success', worker_id)
                    stats['follows_completed'] += 1
                    logger.info(f"Job {job_id} completed successfully")
                else:
                    tracker.update_job_status(
                        job_id, 'failed', worker_id, error=error,
                        retry_delay_minutes=5
                    )
                    stats['follows_failed'] += 1
                    logger.info(f"Job {job_id} failed: {error_category}/{error_type}")

            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.error(f"Unhandled exception: {error_msg}")
                tracker.update_job_status(
                    job_id, 'failed', worker_id, error=error_msg,
                    retry_delay_minutes=5
                )
                stats['follows_failed'] += 1

            # Delay before next job
            if not _shutdown_requested and delay_between_jobs > 0:
                logger.info(f"Waiting {delay_between_jobs}s before next job...")
                time.sleep(delay_between_jobs)

        if _shutdown_requested:
            stats['exit_reason'] = "shutdown_requested"
            logger.info("Shutdown requested")

    finally:
        # Clean shutdown
        logger.info("Cleaning up...")

        try:
            appium_manager.stop()
        except Exception as e:
            logger.warning(f"Error stopping Appium: {e}")

        stats['end_time'] = datetime.now().isoformat()

        logger.info("=" * 60)
        logger.info(f"FOLLOW WORKER {worker_id} FINISHED")
        logger.info(f"  Follows completed: {stats['follows_completed']}")
        logger.info(f"  Follows failed: {stats['follows_failed']}")
        logger.info(f"  Exit reason: {stats['exit_reason']}")
        logger.info("=" * 60)

    return stats


def main():
    """CLI entry point for worker process."""
    parser = argparse.ArgumentParser(description='Follow Worker')
    parser.add_argument('--worker-id', type=int, required=True,
                       help='Worker ID (0-indexed)')
    parser.add_argument('--num-workers', type=int, default=3,
                       help='Total number of workers')
    parser.add_argument('--campaign', required=True,
                       help='Campaign name')
    parser.add_argument('--progress-file', required=True,
                       help='Progress CSV file')
    parser.add_argument('--followed-file', default='all_followed_accounts.txt',
                       help='Followed accounts file')
    parser.add_argument('--max-follows', type=int, default=1,
                       help='Max follows per account per day')
    parser.add_argument('--delay', type=int, default=10,
                       help='Delay between jobs in seconds')

    args = parser.parse_args()

    # Set up signal handlers
    setup_signal_handlers()

    # Create config
    config = get_config(num_workers=args.num_workers)

    # Run worker
    stats = run_worker(
        worker_id=args.worker_id,
        config=config,
        campaign=args.campaign,
        progress_file=args.progress_file,
        followed_file=args.followed_file,
        max_follows_per_account=args.max_follows,
        delay_between_jobs=args.delay
    )

    # Exit with appropriate code
    if stats.get('exit_reason') == 'all_jobs_complete':
        sys.exit(0)
    elif stats.get('follows_failed', 0) > 0 and stats.get('follows_completed', 0) == 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
