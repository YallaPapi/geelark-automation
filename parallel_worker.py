"""
Parallel Worker Process for Multi-Appium Posting.

This module implements a single worker process that:
1. Starts its own dedicated Appium server
2. Claims and processes jobs from the shared progress tracker
3. Uses the existing SmartInstagramPoster for actual posting
4. Handles clean shutdown on signals

Each worker is completely isolated - its own Appium server, own systemPort,
own log file. Workers only communicate via the file-locked progress CSV.

Usage (typically called by orchestrator):
    python parallel_worker.py --worker-id 0 --num-workers 3

Or programmatically:
    from parallel_worker import run_worker
    run_worker(worker_id=0, config=parallel_config)
"""

import os
import sys
import time
import signal
import logging
import argparse
import traceback
from datetime import datetime
from typing import Optional

# Set ANDROID_HOME early
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'
os.environ['ANDROID_SDK_ROOT'] = r'C:\Users\asus\Downloads\android-sdk'

from parallel_config import ParallelConfig, WorkerConfig, get_config
from appium_server_manager import AppiumServerManager, AppiumServerError
from progress_tracker import ProgressTracker
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


def setup_worker_logging(worker_config: WorkerConfig) -> logging.Logger:
    """Set up logging for this worker."""
    # Create logs directory
    os.makedirs(os.path.dirname(worker_config.log_file) or '.', exist_ok=True)

    # Create worker-specific logger
    logger = logging.getLogger(f"worker_{worker_config.worker_id}")
    logger.setLevel(logging.INFO)

    # File handler
    fh = logging.FileHandler(worker_config.log_file, encoding='utf-8')
    fh.setFormatter(logging.Formatter(
        f'%(asctime)s [W{worker_config.worker_id}] %(levelname)s %(message)s'
    ))
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(
        f'%(asctime)s [Worker {worker_config.worker_id}] %(levelname)s %(message)s'
    ))
    logger.addHandler(ch)

    return logger


def stop_phone_by_name(phone_name: str, logger: logging.Logger) -> bool:
    """Stop a phone by its name."""
    try:
        client = GeelarkClient()
        result = client.list_phones(page_size=100)
        for phone in result.get('items', []):
            if phone.get('serialName') == phone_name and phone.get('status') == 1:
                client.stop_phone(phone['id'])
                logger.info(f"Stopped phone: {phone_name}")
                return True
        return False
    except Exception as e:
        logger.warning(f"Error stopping phone {phone_name}: {e}")
        return False


def kill_appium_sessions(appium_url: str, logger: logging.Logger):
    """Kill any existing sessions on this Appium server to prevent orphaned sessions."""
    import urllib.request
    import json

    try:
        # Get all sessions
        req = urllib.request.Request(f"{appium_url}/sessions", method='GET')
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            sessions = data.get('value', [])

            for session in sessions:
                session_id = session.get('id')
                if session_id:
                    try:
                        # Delete this session
                        del_req = urllib.request.Request(
                            f"{appium_url}/session/{session_id}",
                            method='DELETE'
                        )
                        urllib.request.urlopen(del_req, timeout=5)
                        logger.info(f"Killed orphaned Appium session: {session_id[:8]}...")
                    except Exception as e:
                        logger.debug(f"Failed to kill session {session_id[:8]}: {e}")
    except Exception as e:
        logger.debug(f"Could not check Appium sessions: {e}")


def execute_posting_job(
    job: dict,
    worker_config: WorkerConfig,
    config: ParallelConfig,
    logger: logging.Logger,
    tracker=None,
    worker_id: int = None
) -> tuple:
    """
    Execute a single posting job.

    Args:
        job: Job dict from progress tracker
        worker_config: This worker's configuration
        config: Overall parallel config
        logger: Logger instance
        tracker: ProgressTracker instance for verification
        worker_id: Worker ID for verification

    Returns:
        (success: bool, error_message: str)
    """
    # Import here to avoid circular imports and ensure ANDROID_HOME is set
    from post_reel_smart import SmartInstagramPoster

    account = job['account']
    video_path = job['video_path']
    caption = job['caption']
    job_id = job['job_id']

    # Kill any orphaned Appium sessions before starting (prevents session limit issues)
    kill_appium_sessions(worker_config.appium_url, logger)

    # SAFETY CHECK: Verify job is still valid before posting (prevents duplicates)
    if tracker and worker_id is not None:
        is_valid, error = tracker.verify_job_before_post(job_id, worker_id)
        if not is_valid:
            logger.warning(f"Job {job_id} failed pre-post verification: {error}")
            return False, f"Pre-post verification failed: {error}"

    logger.info(f"Starting job {job_id}: posting to {account}")
    logger.info(f"  Video: {video_path}")
    logger.info(f"  Caption: {caption[:50]}...")

    poster = None
    try:
        # Create poster with this worker's Appium URL and systemPort
        poster = SmartInstagramPoster(
            phone_name=account,
            system_port=worker_config.system_port,
            appium_url=worker_config.appium_url
        )

        # Connect to device
        logger.info(f"Connecting to device via {worker_config.appium_url}...")
        poster.connect()

        # Post the video
        logger.info("Posting video...")
        success = poster.post(video_path, caption, humanize=True)

        if success:
            logger.info(f"Job {job_id} completed successfully!")
            return True, ""
        else:
            error = poster.last_error_message or "Post returned False"
            logger.error(f"Job {job_id} failed: {error}")
            return False, error

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Job {job_id} exception: {error_msg}")
        logger.debug(traceback.format_exc())
        return False, error_msg

    finally:
        # Always clean up
        try:
            if poster:
                poster.cleanup()
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")

        # Always stop the phone
        stop_phone_by_name(account, logger)


def run_worker(
    worker_id: int,
    config: ParallelConfig,
    progress_file: str = None,
    delay_between_jobs: int = None
) -> dict:
    """
    Main worker loop.

    Args:
        worker_id: This worker's ID
        config: Parallel configuration
        progress_file: Override progress file path
        delay_between_jobs: Override delay between jobs

    Returns:
        Dict with worker stats: {jobs_completed, jobs_failed, ...}
    """
    global _shutdown_requested

    worker_config = config.get_worker(worker_id)
    logger = setup_worker_logging(worker_config)

    progress_file = progress_file or config.progress_file
    delay = delay_between_jobs if delay_between_jobs is not None else config.delay_between_jobs

    logger.info("="*60)
    logger.info(f"WORKER {worker_id} STARTING")
    logger.info(f"  Appium port: {worker_config.appium_port}")
    logger.info(f"  Appium URL: {worker_config.appium_url}")
    logger.info(f"  systemPort: {worker_config.system_port}")
    logger.info(f"  Progress file: {progress_file}")
    logger.info("="*60)

    # Stats tracking
    stats = {
        'worker_id': worker_id,
        'jobs_completed': 0,
        'jobs_failed': 0,
        'start_time': datetime.now().isoformat(),
        'end_time': None,
        'exit_reason': None
    }

    # Initialize progress tracker
    tracker = ProgressTracker(progress_file)

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
            if progress_stats['pending'] == 0 and progress_stats['claimed'] == 0:
                logger.info("No more jobs to process, exiting")
                stats['exit_reason'] = "all_jobs_complete"
                break

            # Ensure Appium is healthy before each job
            # This will reuse existing healthy servers or restart if needed
            try:
                appium_manager.ensure_healthy()
            except AppiumServerError as e:
                logger.error(f"Appium health check failed: {e}")
                stats['exit_reason'] = f"Appium unhealthy: {e}"
                break

            # Release any stale claims (jobs claimed but never completed)
            released = tracker.release_stale_claims(max_age_seconds=600)
            if released > 0:
                logger.info(f"Released {released} stale job claims")

            # Try to claim a job (with defense-in-depth daily limit check)
            job = tracker.claim_next_job(worker_id, max_posts_per_account_per_day=config.max_posts_per_account_per_day)

            if job is None:
                # No pending jobs, but some might be claimed by other workers
                if progress_stats['claimed'] > 0:
                    logger.debug("Waiting for claimed jobs to complete...")
                    time.sleep(5)
                    continue
                else:
                    logger.info("No more jobs, exiting")
                    stats['exit_reason'] = "all_jobs_complete"
                    break

            # Execute the job
            job_id = job['job_id']
            try:
                success, error = execute_posting_job(
                    job, worker_config, config, logger,
                    tracker=tracker, worker_id=worker_id
                )

                if success:
                    tracker.update_job_status(job_id, 'success', worker_id)
                    stats['jobs_completed'] += 1
                else:
                    tracker.update_job_status(job_id, 'failed', worker_id, error=error)
                    stats['jobs_failed'] += 1

            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.error(f"Unhandled exception processing job {job_id}: {error_msg}")
                tracker.update_job_status(job_id, 'failed', worker_id, error=error_msg)
                stats['jobs_failed'] += 1

            # Delay before next job
            if not _shutdown_requested and delay > 0:
                logger.info(f"Waiting {delay}s before next job...")
                time.sleep(delay)

        if _shutdown_requested:
            stats['exit_reason'] = "shutdown_requested"
            logger.info("Shutdown requested, stopping worker")

    finally:
        # Clean shutdown
        logger.info("Cleaning up...")

        # Stop Appium server
        try:
            appium_manager.stop()
        except Exception as e:
            logger.warning(f"Error stopping Appium: {e}")

        stats['end_time'] = datetime.now().isoformat()

        logger.info("="*60)
        logger.info(f"WORKER {worker_id} FINISHED")
        logger.info(f"  Jobs completed: {stats['jobs_completed']}")
        logger.info(f"  Jobs failed: {stats['jobs_failed']}")
        logger.info(f"  Exit reason: {stats['exit_reason']}")
        logger.info("="*60)

    return stats


def main():
    """CLI entry point for worker process."""
    parser = argparse.ArgumentParser(description='Parallel Posting Worker')
    parser.add_argument('--worker-id', type=int, required=True, help='Worker ID (0-indexed)')
    parser.add_argument('--num-workers', type=int, default=3, help='Total number of workers')
    parser.add_argument('--progress-file', default='parallel_progress.csv', help='Progress CSV file')
    parser.add_argument('--delay', type=int, default=10, help='Delay between jobs in seconds')

    args = parser.parse_args()

    # Set up signal handlers
    setup_signal_handlers()

    # Create config
    config = get_config(num_workers=args.num_workers)

    # Run worker
    stats = run_worker(
        worker_id=args.worker_id,
        config=config,
        progress_file=args.progress_file,
        delay_between_jobs=args.delay
    )

    # Exit with appropriate code
    if stats.get('exit_reason') == 'all_jobs_complete':
        sys.exit(0)
    elif stats.get('jobs_failed', 0) > 0 and stats.get('jobs_completed', 0) == 0:
        sys.exit(1)  # All jobs failed
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
