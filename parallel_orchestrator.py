"""
Parallel Posting Orchestrator - Main Entry Point.

This is the main script for running parallel posting workers. It:
1. Seeds the progress file from scheduler_state.json
2. Starts N worker processes (each with its own Appium server)
3. Monitors worker processes
4. Handles clean shutdown (Ctrl+C stops all workers and phones)

Usage:
    # Start 3 parallel workers
    python parallel_orchestrator.py --workers 3 --run

    # Check status
    python parallel_orchestrator.py --status

    # Stop all (kill any running workers and phones)
    python parallel_orchestrator.py --stop-all

    # Seed progress file without running
    python parallel_orchestrator.py --seed-only

Architecture:
    Orchestrator (this script)
        │
        ├── Worker 0 (subprocess) ──► Appium:4723 ──► Device
        ├── Worker 1 (subprocess) ──► Appium:4725 ──► Device
        └── Worker 2 (subprocess) ──► Appium:4727 ──► Device

    All workers read/write to: parallel_progress.csv (file-locked)
"""

import os
import sys
import time
import signal
import socket
import subprocess
import json
import argparse
import logging
import shutil
from datetime import datetime
from typing import List, Optional, Dict, Tuple

# Import centralized config and set up environment FIRST
from config import Config, CampaignConfig, PostingContext, setup_environment
setup_environment()

from parallel_config import ParallelConfig, get_config, print_config
from progress_tracker import ProgressTracker
from appium_server_manager import cleanup_all_appium_servers, check_all_appium_servers
from geelark_client import GeelarkClient
from retry_manager import RetryPassManager, RetryConfig, PassResult


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [ORCHESTRATOR] %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
_worker_processes: List[subprocess.Popen] = []
_shutdown_requested = False
_active_config: Optional[ParallelConfig] = None
_active_campaign_accounts: Optional[List[str]] = None  # For campaign-specific cleanup


def check_for_running_orchestrators(campaign_name: str = None) -> Tuple[bool, List[str]]:
    """
    Check if other orchestrator processes are running.

    CRITICAL: This must be called BEFORE starting any workers.
    Multiple orchestrators running simultaneously for the SAME campaign
    causes race conditions and can result in duplicate posts.

    Different campaigns CAN run concurrently since they use separate
    progress files and account lists.

    Args:
        campaign_name: If specified, only conflict with orchestrators running
                      the same campaign. If None, conflict with any non-campaign
                      orchestrator.

    Returns:
        (has_conflicts: bool, list of conflicting process descriptions)
    """
    import re
    current_pid = os.getpid()
    conflicts = []

    def extract_campaign_from_cmdline(cmdline: str) -> Optional[str]:
        """Extract campaign name from command line if present."""
        # Match --campaign NAME or -c NAME
        match = re.search(r'(?:--campaign|-c)\s+(\S+)', cmdline)
        return match.group(1) if match else None

    def is_conflict(other_campaign: Optional[str]) -> bool:
        """Check if the other orchestrator conflicts with us."""
        if campaign_name is None:
            # We're non-campaign, conflict with other non-campaign
            return other_campaign is None
        else:
            # We're a campaign, only conflict with same campaign
            return other_campaign == campaign_name

    if sys.platform == 'win32':
        try:
            # Use WMIC to get command lines (tasklist doesn't show command line)
            result = subprocess.run(
                ['wmic', 'process', 'where', "name='python.exe'", 'get', 'processid,commandline'],
                capture_output=True, text=True, timeout=15
            )

            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line or 'CommandLine' in line:
                    continue

                # Check if this is an orchestrator process
                if 'parallel_orchestrator.py' in line and '--run' in line:
                    # Extract PID (last numeric part of line)
                    parts = line.split()
                    pid = None
                    for part in reversed(parts):
                        if part.isdigit():
                            pid = int(part)
                            break

                    if pid and pid != current_pid:
                        other_campaign = extract_campaign_from_cmdline(line)
                        if is_conflict(other_campaign):
                            campaign_info = f" (campaign: {other_campaign})" if other_campaign else " (no campaign)"
                            conflicts.append(f"PID {pid}: parallel_orchestrator.py --run{campaign_info}")

        except Exception as e:
            logger.warning(f"Could not check for running orchestrators: {e}")
    else:
        # Unix/Linux/Mac
        try:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True, text=True, timeout=10
            )

            for line in result.stdout.split('\n'):
                if 'parallel_orchestrator.py' in line and '--run' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        pid = int(parts[1])
                        if pid != current_pid:
                            other_campaign = extract_campaign_from_cmdline(line)
                            if is_conflict(other_campaign):
                                campaign_info = f" (campaign: {other_campaign})" if other_campaign else " (no campaign)"
                                conflicts.append(f"PID {pid}: parallel_orchestrator.py --run{campaign_info}")

        except Exception as e:
            logger.warning(f"Could not check for running orchestrators: {e}")

    return len(conflicts) > 0, conflicts


def is_port_in_use(port: int) -> Tuple[bool, Optional[str]]:
    """
    Check if a port is in use.

    Returns:
        (in_use: bool, process_info: str or None)
    """
    # First try socket check
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', port))
        if result != 0:
            return False, None

    # Port is in use - try to find what's using it
    process_info = None
    if sys.platform == 'win32':
        try:
            result = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split('\n'):
                if f':{port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    if parts:
                        pid = parts[-1]
                        # Get process name
                        name_result = subprocess.run(
                            ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                            capture_output=True, text=True, timeout=5
                        )
                        if name_result.stdout.strip():
                            process_info = f"PID {pid}: {name_result.stdout.strip().split(',')[0].strip('\"')}"
                        else:
                            process_info = f"PID {pid}"
                        break
        except Exception:
            process_info = "unknown process"
    else:
        try:
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                pid = result.stdout.strip().split('\n')[0]
                process_info = f"PID {pid}"
        except Exception:
            process_info = "unknown process"

    return True, process_info


def is_healthy_appium(port: int) -> bool:
    """Check if a healthy Appium server is running on the port."""
    try:
        from urllib.request import urlopen, Request
        from urllib.error import URLError
        import json as json_module

        url = f"http://127.0.0.1:{port}/status"
        req = Request(url, method='GET')
        with urlopen(req, timeout=3) as response:
            data = json_module.loads(response.read().decode())
            return data.get('value', {}).get('ready', False)
    except:
        return False


def check_ports_status(config: ParallelConfig) -> Tuple[List[str], List[str], List[str]]:
    """
    Check status of all required ports.

    Returns:
        (reusable_ports, blocked_ports, free_ports) - lists of status messages
    """
    reusable = []  # Ports with healthy Appium we can reuse
    blocked = []   # Ports in use by non-Appium processes
    free = []      # Ports that are free

    for worker in config.workers:
        port = worker.appium_port

        # First check if there's a healthy Appium
        if is_healthy_appium(port):
            reusable.append(f"Port {port} (Worker {worker.worker_id}): Healthy Appium - will REUSE")
        # Then check if port is in use by something else
        elif is_port_in_use(port)[0]:
            in_use, proc_info = is_port_in_use(port)
            msg = f"Port {port} (Worker {worker.worker_id}): BLOCKED"
            if proc_info:
                msg += f" by {proc_info}"
            blocked.append(msg)
        else:
            free.append(f"Port {port} (Worker {worker.worker_id}): Free - will START new Appium")

    return reusable, blocked, free


def check_all_ports_available(config: ParallelConfig) -> Tuple[bool, List[str]]:
    """
    Check if all required ports are available or reusable.

    Args:
        config: Parallel configuration

    Returns:
        (all_ok: bool, list of conflict messages)
    """
    reusable, blocked, free = check_ports_status(config)

    # Log the status
    for msg in reusable:
        logger.info(f"  {msg}")
    for msg in free:
        logger.info(f"  {msg}")
    for msg in blocked:
        logger.warning(f"  {msg}")

    # Only blocked ports are a problem
    return len(blocked) == 0, blocked


def kill_process_on_port(port: int) -> bool:
    """Kill whatever process is using a port."""
    if sys.platform == 'win32':
        try:
            result = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split('\n'):
                if f':{port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    if parts:
                        pid = parts[-1]
                        if pid.isdigit():
                            subprocess.run(['taskkill', '/F', '/PID', pid],
                                         capture_output=True, timeout=10)
                            logger.info(f"Killed process on port {port} (PID {pid})")
                            return True
        except Exception as e:
            logger.warning(f"Error killing process on port {port}: {e}")
    else:
        try:
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True, text=True, timeout=5
            )
            for pid in result.stdout.strip().split('\n'):
                if pid.isdigit():
                    subprocess.run(['kill', '-9', pid], capture_output=True)
                    logger.info(f"Killed process on port {port} (PID {pid})")
                    return True
        except Exception as e:
            logger.warning(f"Error killing process on port {port}: {e}")
    return False


def ensure_ports_available(config: ParallelConfig, force_kill: bool = False) -> bool:
    """
    Ensure all required ports are available or have healthy Appium servers.

    Strategy:
    - Healthy Appium servers: REUSE (don't touch)
    - Blocked by other processes: KILL if force_kill=True
    - Free ports: OK (will start new Appium)

    Args:
        config: Parallel configuration
        force_kill: If True, kill processes blocking ports

    Returns:
        True if all ports are ready (reusable or free)
    """
    logger.info("Checking port status...")

    reusable, blocked, free = check_ports_status(config)

    # Log status
    for msg in reusable:
        logger.info(f"  {msg}")
    for msg in free:
        logger.info(f"  {msg}")

    if not blocked:
        logger.info("All ports ready!")
        return True

    # Report blocked ports
    logger.warning(f"Found {len(blocked)} blocked port(s):")
    for msg in blocked:
        logger.warning(f"  {msg}")

    if not force_kill:
        logger.error("Use --force-kill-ports to kill blocking processes")
        return False

    # Kill ONLY blocked ports (not healthy Appium)
    logger.info("Force killing blocked ports (healthy Appium will be preserved)...")
    for worker in config.workers:
        port = worker.appium_port
        # Only kill if blocked (not healthy Appium)
        if not is_healthy_appium(port) and is_port_in_use(port)[0]:
            kill_process_on_port(port)

    time.sleep(2)  # Give OS time to release ports

    # Verify
    reusable, blocked, free = check_ports_status(config)
    if blocked:
        logger.error("Some ports still blocked after killing processes:")
        for msg in blocked:
            logger.error(f"  - {msg}")
        return False

    logger.info("All ports now ready!")
    return True


def setup_signal_handlers():
    """Set up signal handlers for clean shutdown."""
    global _shutdown_requested

    def handle_signal(signum, frame):
        global _shutdown_requested, _active_config
        if not _shutdown_requested:
            _shutdown_requested = True
            logger.info(f"\nReceived signal {signum}, initiating graceful shutdown...")
            logger.info("Press Ctrl+C again to force kill")
        else:
            logger.warning("Force killing all processes...")
            force_kill_all(_active_config)
            sys.exit(1)

    if sys.platform == 'win32':
        signal.signal(signal.SIGBREAK, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)


def stop_all_phones() -> int:
    """
    Stop all running Geelark phones.

    WARNING: This stops ALL phones including VA phones!
    Use stop_campaign_phones() for campaign-specific cleanup.
    """
    logger.info("Stopping all running phones...")
    try:
        client = GeelarkClient()
        stopped = 0
        for page in range(1, 20):
            result = client.list_phones(page=page, page_size=100)
            for phone in result.get('items', []):
                if phone.get('status') == 1:
                    client.stop_phone(phone['id'])
                    logger.info(f"  Stopped: {phone.get('serialName', 'unknown')}")
                    stopped += 1
            if len(result.get('items', [])) < 100:
                break
        logger.info(f"Stopped {stopped} phone(s)")
        return stopped
    except Exception as e:
        logger.error(f"Error stopping phones: {e}")
        return 0


def stop_campaign_phones(campaign_accounts: List[str]) -> int:
    """
    Stop only phones that match the campaign's account list.

    This is the SAFE way to stop phones - it only stops phones
    whose serialName matches an account in the campaign, leaving
    VA phones and other campaigns untouched.

    Args:
        campaign_accounts: List of account names for this campaign

    Returns:
        Number of phones stopped
    """
    if not campaign_accounts:
        logger.warning("No campaign accounts provided, not stopping any phones")
        return 0

    campaign_accounts_set = set(campaign_accounts)
    logger.info(f"Stopping phones for {len(campaign_accounts_set)} campaign accounts...")

    try:
        client = GeelarkClient()
        stopped = 0
        skipped = 0

        for page in range(1, 20):
            result = client.list_phones(page=page, page_size=100)
            for phone in result.get('items', []):
                phone_name = phone.get('serialName', '')
                if phone.get('status') == 1:  # Running
                    if phone_name in campaign_accounts_set:
                        client.stop_phone(phone['id'])
                        logger.info(f"  Stopped: {phone_name}")
                        stopped += 1
                    else:
                        skipped += 1
            if len(result.get('items', [])) < 100:
                break

        if skipped > 0:
            logger.info(f"  Skipped {skipped} running phone(s) not in this campaign")
        logger.info(f"Stopped {stopped} campaign phone(s)")
        return stopped
    except Exception as e:
        logger.error(f"Error stopping campaign phones: {e}")
        return 0


def kill_all_appium_ports(config: ParallelConfig) -> int:
    """Kill ALL processes on ALL Appium ports (regardless of health)."""
    killed = 0
    for worker in config.workers:
        port = worker.appium_port
        if is_port_in_use(port)[0]:
            if kill_process_on_port(port):
                killed += 1
    return killed


def disconnect_all_adb() -> None:
    """Disconnect all stale ADB connections."""
    logger.info("Disconnecting all ADB connections...")
    try:
        adb_path = Config.ADB_PATH  # Use centralized config
        if os.path.exists(adb_path):
            subprocess.run([adb_path, 'disconnect'], capture_output=True, timeout=10)
            logger.info("  ADB disconnected all")
    except Exception as e:
        logger.warning(f"Error disconnecting ADB: {e}")


def reset_day_ctx(ctx: PostingContext, archive_dir: str = None) -> Tuple[bool, str]:
    """
    Reset for a new day by archiving the current progress file.

    CRITICAL: This is the ONLY safe way to start fresh for a new day.
    NEVER delete the progress file manually - use this command.

    The operation:
    1. Check for running orchestrators (refuse to reset if any are running)
    2. Archive current progress file to parallel_progress_YYYYMMDD.csv
    3. Create fresh progress CSV with headers only

    Args:
        ctx: PostingContext with progress_file path
        archive_dir: Optional directory for archives (default: same as progress file)

    Returns:
        (success: bool, message: str)
    """
    progress_file = ctx.progress_file

    # Check for running orchestrators first (campaign-aware)
    has_conflicts, conflicts = check_for_running_orchestrators(ctx.campaign_name)
    if has_conflicts:
        return False, f"Cannot reset while orchestrator(s) running: {conflicts}"

    if not os.path.exists(progress_file):
        return False, f"Progress file not found: {progress_file}"

    # Determine archive directory
    if archive_dir is None:
        archive_dir = os.path.dirname(progress_file) or '.'

    # Compute archive filename with today's date
    today = datetime.now().strftime('%Y%m%d')
    base_name = os.path.splitext(os.path.basename(progress_file))[0]
    archive_name = f"{base_name}_{today}.csv"
    archive_path = os.path.join(archive_dir, archive_name)

    # Handle existing archive (add suffix)
    counter = 1
    while os.path.exists(archive_path):
        archive_name = f"{base_name}_{today}_{counter}.csv"
        archive_path = os.path.join(archive_dir, archive_name)
        counter += 1

    try:
        # Read final stats before archiving
        tracker = ProgressTracker(progress_file)
        stats = tracker.get_stats()
        logger.info(f"Archiving progress file for {ctx.describe()} with stats: {stats}")

        # Move (atomic rename where possible)
        shutil.move(progress_file, archive_path)
        logger.info(f"Archived to: {archive_path}")

        # Remove lock file if exists
        lock_file = progress_file + '.lock'
        if os.path.exists(lock_file):
            os.remove(lock_file)

        # Create fresh progress file with headers only
        with open(progress_file, 'w', encoding='utf-8', newline='') as f:
            import csv
            writer = csv.DictWriter(f, fieldnames=ProgressTracker.COLUMNS)
            writer.writeheader()
        logger.info(f"Created fresh progress file: {progress_file}")

        return True, f"Reset complete for {ctx.describe()}. Archived to {archive_path}"

    except Exception as e:
        return False, f"Reset failed: {e}"


def reset_day(progress_file: str, archive_dir: str = None) -> Tuple[bool, str]:
    """
    Legacy wrapper for reset_day_ctx.

    DEPRECATED: Use reset_day_ctx(ctx) instead for campaign-aware resets.
    """
    ctx = PostingContext.legacy(progress_file=progress_file)
    return reset_day_ctx(ctx, archive_dir)


def retry_all_failed_ctx(
    ctx: PostingContext,
    include_non_retryable: bool = False
) -> int:
    """
    Reset all failed jobs back to retrying status.

    Args:
        ctx: PostingContext with progress_file path
        include_non_retryable: Include non-retryable errors (logged out, suspended, etc.)

    Returns:
        Number of jobs reset to retrying
    """
    if not os.path.exists(ctx.progress_file):
        logger.error(f"Progress file not found: {ctx.progress_file}")
        return 0

    tracker = ProgressTracker(ctx.progress_file)
    stats_before = tracker.get_stats()

    logger.info(f"Retrying failed jobs for {ctx.describe()}")
    logger.info(f"Current: {stats_before['failed']} failed, {stats_before.get('retrying', 0)} retrying")

    count = tracker.retry_all_failed(include_non_retryable=include_non_retryable)

    if count > 0:
        stats_after = tracker.get_stats()
        logger.info(f"Reset {count} jobs to retrying")
        logger.info(f"New: {stats_after['failed']} failed, {stats_after.get('retrying', 0)} retrying")

    return count


def validate_progress_file(progress_file: str) -> bool:
    """
    Check if progress file is valid (not empty/corrupt).

    CRITICAL: This function NO LONGER deletes files automatically.
    The progress file is the daily ledger and must be preserved.
    If the file is empty or corrupt, operator must manually use --reset-day.

    Returns:
        True if file is valid or doesn't exist
        False if file exists but is empty/corrupt (DOES NOT DELETE - requires manual fix)
    """
    if not os.path.exists(progress_file):
        return True

    try:
        # Check file size first
        file_size = os.path.getsize(progress_file)
        if file_size == 0:
            logger.error(f"Progress file {progress_file} is empty (0 bytes). "
                        f"Use --reset-day to archive and create a fresh ledger.")
            return False

        import csv
        with open(progress_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if len(rows) == 0:
                logger.error(f"Progress file {progress_file} has header but no data rows. "
                            f"Use --reset-day to archive and create a fresh ledger.")
                return False
        return True
    except Exception as e:
        logger.error(f"Progress file {progress_file} appears corrupt: {e}. "
                    f"Use --reset-day to archive and create a fresh ledger.")
        return False


def full_cleanup(
    config: ParallelConfig,
    release_claims: bool = True,
    campaign_accounts: List[str] = None
) -> None:
    """
    Complete cleanup of resources.

    Call this:
    - At startup before any workers
    - On shutdown/Ctrl+C
    - On --stop-all command

    Cleans up:
    1. Running phones (campaign-specific if accounts provided, otherwise ALL)
    2. ALL processes on Appium ports
    3. ALL stale ADB connections
    4. Empty/corrupt progress files
    5. Release stale claimed jobs back to pending

    Args:
        config: Parallel configuration
        release_claims: Whether to release stale claimed jobs
        campaign_accounts: If provided, only stop phones matching these accounts.
                          If None, stops ALL phones (use with caution!)
    """
    logger.info("="*60)
    if campaign_accounts:
        logger.info(f"CAMPAIGN CLEANUP - Freeing resources for {len(campaign_accounts)} accounts")
    else:
        logger.info("FULL CLEANUP - Freeing ALL resources (including non-campaign phones)")
    logger.info("="*60)

    # 1. Stop phones (campaign-specific or ALL)
    if campaign_accounts:
        phones_stopped = stop_campaign_phones(campaign_accounts)
    else:
        phones_stopped = stop_all_phones()

    # 2. Kill ALL Appium port processes
    logger.info("Killing all processes on Appium ports...")
    ports_killed = kill_all_appium_ports(config)
    logger.info(f"  Killed {ports_killed} port process(es)")

    # 3. Disconnect stale ADB
    disconnect_all_adb()

    # 4. Validate progress file
    validate_progress_file(config.progress_file)

    # 5. Release any stale claimed jobs (workers crashed mid-job)
    if release_claims and os.path.exists(config.progress_file):
        try:
            tracker = ProgressTracker(config.progress_file)
            released = tracker.release_stale_claims(max_age_seconds=0)
            if released > 0:
                logger.info(f"  Released {released} stale claimed job(s) back to pending")
        except Exception as e:
            logger.warning(f"  Could not release stale claims: {e}")

    # Give OS time to release resources
    time.sleep(2)

    logger.info("="*60)
    logger.info(f"CLEANUP COMPLETE: {phones_stopped} phones stopped, {ports_killed} ports freed")
    logger.info("="*60)


def seed_progress_file_ctx(
    ctx: PostingContext,
    parallel_config: ParallelConfig,
    force_reseed: bool = False,
) -> int:
    """
    Seed progress file from campaign or legacy state.

    Args:
        ctx: PostingContext with all paths and settings
        parallel_config: Worker configuration
        force_reseed: If True, overwrite existing progress file

    Returns:
        Number of jobs seeded
    """
    tracker = ProgressTracker(ctx.progress_file)

    # Check existing file
    if tracker.exists() and not force_reseed:
        stats = tracker.get_stats()
        if stats['pending'] > 0 or stats['claimed'] > 0:
            logger.warning(f"Progress file already has {stats['pending']} pending, {stats['claimed']} claimed jobs")
            logger.warning("Use --force-reseed to overwrite")
            return 0

    logger.info(f"Seeding progress file for {ctx.describe()}...")

    try:
        if ctx.is_campaign_mode():
            # Campaign mode: seed from captions CSV
            count = tracker.seed_from_campaign(
                ctx.campaign_config,
                max_posts_per_account_per_day=ctx.max_posts_per_account_per_day
            )
        else:
            # Legacy mode: seed from scheduler_state.json
            if not ctx.state_file or not os.path.exists(ctx.state_file):
                logger.error(f"State file not found: {ctx.state_file}")
                return 0

            accounts = ctx.get_accounts()
            count = tracker.seed_from_scheduler_state(
                ctx.state_file,
                accounts,
                redistribute=False,
                max_posts_per_account_per_day=ctx.max_posts_per_account_per_day
            )

        logger.info(f"Seeded {count} jobs (max {ctx.max_posts_per_account_per_day} posts/account/day)")
        return count
    except Exception as e:
        logger.error(f"Error seeding: {e}")
        import traceback
        traceback.print_exc()
        return 0


def seed_progress_file(
    config: ParallelConfig,
    state_file: str = "scheduler_state.json",
    accounts_filter: List[str] = None
) -> int:
    """
    Legacy wrapper for seed_progress_file_ctx.

    DEPRECATED: Use seed_progress_file_ctx(ctx, parallel_config) instead.
    """
    ctx = PostingContext.legacy(
        progress_file=config.progress_file,
        state_file=state_file,
        max_posts_per_account_per_day=config.max_posts_per_account_per_day
    )
    return seed_progress_file_ctx(ctx, config, force_reseed=False)


def start_worker_process(worker_id: int, config: ParallelConfig) -> subprocess.Popen:
    """Start a single worker subprocess."""
    cmd = [
        sys.executable,
        'parallel_worker.py',
        '--worker-id', str(worker_id),
        '--num-workers', str(config.num_workers),
        '--progress-file', config.progress_file,
        '--delay', str(config.delay_between_jobs)
    ]

    logger.info(f"Starting worker {worker_id}...")

    # Get environment with Android SDK
    env = os.environ.copy()
    env.update(config.get_env_vars())

    if sys.platform == 'win32':
        proc = subprocess.Popen(
            cmd,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        proc = subprocess.Popen(
            cmd,
            env=env,
            start_new_session=True
        )

    logger.info(f"Worker {worker_id} started with PID {proc.pid}")
    return proc


def start_all_workers(config: ParallelConfig) -> List[subprocess.Popen]:
    """Start all worker processes."""
    global _worker_processes

    processes = []
    for worker in config.workers:
        proc = start_worker_process(worker.worker_id, config)
        processes.append(proc)
        time.sleep(60)  # Stagger starts - 60s between workers for Geelark ADB setup to complete

    _worker_processes = processes
    return processes


def stop_all_workers(processes: List[subprocess.Popen], timeout: int = 30) -> None:
    """Stop all worker processes gracefully."""
    logger.info(f"Stopping {len(processes)} worker(s)...")

    # Send termination signal
    for proc in processes:
        if proc.poll() is None:
            try:
                if sys.platform == 'win32':
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.terminate()
            except Exception as e:
                logger.warning(f"Error signaling process {proc.pid}: {e}")

    # Wait for graceful shutdown
    deadline = time.time() + timeout
    while time.time() < deadline:
        all_done = all(proc.poll() is not None for proc in processes)
        if all_done:
            break
        time.sleep(1)

    # Force kill any remaining
    for proc in processes:
        if proc.poll() is None:
            logger.warning(f"Force killing worker PID {proc.pid}")
            proc.kill()

    logger.info("All workers stopped")


def force_kill_all(config: ParallelConfig = None):
    """Force kill all workers and cleanup all resources."""
    global _worker_processes, _active_campaign_accounts

    # Kill all worker processes
    for proc in _worker_processes:
        if proc.poll() is None:
            try:
                proc.kill()
            except:
                pass

    # Full cleanup if we have config
    if config:
        full_cleanup(config, campaign_accounts=_active_campaign_accounts)
    else:
        # Fallback: just stop campaign phones (or all if no campaign) and kill common ports
        if _active_campaign_accounts:
            stop_campaign_phones(_active_campaign_accounts)
        else:
            stop_all_phones()
        for port in [4723, 4725, 4727, 4729, 4731]:
            kill_process_on_port(port)


def monitor_workers(processes: List[subprocess.Popen], config: ParallelConfig) -> None:
    """Monitor worker processes until all complete or shutdown requested."""
    global _shutdown_requested

    tracker = ProgressTracker(config.progress_file)

    logger.info("Monitoring workers... (Ctrl+C to stop)")

    last_status_time = 0
    status_interval = 30  # Print status every 30 seconds

    while not _shutdown_requested:
        # Check if all workers have exited
        all_done = all(proc.poll() is not None for proc in processes)
        if all_done:
            logger.info("All workers have exited")
            break

        # Print periodic status
        now = time.time()
        if now - last_status_time >= status_interval:
            stats = tracker.get_stats()
            active_workers = sum(1 for p in processes if p.poll() is None)
            logger.info(
                f"Status: {stats['success']} success, {stats['failed']} failed, "
                f"{stats['pending']} pending, {stats['claimed']} in-progress | "
                f"{active_workers}/{len(processes)} workers active"
            )
            last_status_time = now

        time.sleep(1)

    # If shutdown requested, stop workers
    if _shutdown_requested:
        stop_all_workers(processes, timeout=config.shutdown_timeout)


def show_status_ctx(ctx: PostingContext, parallel_config: ParallelConfig) -> None:
    """
    Show current status of progress and resources.

    Args:
        ctx: PostingContext for file paths
        parallel_config: Worker configuration
    """
    print("\n" + "="*60)
    print(f"PARALLEL POSTING STATUS - {ctx.describe()}")
    print("="*60)

    # Progress stats
    tracker = ProgressTracker(ctx.progress_file)
    if tracker.exists():
        stats = tracker.get_stats()
        print(f"\nProgress ({ctx.progress_file}):")
        print(f"  Total jobs:  {stats['total']}")
        print(f"  Pending:     {stats['pending']}")
        print(f"  In-progress: {stats['claimed']}")
        print(f"  Retrying:    {stats.get('retrying', 0)}")
        print(f"  Success:     {stats['success']}")
        print(f"  Failed:      {stats['failed']}")

        if stats['success'] + stats['failed'] > 0:
            success_rate = stats['success'] / (stats['success'] + stats['failed']) * 100
            print(f"  Success rate: {success_rate:.1f}%")

        # Per-worker stats
        worker_stats = tracker.get_worker_stats()
        if worker_stats:
            print("\n  Per-worker:")
            for wid, ws in sorted(worker_stats.items()):
                print(f"    Worker {wid}: {ws['success']} success, {ws['failed']} failed")
    else:
        print(f"\nProgress file not found: {ctx.progress_file}")
        print("  Run with --seed-only or --run to create it")

    # If campaign mode, show campaign-specific info
    if ctx.is_campaign_mode():
        print(f"\nCampaign Info:")
        print(f"  Name: {ctx.campaign_name}")
        print(f"  Videos: {ctx.videos_dir}")
        try:
            print(f"  Accounts: {len(ctx.get_accounts())}")
        except Exception:
            print(f"  Accounts: (error reading)")

    # Appium server status
    print("\nAppium Servers:")
    appium_status = check_all_appium_servers(parallel_config)
    for wid, status in sorted(appium_status.items()):
        state = "RUNNING" if status['healthy'] else "NOT RUNNING"
        print(f"  Worker {wid}: port {status['port']} - {state}")

    # Running phones
    print("\nGeelark Phones:")
    try:
        client = GeelarkClient()
        result = client.list_phones(page_size=100)
        running = [p for p in result.get('items', []) if p.get('status') == 1]

        # If campaign mode, highlight which phones are in the campaign
        if ctx.is_campaign_mode():
            try:
                campaign_accounts = set(ctx.get_accounts())
            except Exception:
                campaign_accounts = set()

            if running:
                campaign_phones = [p for p in running if p.get('serialName', '') in campaign_accounts]
                other_phones = [p for p in running if p.get('serialName', '') not in campaign_accounts]

                if campaign_phones:
                    print(f"  Campaign phones ({len(campaign_phones)}):")
                    for phone in campaign_phones:
                        print(f"    RUNNING: {phone.get('serialName', 'unknown')}")

                if other_phones:
                    print(f"  Other phones ({len(other_phones)}):")
                    for phone in other_phones:
                        print(f"    RUNNING: {phone.get('serialName', 'unknown')}")

                if not campaign_phones and not other_phones:
                    print("  No phones currently running")
            else:
                print("  No phones currently running")
        else:
            if running:
                for phone in running:
                    print(f"  RUNNING: {phone.get('serialName', 'unknown')}")
            else:
                print("  No phones currently running")
    except Exception as e:
        print(f"  Error checking phones: {e}")

    print("="*60 + "\n")


def show_status(config: ParallelConfig) -> None:
    """
    Legacy wrapper for show_status_ctx.

    DEPRECATED: Use show_status_ctx(ctx, parallel_config) instead.
    """
    ctx = PostingContext.legacy(progress_file=config.progress_file)
    show_status_ctx(ctx, config)


def run_parallel_posting_ctx(
    ctx: PostingContext,
    num_workers: int = 3,
    force_reseed: bool = False,
    retry_all_failed: bool = True,
    retry_include_non_retryable: bool = False,
    retry_config: RetryConfig = None,
) -> Dict:
    """
    Main entry point for parallel posting with PostingContext.

    Args:
        ctx: PostingContext (campaign or legacy)
        num_workers: Number of parallel workers
        force_reseed: Force reseed progress file
        retry_all_failed: Retry failed jobs from previous runs
        retry_include_non_retryable: Include non-retryable in retry
        retry_config: Multi-pass retry configuration

    Returns:
        Dict with results
    """
    global _active_config, _shutdown_requested, _active_campaign_accounts

    setup_signal_handlers()

    parallel_config = get_config(num_workers=num_workers)
    parallel_config.progress_file = ctx.progress_file

    # Store for emergency cleanup
    campaign_accounts = ctx.get_accounts() if ctx.is_campaign_mode() else None
    _active_campaign_accounts = campaign_accounts

    logger.info(f"Starting posting for {ctx.describe()}")
    logger.info(f"  Progress file: {ctx.progress_file}")
    try:
        logger.info(f"  Accounts: {len(ctx.get_accounts())}")
    except Exception:
        pass

    _active_config = parallel_config  # Store for signal handler

    # Use default retry config if not provided
    if retry_config is None:
        retry_config = RetryConfig()

    # CRITICAL: Check for other running orchestrators BEFORE anything else
    logger.info(f"Checking for conflicting orchestrators (campaign: {ctx.campaign_name or 'none'})...")
    has_conflicts, conflicts = check_for_running_orchestrators(ctx.campaign_name)
    if has_conflicts:
        logger.error("="*60)
        logger.error("CONFLICT: Another orchestrator is running!")
        logger.error("="*60)
        for conflict in conflicts:
            logger.error(f"  - {conflict}")
        logger.error("")
        logger.error("Running multiple orchestrators for the SAME campaign causes:")
        logger.error("  - Race conditions in job claiming")
        logger.error("  - Duplicate posts to accounts")
        logger.error("  - Accounts exceeding daily post limits")
        logger.error("")
        logger.error("Please stop the other orchestrator first, or use --stop-all")
        if ctx.is_campaign_mode():
            logger.error("NOTE: Different campaigns can run concurrently.")
        logger.error("="*60)
        return {'error': 'orchestrator_conflict', 'conflicts': conflicts}
    logger.info("No conflicting orchestrators found")

    print_config(parallel_config)

    # Ensure logs directory exists
    parallel_config.ensure_logs_dir()

    # CLEANUP at startup - stop phones, kill ports, clear stale ADB
    # If campaign specified, only stop campaign phones (not VA phones)
    full_cleanup(parallel_config, campaign_accounts=campaign_accounts)

    # Seed progress file
    tracker = ProgressTracker(ctx.progress_file)

    # CRITICAL: Retry all failed jobs from previous runs
    if retry_all_failed and tracker.exists():
        stats_before = tracker.get_stats()
        if stats_before['failed'] > 0:
            logger.info("="*60)
            logger.info("RETRYING FAILED JOBS FROM PREVIOUS RUNS")
            logger.info("="*60)
            count = tracker.retry_all_failed(include_non_retryable=retry_include_non_retryable)
            if count > 0:
                logger.info(f"Reset {count} failed jobs to RETRYING status")
            logger.info("="*60)

    if force_reseed and tracker.exists():
        logger.info("Force reseeding - removing existing progress file")
        os.remove(ctx.progress_file)
        if os.path.exists(ctx.progress_file + '.lock'):
            os.remove(ctx.progress_file + '.lock')

    if not tracker.exists() or force_reseed:
        count = seed_progress_file_ctx(ctx, parallel_config, force_reseed)
        if count == 0:
            if ctx.is_campaign_mode():
                logger.error(f"No jobs to process. Check campaign folder: {ctx.campaign_config.base_dir}")
            else:
                logger.error("No jobs to process. Check scheduler_state.json and accounts.txt")
            return {'error': 'no_jobs'}

    # Show initial stats
    stats = tracker.get_stats()
    logger.info(f"Starting with {stats['pending']} pending jobs for {ctx.describe()}")

    # Initialize retry pass manager
    retry_mgr = RetryPassManager(tracker, retry_config)

    try:
        # Multi-pass retry loop
        result = PassResult.RETRYABLE_REMAINING

        while result == PassResult.RETRYABLE_REMAINING and not _shutdown_requested:
            # Start new pass
            pass_num = retry_mgr.start_new_pass()

            # Start workers for this pass
            processes = start_all_workers(parallel_config)

            # Monitor until pass complete
            monitor_workers(processes, parallel_config)

            # If shutdown requested, break out of retry loop
            if _shutdown_requested:
                logger.info("Shutdown requested, stopping retry loop")
                break

            # End pass and decide what to do next
            result = retry_mgr.end_pass()

            if result == PassResult.RETRYABLE_REMAINING:
                logger.info(f"Waiting {retry_config.retry_delay_seconds}s before next pass...")
                for _ in range(retry_config.retry_delay_seconds):
                    if _shutdown_requested:
                        break
                    time.sleep(1)

        # Log final result
        if result == PassResult.ALL_COMPLETE:
            logger.info("All jobs completed successfully!")
        elif result == PassResult.ONLY_NON_RETRYABLE:
            logger.info("Stopped: Only non-retryable account failures remain")
        elif result == PassResult.MAX_PASSES_REACHED:
            logger.info(f"Stopped: Max passes ({retry_config.max_passes}) reached")

    finally:
        # CLEANUP on exit - stop campaign phones, free ports, clear ADB
        full_cleanup(parallel_config, campaign_accounts=campaign_accounts)
        _active_campaign_accounts = None  # Clear global

    # Final stats
    final_stats = tracker.get_stats()
    failure_stats = tracker.get_failure_stats()

    logger.info("="*60)
    logger.info(f"FINAL RESULTS - {ctx.describe()}")
    logger.info(f"  Success:  {final_stats['success']}")
    logger.info(f"  Failed:   {final_stats['failed']}")
    logger.info(f"    - Account issues: {failure_stats['account_failures']}")
    logger.info(f"    - Infrastructure: {failure_stats['infrastructure_failures']}")
    logger.info(f"    - Unknown: {failure_stats['unknown_failures']}")
    logger.info(f"  Retrying: {final_stats.get('retrying', 0)}")
    logger.info(f"  Pending:  {final_stats['pending']}")
    logger.info(f"  Total passes: {retry_mgr.current_pass}")
    logger.info("="*60)

    # Add retry summary to results
    final_stats['retry_summary'] = retry_mgr.get_summary()
    final_stats['failure_breakdown'] = failure_stats

    return final_stats


def run_parallel_posting(
    num_workers: int = 3,
    state_file: str = "scheduler_state.json",
    force_reseed: bool = False,
    force_kill_ports: bool = False,
    accounts: List[str] = None,
    retry_all_failed: bool = True,
    retry_include_non_retryable: bool = False,
    retry_config: RetryConfig = None,
    campaign_config: 'CampaignConfig' = None
) -> Dict:
    """
    Legacy wrapper for run_parallel_posting_ctx.

    DEPRECATED: Use run_parallel_posting_ctx(ctx, ...) instead for cleaner code.
    """
    # Build context based on parameters
    if campaign_config:
        ctx = PostingContext.from_campaign(campaign_config)
    else:
        ctx = PostingContext.legacy(
            progress_file=Config.PROGRESS_FILE,
            state_file=state_file,
        )

    return run_parallel_posting_ctx(
        ctx=ctx,
        num_workers=num_workers,
        force_reseed=force_reseed,
        retry_all_failed=retry_all_failed,
        retry_include_non_retryable=retry_include_non_retryable,
        retry_config=retry_config,
    )


def load_campaign_or_exit(campaign_arg: str) -> CampaignConfig:
    """
    Load campaign config or exit with error.

    Args:
        campaign_arg: Campaign name or path

    Returns:
        CampaignConfig instance
    """
    # Try as name in campaigns/ directory
    campaign_path = os.path.join(Config.PROJECT_ROOT, Config.CAMPAIGNS_DIR, campaign_arg)

    if not os.path.isdir(campaign_path):
        # Try as direct path
        campaign_path = campaign_arg

    try:
        return CampaignConfig.from_folder(campaign_path)
    except FileNotFoundError:
        logger.error(f"Campaign folder not found: {campaign_path}")
        logger.error("Available campaigns:")
        for c in CampaignConfig.list_campaigns():
            logger.error(f"  - {c.name}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Invalid campaign '{campaign_arg}': {e}")
        sys.exit(1)


def list_campaigns_command():
    """Handle --list-campaigns command."""
    campaigns = CampaignConfig.list_campaigns()

    if not campaigns:
        print("\nNo campaigns found in campaigns/ directory")
        print("Create a campaign folder with:")
        print("  - accounts.txt (one account per line)")
        print("  - captions.csv (filename,post_caption columns)")
        print("  - videos/ subfolder with .mp4 files")
        return

    print("\n" + "="*60)
    print("AVAILABLE CAMPAIGNS")
    print("="*60)

    for c in campaigns:
        status = "ENABLED" if c.enabled else "DISABLED"
        try:
            accounts = c.get_accounts()
            account_count = len(accounts)
        except Exception:
            account_count = "(error)"

        print(f"\n  {c.name} [{status}]")
        print(f"    Accounts:     {account_count}")
        print(f"    Videos:       {c.videos_dir}")
        print(f"    Captions:     {c.captions_file}")
        print(f"    Progress:     {c.progress_file}")
        print(f"    Daily limit:  {c.max_posts_per_account_per_day} posts/account")

    print("\n" + "="*60)
    print("Usage: python parallel_orchestrator.py --campaign <name> --run")
    print("="*60 + "\n")


def main():
    """CLI entry point with clean context-based dispatch."""
    parser = argparse.ArgumentParser(
        description='Parallel Posting Orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with 3 workers
  python parallel_orchestrator.py --workers 3 --run

  # Run a specific campaign
  python parallel_orchestrator.py --campaign viral --workers 5 --run

  # Check current status
  python parallel_orchestrator.py --status

  # Check campaign status
  python parallel_orchestrator.py --campaign viral --status

  # Stop everything
  python parallel_orchestrator.py --stop-all

  # Just seed progress file
  python parallel_orchestrator.py --seed-only
        """
    )

    parser.add_argument('--workers', '-w', type=int, default=3,
                        help='Number of parallel workers (default: 3)')
    parser.add_argument('--state-file', default='scheduler_state.json',
                        help='Path to scheduler state file')
    parser.add_argument('--run', action='store_true',
                        help='Run parallel posting')
    parser.add_argument('--status', action='store_true',
                        help='Show current status')
    parser.add_argument('--stop-all', action='store_true',
                        help='Stop all workers, Appium servers, and phones')
    parser.add_argument('--seed-only', action='store_true',
                        help='Only seed progress file, do not run')
    parser.add_argument('--force-reseed', action='store_true',
                        help='Force reseed progress file even if exists')
    parser.add_argument('--force-kill-ports', action='store_true',
                        help='Force kill processes blocking required ports')
    parser.add_argument('--accounts', '-a',
                        help='Comma-separated list of accounts to use (e.g., phone1,phone2)')
    parser.add_argument('--reset-day', action='store_true',
                        help='Archive current progress file and start fresh for new day')
    parser.add_argument('--retry-all-failed', action='store_true',
                        help='Reset all failed jobs back to retrying status (runs automatically with --run)')
    parser.add_argument('--retry-include-non-retryable', action='store_true',
                        help='When retrying, also include non-retryable errors (logged out, suspended, etc.)')

    # Multi-pass retry configuration
    parser.add_argument('--max-passes', type=int, default=3,
                        help='Maximum number of retry passes (default: 3)')
    parser.add_argument('--retry-delay', type=int, default=30,
                        help='Delay in seconds between retry passes (default: 30)')
    parser.add_argument('--infra-retry-limit', type=int, default=3,
                        help='Max retries per job for infrastructure errors (default: 3)')
    parser.add_argument('--no-retry-unknown', action='store_true',
                        help='Do NOT retry jobs with unknown/unclassified errors (default: retry them)')

    # Campaign support
    parser.add_argument('--campaign', '-c', type=str, default=None,
                        help='Campaign name to run (e.g., "viral", "podcast"). Uses campaigns/<name>/ folder.')
    parser.add_argument('--list-campaigns', action='store_true',
                        help='List all available campaigns')

    # Navigation mode (hybrid vs AI-only)
    parser.add_argument('--ai-only', action='store_true',
                        help='Use AI-only mode (for mapping NEW flows, disables rule-based navigation)')
    parser.add_argument('--no-ai-fallback', action='store_true',
                        help='STRICT rules-only mode - no AI rescue when rules fail. '
                             'Use this to TEST which rules work/fail. Failures are intentional!')

    args = parser.parse_args()

    parallel_config = get_config(num_workers=args.workers)

    # Apply navigation mode settings
    if args.ai_only:
        parallel_config.use_hybrid = False
        parallel_config.ai_fallback = True  # N/A in AI-only mode
        logger.info("[NAV MODE] AI-ONLY - Claude decides every step (for mapping new flows)")
    elif args.no_ai_fallback:
        parallel_config.use_hybrid = True
        parallel_config.ai_fallback = False
        logger.warning("[NAV MODE] STRICT RULES-ONLY - No AI fallback!")
        logger.warning("  Failures will expose broken rules - this is intentional for testing")
    else:
        parallel_config.use_hybrid = True
        parallel_config.ai_fallback = True
        logger.info("[NAV MODE] HYBRID - Rule-based navigation with AI fallback")

    # ============================================================
    # STEP 1: Handle --list-campaigns (no context needed)
    # ============================================================
    if args.list_campaigns:
        list_campaigns_command()
        sys.exit(0)

    # ============================================================
    # STEP 2: Build PostingContext (single source of truth)
    # ============================================================
    ctx: PostingContext

    if args.campaign:
        # Campaign mode
        campaign_config = load_campaign_or_exit(args.campaign)

        # Check if campaign is enabled
        if not campaign_config.enabled:
            logger.error(f"Campaign '{campaign_config.name}' is disabled")
            logger.error("Enable it by setting 'enabled: true' in campaign.json")
            sys.exit(1)

        ctx = PostingContext.from_campaign(campaign_config)
        logger.info(f"Loaded {ctx.describe()}")
        logger.info(f"  Progress: {ctx.progress_file}")
        try:
            logger.info(f"  Accounts: {len(ctx.get_accounts())}")
        except Exception:
            pass
    else:
        # Legacy mode
        ctx = PostingContext.legacy(
            progress_file=Config.PROGRESS_FILE,
            accounts_file=Config.ACCOUNTS_FILE,
            state_file=args.state_file,
        )
        logger.info(f"Running in {ctx.describe()}")

    # Warn about ignored flags
    if args.campaign and args.state_file != 'scheduler_state.json':
        logger.warning("--state-file ignored when --campaign is specified")
    if args.campaign and args.accounts:
        logger.warning("--accounts ignored when --campaign is specified (using campaign accounts)")

    # ============================================================
    # STEP 3: Dispatch to operation (all use ctx)
    # ============================================================

    if args.reset_day:
        logger.info("="*60)
        logger.info(f"DAILY RESET - Archiving progress file for {ctx.describe()}")
        logger.info("="*60)
        success, message = reset_day_ctx(ctx)
        if success:
            logger.info(message)
            logger.info("Ready for new day. Run with --run to start posting.")
        else:
            logger.error(message)
            sys.exit(1)

    elif args.retry_all_failed:
        count = retry_all_failed_ctx(ctx, args.retry_include_non_retryable)
        if count == 0:
            logger.info("No failed jobs to retry")

    elif args.status:
        show_status_ctx(ctx, parallel_config)

    elif args.stop_all:
        if ctx.is_campaign_mode():
            campaign_accounts = ctx.get_accounts()
            logger.info(f"Stopping {ctx.describe()} phones ({len(campaign_accounts)} accounts)...")
            full_cleanup(parallel_config, campaign_accounts=campaign_accounts)
        else:
            logger.info("Stopping ALL phones (no campaign specified)...")
            full_cleanup(parallel_config)
        logger.info("Done")

    elif args.seed_only:
        count = seed_progress_file_ctx(ctx, parallel_config, args.force_reseed)
        if count > 0:
            logger.info(f"Progress file ready with {count} jobs for {ctx.describe()}")
        else:
            logger.error("Failed to seed progress file (no jobs created)")
            sys.exit(1)

    elif args.run:
        # SAFETY CHECK: --force-reseed requires --reset-day to prevent accidental mid-day reseeds
        if args.force_reseed and os.path.exists(ctx.progress_file):
            logger.error("SAFETY: --force-reseed is not allowed when progress file exists!")
            logger.error("  The progress file is the daily ledger and tracks posting limits.")
            logger.error("  Reseeding mid-day can cause duplicate posts and exceed daily limits.")
            logger.error("")
            logger.error("  To start a new day: python parallel_orchestrator.py --reset-day")
            logger.error("  Then run normally without --force-reseed")
            sys.exit(1)

        # Create RetryConfig from CLI args
        retry_cfg = RetryConfig(
            max_passes=args.max_passes,
            retry_delay_seconds=args.retry_delay,
            infrastructure_retry_limit=args.infra_retry_limit,
            unknown_error_is_retryable=not args.no_retry_unknown
        )

        logger.info(f"Retry config: max_passes={retry_cfg.max_passes}, "
                   f"retry_delay={retry_cfg.retry_delay_seconds}s, "
                   f"infra_limit={retry_cfg.infrastructure_retry_limit}, "
                   f"retry_unknown={retry_cfg.unknown_error_is_retryable}")

        results = run_parallel_posting_ctx(
            ctx=ctx,
            num_workers=args.workers,
            force_reseed=args.force_reseed,
            retry_all_failed=True,  # Always retry failed jobs on start
            retry_include_non_retryable=args.retry_include_non_retryable,
            retry_config=retry_cfg,
        )
        if results.get('error'):
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
