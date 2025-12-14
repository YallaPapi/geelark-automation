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
from config import Config, setup_environment
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


def check_for_running_orchestrators() -> Tuple[bool, List[str]]:
    """
    Check if other orchestrator processes are running.

    CRITICAL: This must be called BEFORE starting any workers.
    Multiple orchestrators running simultaneously causes race conditions
    and can result in duplicate posts or accounts getting >1 post per day.

    Returns:
        (has_conflicts: bool, list of conflicting process descriptions)
    """
    current_pid = os.getpid()
    conflicts = []

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
                        conflicts.append(f"PID {pid}: parallel_orchestrator.py --run")

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
                            conflicts.append(f"PID {pid}: parallel_orchestrator.py --run")

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
    """Stop all running Geelark phones."""
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


def reset_day(progress_file: str, archive_dir: str = None) -> Tuple[bool, str]:
    """
    Reset for a new day by archiving the current progress file.

    CRITICAL: This is the ONLY safe way to start fresh for a new day.
    NEVER delete the progress file manually - use this command.

    The operation:
    1. Check for running orchestrators (refuse to reset if any are running)
    2. Archive current progress file to parallel_progress_YYYYMMDD.csv
    3. Create fresh progress CSV with headers only

    Args:
        progress_file: Path to progress CSV
        archive_dir: Optional directory for archives (default: same as progress file)

    Returns:
        (success: bool, message: str)
    """
    # Check for running orchestrators first
    has_conflicts, conflicts = check_for_running_orchestrators()
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
        logger.info(f"Archiving progress file with stats: {stats}")

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

        return True, f"Archived to {archive_path}, fresh progress file created"

    except Exception as e:
        return False, f"Reset failed: {e}"


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


def full_cleanup(config: ParallelConfig, release_claims: bool = True) -> None:
    """
    Complete cleanup of ALL resources.

    Call this:
    - At startup before any workers
    - On shutdown/Ctrl+C
    - On --stop-all command

    Cleans up:
    1. ALL running phones (they cost money!)
    2. ALL processes on Appium ports
    3. ALL stale ADB connections
    4. Empty/corrupt progress files
    5. Release stale claimed jobs back to pending
    """
    logger.info("="*60)
    logger.info("FULL CLEANUP - Freeing all resources")
    logger.info("="*60)

    # 1. Stop ALL phones first (they cost money!)
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


def seed_progress_file(
    config: ParallelConfig,
    state_file: str = "scheduler_state.json",
    accounts_filter: List[str] = None
) -> int:
    """
    Seed the progress file from scheduler state.

    Args:
        config: Parallel config
        state_file: Path to scheduler_state.json
        accounts_filter: Optional list of accounts to include

    Returns:
        Number of jobs seeded
    """
    logger.info(f"Seeding progress file from {state_file}...")

    if not os.path.exists(state_file):
        logger.error(f"State file not found: {state_file}")
        return 0

    tracker = ProgressTracker(config.progress_file)

    # Check if progress file already exists with pending jobs
    if tracker.exists():
        stats = tracker.get_stats()
        if stats['pending'] > 0 or stats['claimed'] > 0:
            logger.warning(f"Progress file already has {stats['pending']} pending, {stats['claimed']} claimed jobs")
            logger.warning("Use --force-reseed to overwrite")
            return 0

    try:
        # redistribute=False preserves original job order and account assignments
        # Account-level locking in claim_next_job handles conflict prevention
        # Pass max_posts_per_account_per_day from config for daily limit enforcement
        count = tracker.seed_from_scheduler_state(
            state_file,
            accounts_filter,
            redistribute=False,
            max_posts_per_account_per_day=config.max_posts_per_account_per_day
        )
        logger.info(f"Seeded {count} jobs (max {config.max_posts_per_account_per_day} posts/account/day)")
        return count
    except Exception as e:
        logger.error(f"Error seeding: {e}")
        return 0


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
    global _worker_processes

    # Kill all worker processes
    for proc in _worker_processes:
        if proc.poll() is None:
            try:
                proc.kill()
            except:
                pass

    # Full cleanup if we have config
    if config:
        full_cleanup(config)
    else:
        # Fallback: just stop phones and kill common ports
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


def show_status(config: ParallelConfig) -> None:
    """Show current status of progress and Appium servers."""
    print("\n" + "="*60)
    print("PARALLEL POSTING STATUS")
    print("="*60)

    # Progress stats
    tracker = ProgressTracker(config.progress_file)
    if tracker.exists():
        stats = tracker.get_stats()
        print(f"\nProgress ({config.progress_file}):")
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
        print(f"\nProgress file not found: {config.progress_file}")
        print("  Run with --seed-only or --run to create it")

    # Appium server status
    print("\nAppium Servers:")
    appium_status = check_all_appium_servers(config)
    for wid, status in sorted(appium_status.items()):
        state = "RUNNING" if status['healthy'] else "NOT RUNNING"
        print(f"  Worker {wid}: port {status['port']} - {state}")

    # Running phones
    print("\nGeelark Phones:")
    try:
        client = GeelarkClient()
        result = client.list_phones(page_size=100)
        running = [p for p in result.get('items', []) if p.get('status') == 1]
        if running:
            for phone in running:
                print(f"  RUNNING: {phone.get('serialName', 'unknown')}")
        else:
            print("  No phones currently running")
    except Exception as e:
        print(f"  Error checking phones: {e}")

    print("="*60 + "\n")


def run_parallel_posting(
    num_workers: int = 3,
    state_file: str = "scheduler_state.json",
    force_reseed: bool = False,
    force_kill_ports: bool = False,
    accounts: List[str] = None,
    retry_all_failed: bool = True,
    retry_include_non_retryable: bool = False,
    retry_config: RetryConfig = None
) -> Dict:
    """
    Main entry point to run parallel posting with multi-pass retry.

    Args:
        num_workers: Number of parallel workers
        state_file: Path to scheduler state file
        force_reseed: Force reseed progress file even if it exists
        force_kill_ports: Force kill processes blocking required ports
        accounts: List of accounts to use (required for distribution)
        retry_all_failed: If True, retry failed jobs from previous runs
        retry_include_non_retryable: If True, also retry non-retryable errors
        retry_config: RetryConfig for multi-pass retry behavior

    Returns:
        Dict with results: {success_count, failed_count, ...}
    """
    global _active_config, _shutdown_requested

    setup_signal_handlers()

    config = get_config(num_workers=num_workers)
    _active_config = config  # Store for signal handler

    # Use default retry config if not provided
    if retry_config is None:
        retry_config = RetryConfig()

    # CRITICAL: Check for other running orchestrators BEFORE anything else
    # Multiple orchestrators = race conditions = duplicate posts
    logger.info("Checking for other running orchestrators...")
    has_conflicts, conflicts = check_for_running_orchestrators()
    if has_conflicts:
        logger.error("="*60)
        logger.error("CONFLICT: Other orchestrator processes are running!")
        logger.error("="*60)
        for conflict in conflicts:
            logger.error(f"  - {conflict}")
        logger.error("")
        logger.error("Running multiple orchestrators simultaneously causes:")
        logger.error("  - Race conditions in job claiming")
        logger.error("  - Duplicate posts to accounts")
        logger.error("  - Accounts exceeding daily post limits")
        logger.error("")
        logger.error("Please stop the other orchestrator(s) first, or use --stop-all")
        logger.error("="*60)
        return {'error': 'orchestrator_conflict', 'conflicts': conflicts}
    logger.info("No conflicting orchestrators found")

    print_config(config)

    # Ensure logs directory exists
    config.ensure_logs_dir()

    # FULL CLEANUP at startup - stop ALL phones, kill ALL ports, clear stale ADB
    # This ensures we start from a clean state every time
    full_cleanup(config)

    # Seed progress file
    tracker = ProgressTracker(config.progress_file)

    # CRITICAL: Retry all failed jobs from previous runs
    # This ensures jobs that failed before get another chance
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
        os.remove(config.progress_file)
        if os.path.exists(config.progress_file + '.lock'):
            os.remove(config.progress_file + '.lock')

    if not tracker.exists() or force_reseed:
        if not accounts:
            logger.error("No accounts specified. Use --accounts phone1,phone2 to specify accounts")
            return {'error': 'no_accounts'}
        count = seed_progress_file(config, state_file, accounts)
        if count == 0:
            logger.error("No jobs to process. Check scheduler_state.json")
            return {'error': 'no_jobs'}

    # Show initial stats
    stats = tracker.get_stats()
    logger.info(f"Starting with {stats['pending']} pending jobs")

    # Initialize retry pass manager
    retry_mgr = RetryPassManager(tracker, retry_config)

    try:
        # Multi-pass retry loop
        result = PassResult.RETRYABLE_REMAINING

        while result == PassResult.RETRYABLE_REMAINING and not _shutdown_requested:
            # Start new pass
            pass_num = retry_mgr.start_new_pass()

            # Start workers for this pass
            processes = start_all_workers(config)

            # Monitor until pass complete
            monitor_workers(processes, config)

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
        # FULL CLEANUP on exit - stop phones, free ports, clear ADB
        full_cleanup(config)

    # Final stats
    final_stats = tracker.get_stats()
    failure_stats = tracker.get_failure_stats()

    logger.info("="*60)
    logger.info("FINAL RESULTS")
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


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Parallel Posting Orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with 3 workers
  python parallel_orchestrator.py --workers 3 --run

  # Check current status
  python parallel_orchestrator.py --status

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

    args = parser.parse_args()

    # Parse accounts list if provided
    accounts_list = None
    if args.accounts:
        accounts_list = [a.strip() for a in args.accounts.split(',') if a.strip()]

    config = get_config(num_workers=args.workers)

    if args.reset_day:
        logger.info("="*60)
        logger.info("DAILY RESET - Archiving progress file for new day")
        logger.info("="*60)
        success, message = reset_day(config.progress_file)
        if success:
            logger.info(message)
            logger.info("Ready for new day. Run with --run to start posting.")
        else:
            logger.error(message)
            sys.exit(1)

    elif args.retry_all_failed:
        # Standalone retry-all-failed command
        if not os.path.exists(config.progress_file):
            logger.error(f"Progress file not found: {config.progress_file}")
            sys.exit(1)

        tracker = ProgressTracker(config.progress_file)
        stats_before = tracker.get_stats()
        logger.info(f"Current stats: {stats_before['failed']} failed, {stats_before.get('retrying', 0)} retrying")

        count = tracker.retry_all_failed(include_non_retryable=args.retry_include_non_retryable)
        if count > 0:
            stats_after = tracker.get_stats()
            logger.info(f"Reset {count} failed jobs to retrying status")
            logger.info(f"New stats: {stats_after['failed']} failed, {stats_after.get('retrying', 0)} retrying")
        else:
            logger.info("No failed jobs found to retry")

    elif args.status:
        show_status(config)

    elif args.stop_all:
        logger.info("Stopping everything...")
        full_cleanup(config)
        logger.info("Done")

    elif args.seed_only:
        count = seed_progress_file(config, args.state_file, accounts_list)
        if count > 0:
            logger.info(f"Progress file ready with {count} jobs")
        else:
            logger.error("Failed to seed progress file")
            sys.exit(1)

    elif args.run:
        # SAFETY CHECK: --force-reseed requires --reset-day to prevent accidental mid-day reseeds
        # that could result in duplicate posts or exceeded daily limits
        if args.force_reseed and os.path.exists(config.progress_file):
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

        results = run_parallel_posting(
            num_workers=args.workers,
            state_file=args.state_file,
            force_reseed=args.force_reseed,
            force_kill_ports=args.force_kill_ports,
            accounts=accounts_list,
            retry_all_failed=True,  # Always retry failed jobs on start
            retry_include_non_retryable=args.retry_include_non_retryable,
            retry_config=retry_cfg
        )
        if results.get('error'):
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
