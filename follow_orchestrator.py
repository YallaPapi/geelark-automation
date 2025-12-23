"""
Follow Orchestrator - Coordinates parallel follow workers.

Mirrors parallel_orchestrator.py for posting.

Usage:
    python follow_orchestrator.py --campaign podcast --workers 5 --max-follows 2 --run
    python follow_orchestrator.py --campaign podcast --status
    python follow_orchestrator.py --campaign podcast --reset
"""

import os
import sys
import time
import signal
import logging
import argparse
import subprocess
from datetime import datetime
from typing import List, Optional, Dict, Any

# Import centralized config and set up environment FIRST
from config import Config, CampaignConfig, setup_environment
setup_environment()

# Import parallel config for worker configuration
from parallel_config import ParallelConfig, get_config
# Import follow tracker
from follow_tracker import FollowTracker
# Import Geelark client for stopping phones
from geelark_client import GeelarkClient

# Global flag for clean shutdown
_shutdown_requested = False
_worker_processes: List[subprocess.Popen] = []

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [Orchestrator] %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)


def setup_signal_handlers():
    """Set up signal handlers for clean shutdown."""
    global _shutdown_requested

    def handle_signal(signum, frame):
        global _shutdown_requested
        _shutdown_requested = True
        logger.info(f"Received signal {signum}, initiating shutdown...")
        stop_all_workers()

    if sys.platform == 'win32':
        signal.signal(signal.SIGBREAK, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)


def stop_all_workers():
    """Stop all worker processes."""
    global _worker_processes

    for proc in _worker_processes:
        if proc.poll() is None:  # Still running
            try:
                if sys.platform == 'win32':
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate()
                logger.info(f"Terminated worker process {proc.pid}")
            except Exception as e:
                logger.warning(f"Error terminating worker {proc.pid}: {e}")

    # Wait for processes to exit
    for proc in _worker_processes:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            logger.warning(f"Force killed worker {proc.pid}")

    _worker_processes.clear()


def stop_all_phones():
    """Stop all running Geelark phones."""
    logger.info("Stopping all running phones...")
    try:
        client = GeelarkClient()
        stopped = 0
        for page in range(1, 20):
            result = client.list_phones(page=page, page_size=100)
            for phone in result.get('items', []):
                if phone.get('status') != 0:  # 0=stopped, 1=starting, 2=running  # Running
                    try:
                        client.stop_phone(phone['id'])
                        stopped += 1
                        logger.debug(f"Stopped: {phone.get('serialName')}")
                    except Exception as e:
                        logger.warning(f"Failed to stop {phone.get('serialName')}: {e}")
            if len(result.get('items', [])) < 100:
                break
        logger.info(f"Stopped {stopped} phones")
    except Exception as e:
        logger.error(f"Error stopping phones: {e}")


def load_targets(targets_file: str) -> List[str]:
    """Load target usernames from file.

    Args:
        targets_file: Path to followers.txt

    Returns:
        List of target usernames
    """
    targets = []

    if not os.path.exists(targets_file):
        logger.warning(f"Targets file not found: {targets_file}")
        return targets

    with open(targets_file, 'r', encoding='utf-8') as f:
        for line in f:
            target = line.strip().lstrip('@')
            if target and not target.startswith('#'):
                targets.append(target)

    logger.info(f"Loaded {len(targets)} targets from {targets_file}")
    return targets


def spawn_worker(
    worker_id: int,
    num_workers: int,
    campaign: str,
    progress_file: str,
    followed_file: str,
    max_follows: int,
    delay: int
) -> subprocess.Popen:
    """Spawn a worker subprocess.

    Args:
        worker_id: Worker ID (0-indexed)
        num_workers: Total number of workers
        campaign: Campaign name
        progress_file: Path to follow_progress.csv
        followed_file: Path to all_followed_accounts.txt
        max_follows: Max follows per account per day
        delay: Delay between jobs in seconds

    Returns:
        Subprocess handle
    """
    cmd = [
        sys.executable,
        'follow_worker.py',
        '--worker-id', str(worker_id),
        '--num-workers', str(num_workers),
        '--campaign', campaign,
        '--progress-file', progress_file,
        '--followed-file', followed_file,
        '--max-follows', str(max_follows),
        '--delay', str(delay),
    ]

    logger.info(f"Spawning worker {worker_id}: {' '.join(cmd)}")

    if sys.platform == 'win32':
        proc = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        proc = subprocess.Popen(
            cmd,
            start_new_session=True
        )

    return proc


def show_status(campaign: str, progress_file: str, followed_file: str):
    """Show current follow progress status.

    Args:
        campaign: Campaign name
        progress_file: Path to follow_progress.csv
        followed_file: Path to all_followed_accounts.txt
    """
    print(f"\n=== Follow Status for Campaign: {campaign} ===\n")

    # Check if progress file exists
    if not os.path.exists(progress_file):
        print(f"Progress file not found: {progress_file}")
        print("Run with --run to start following.")
        return

    # Get stats from tracker
    tracker = FollowTracker(progress_file, followed_file)
    stats = tracker.get_stats()

    print(f"Progress File: {progress_file}")
    print(f"Followed File: {followed_file}")
    print()
    print(f"Total Jobs:    {stats['total']}")
    print(f"Pending:       {stats['pending']}")
    print(f"Claimed:       {stats['claimed']}")
    print(f"Retrying:      {stats['retrying']}")
    print(f"Success:       {stats['success']}")
    print(f"Failed:        {stats['failed']}")
    print()

    if stats['total'] > 0:
        success_rate = (stats['success'] / stats['total']) * 100
        print(f"Success Rate:  {success_rate:.1f}%")

    # Count followed accounts
    if os.path.exists(followed_file):
        with open(followed_file, 'r', encoding='utf-8') as f:
            followed_count = sum(1 for line in f if line.strip())
        print(f"\nTotal Followed Accounts: {followed_count}")


def reset_progress(campaign: str, progress_file: str, followed_file: str):
    """Reset follow progress for a campaign.

    Args:
        campaign: Campaign name
        progress_file: Path to follow_progress.csv
        followed_file: Path to all_followed_accounts.txt
    """
    print(f"\n=== Resetting Follow Progress for Campaign: {campaign} ===\n")

    # Archive old progress file if it exists
    if os.path.exists(progress_file):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = progress_file.replace('.csv', f'_{timestamp}_archive.csv')
        os.rename(progress_file, archive_file)
        print(f"Archived old progress to: {archive_file}")

    # Create fresh tracker (creates empty files)
    tracker = FollowTracker(progress_file, followed_file)
    tracker.reset()
    print(f"Created fresh progress file: {progress_file}")

    # Note: we keep all_followed_accounts.txt to prevent re-following
    print(f"\nNote: {followed_file} preserved to prevent re-following")
    print("Use --reset-all to also clear followed accounts (not recommended)")


def run_orchestrator(
    campaign: str,
    num_workers: int,
    max_follows_per_account: int,
    delay_between_jobs: int,
    targets_file: str,
    progress_file: str,
    followed_file: str,
    stagger_seconds: int = 60
):
    """
    Run the follow orchestrator.

    Args:
        campaign: Campaign name
        num_workers: Number of parallel workers
        max_follows_per_account: Max follows per account per day
        delay_between_jobs: Delay between jobs in seconds
        targets_file: Path to followers.txt
        progress_file: Path to follow_progress.csv
        followed_file: Path to all_followed_accounts.txt
        stagger_seconds: Seconds between worker starts
    """
    global _shutdown_requested, _worker_processes

    logger.info("=" * 60)
    logger.info("FOLLOW ORCHESTRATOR STARTING")
    logger.info(f"  Campaign: {campaign}")
    logger.info(f"  Workers: {num_workers}")
    logger.info(f"  Max follows/account: {max_follows_per_account}")
    logger.info(f"  Delay between jobs: {delay_between_jobs}s")
    logger.info(f"  Stagger between workers: {stagger_seconds}s")
    logger.info("=" * 60)

    # Load campaign config
    campaign_folder = f"campaigns/{campaign}"
    if not os.path.exists(campaign_folder):
        logger.error(f"Campaign folder not found: {campaign_folder}")
        return

    campaign_config = CampaignConfig.from_folder(campaign_folder)
    accounts = campaign_config.get_accounts()

    if not accounts:
        logger.error(f"No accounts found in campaign: {campaign}")
        return

    logger.info(f"Found {len(accounts)} campaign accounts")

    # Load targets
    targets = load_targets(targets_file)
    if not targets:
        logger.error(f"No targets found in: {targets_file}")
        return

    # Initialize tracker
    tracker = FollowTracker(progress_file, followed_file)

    # Seed jobs if needed
    if not tracker.exists():
        logger.info("Seeding follow jobs...")
        seeded = tracker.seed_from_targets(
            targets_file, accounts, max_follows_per_account
        )
        logger.info(f"Seeded {seeded} follow jobs")
    else:
        stats = tracker.get_stats()
        remaining = stats['pending'] + stats['retrying']
        logger.info(f"Resuming with {remaining} remaining jobs")

    # Check for remaining work
    stats = tracker.get_stats()
    if stats['pending'] == 0 and stats['retrying'] == 0 and stats['claimed'] == 0:
        logger.info("No jobs to process")
        return

    # Create parallel config
    config = get_config(num_workers=num_workers)

    # Spawn workers with staggered start
    logger.info(f"Spawning {num_workers} workers...")
    for worker_id in range(num_workers):
        if _shutdown_requested:
            break

        proc = spawn_worker(
            worker_id=worker_id,
            num_workers=num_workers,
            campaign=campaign,
            progress_file=progress_file,
            followed_file=followed_file,
            max_follows=max_follows_per_account,
            delay=delay_between_jobs
        )
        _worker_processes.append(proc)
        logger.info(f"Worker {worker_id} started (PID {proc.pid})")

        # Stagger worker starts (except for last worker)
        if worker_id < num_workers - 1 and not _shutdown_requested:
            logger.info(f"Waiting {stagger_seconds}s before next worker...")
            for _ in range(stagger_seconds):
                if _shutdown_requested:
                    break
                time.sleep(1)

    # Monitor workers
    logger.info("All workers started, monitoring...")

    while not _shutdown_requested:
        # Check if any workers are still running
        running = [p for p in _worker_processes if p.poll() is None]

        if not running:
            logger.info("All workers have exited")
            break

        # Log status periodically
        stats = tracker.get_stats()
        remaining = stats['pending'] + stats['retrying']
        logger.debug(
            f"Status: {len(running)} workers running, "
            f"{remaining} jobs remaining, "
            f"{stats['success']} succeeded, {stats['failed']} failed"
        )

        time.sleep(10)

    # Clean up
    logger.info("Orchestrator shutting down...")
    stop_all_workers()
    stop_all_phones()

    # Final stats
    stats = tracker.get_stats()
    logger.info("=" * 60)
    logger.info("FOLLOW ORCHESTRATOR FINISHED")
    logger.info(f"  Success: {stats['success']}")
    logger.info(f"  Failed:  {stats['failed']}")
    logger.info(f"  Pending: {stats['pending']}")
    logger.info("=" * 60)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Follow Orchestrator - Parallel Instagram following'
    )
    parser.add_argument('--campaign', default='podcast',
                       help='Campaign name (default: podcast)')
    parser.add_argument('--workers', type=int, default=5,
                       help='Number of parallel workers (default: 5)')
    parser.add_argument('--max-follows', type=int, default=2,
                       help='Max follows per account per day (default: 2)')
    parser.add_argument('--delay', type=int, default=10,
                       help='Delay between jobs in seconds (default: 10)')
    parser.add_argument('--stagger', type=int, default=60,
                       help='Seconds between worker starts (default: 60)')

    # Action flags
    parser.add_argument('--run', action='store_true',
                       help='Run the orchestrator')
    parser.add_argument('--status', action='store_true',
                       help='Show current status')
    parser.add_argument('--reset', action='store_true',
                       help='Reset progress (archive old, create new)')
    parser.add_argument('--stop-all', action='store_true',
                       help='Stop all running phones')

    args = parser.parse_args()

    # Construct paths
    campaign_folder = f"campaigns/{args.campaign}"
    targets_file = os.path.join(campaign_folder, 'followers.txt')
    progress_file = os.path.join(campaign_folder, 'follow_progress.csv')
    followed_file = 'all_followed_accounts.txt'

    # Handle actions
    if args.stop_all:
        stop_all_phones()
        return

    if args.status:
        show_status(args.campaign, progress_file, followed_file)
        return

    if args.reset:
        reset_progress(args.campaign, progress_file, followed_file)
        return

    if args.run:
        # Set up signal handlers
        setup_signal_handlers()

        run_orchestrator(
            campaign=args.campaign,
            num_workers=args.workers,
            max_follows_per_account=args.max_follows,
            delay_between_jobs=args.delay,
            targets_file=targets_file,
            progress_file=progress_file,
            followed_file=followed_file,
            stagger_seconds=args.stagger
        )
        return

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
