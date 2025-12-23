#!/usr/bin/env python3
"""
External watchdog for posting_scheduler.py

Monitors:
1. Is the scheduler PID from scheduler.lock still alive?
2. Has scheduler_live.log been updated in the last X minutes?

If either check fails, kills and restarts the scheduler.

Usage:
  python scheduler_watchdog.py              # Run once
  python scheduler_watchdog.py --loop       # Run continuously every 2 minutes
  python scheduler_watchdog.py --loop 5     # Run continuously every 5 minutes
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
SCRIPT_DIR = Path(__file__).parent
SCHEDULER_SCRIPT = SCRIPT_DIR / "posting_scheduler.py"
LOCK_FILE = SCRIPT_DIR / "scheduler.lock"
LOG_FILE = SCRIPT_DIR / "scheduler_live.log"
WATCHDOG_LOG = SCRIPT_DIR / "watchdog.log"

# Thresholds
MAX_LOG_STALE_MINUTES = 5  # Restart if log hasn't been updated in this many minutes
MAX_HEARTBEAT_STALE_MINUTES = 3  # Restart if heartbeat is stale


def log(msg: str):
    """Log to both console and file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(WATCHDOG_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def is_pid_alive(pid: int) -> bool:
    """Check if a process with given PID is running"""
    try:
        # Windows-specific check
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            shell=True
        )
        return str(pid) in result.stdout
    except Exception as e:
        log(f"Error checking PID {pid}: {e}")
        return False


def kill_process(pid: int) -> bool:
    """Kill a process by PID"""
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            text=True,
            shell=True
        )
        return "SUCCESS" in result.stdout or "not found" in result.stderr.lower()
    except Exception as e:
        log(f"Error killing PID {pid}: {e}")
        return False


def stop_all_phones():
    """Stop any running Geelark phones to prevent billing"""
    log("Stopping all running phones...")
    try:
        # Import and use GeelarkClient
        sys.path.insert(0, str(SCRIPT_DIR))
        from geelark_client import GeelarkClient

        client = GeelarkClient()
        stopped = 0
        for page in range(1, 20):
            result = client.list_phones(page=page, page_size=100)
            for phone in result['items']:
                if phone['status'] != 0:  # 0=stopped, 1=starting, 2=running  # Running
                    client.stop_phone(phone['id'])
                    log(f"  Stopped: {phone['serialName']}")
                    stopped += 1
            if len(result['items']) < 100:
                break
        log(f"  Total stopped: {stopped}")
        return stopped
    except Exception as e:
        log(f"Error stopping phones: {e}")
        return 0


def get_lock_info() -> dict:
    """Read scheduler.lock file"""
    if not LOCK_FILE.exists():
        return None
    try:
        with open(LOCK_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        log(f"Error reading lock file: {e}")
        return None


def get_log_mtime() -> datetime:
    """Get last modification time of scheduler_live.log"""
    if not LOG_FILE.exists():
        return None
    try:
        mtime = os.path.getmtime(LOG_FILE)
        return datetime.fromtimestamp(mtime)
    except Exception as e:
        log(f"Error getting log mtime: {e}")
        return None


def start_scheduler() -> int:
    """Start the scheduler and return the new PID"""
    log("Starting scheduler...")
    try:
        # Start scheduler in background
        process = subprocess.Popen(
            [sys.executable, str(SCHEDULER_SCRIPT), "--run"],
            cwd=str(SCRIPT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        log(f"  Started scheduler with PID {process.pid}")

        # Wait a moment for lock file to be created
        time.sleep(3)

        # Verify it started
        lock_info = get_lock_info()
        if lock_info:
            log(f"  Confirmed running: PID {lock_info['pid']}")
            return lock_info['pid']
        else:
            log("  Warning: Lock file not created yet")
            return process.pid
    except Exception as e:
        log(f"Error starting scheduler: {e}")
        return None


def check_and_restart() -> bool:
    """
    Check scheduler health and restart if needed.
    Returns True if scheduler is healthy, False if it was restarted.
    """
    log("=" * 50)
    log("Watchdog check starting...")

    # Check 1: Is there a lock file?
    lock_info = get_lock_info()
    if not lock_info:
        log("No lock file found - scheduler not running")
        stop_all_phones()
        start_scheduler()
        return False

    pid = lock_info['pid']
    last_heartbeat = datetime.fromisoformat(lock_info.get('last_heartbeat', lock_info['started']))

    log(f"Lock file: PID={pid}, last_heartbeat={last_heartbeat}")

    # Check 2: Is the PID alive?
    if not is_pid_alive(pid):
        log(f"PID {pid} is NOT alive - scheduler crashed!")
        stop_all_phones()
        LOCK_FILE.unlink(missing_ok=True)
        start_scheduler()
        return False

    # Check 3: Is heartbeat recent?
    heartbeat_age = datetime.now() - last_heartbeat
    if heartbeat_age > timedelta(minutes=MAX_HEARTBEAT_STALE_MINUTES):
        log(f"Heartbeat is stale ({heartbeat_age.total_seconds():.0f}s old) - scheduler frozen!")
        stop_all_phones()
        kill_process(pid)
        LOCK_FILE.unlink(missing_ok=True)
        start_scheduler()
        return False

    # Check 4: Is log file being updated?
    log_mtime = get_log_mtime()
    if log_mtime:
        log_age = datetime.now() - log_mtime
        log(f"Log file last updated: {log_age.total_seconds():.0f}s ago")

        if log_age > timedelta(minutes=MAX_LOG_STALE_MINUTES):
            log(f"Log is stale ({log_age.total_seconds():.0f}s old) - scheduler may be stuck!")
            # Don't restart just for stale log if heartbeat is OK
            # The scheduler might just be waiting between posts
            log("  (Heartbeat OK, not restarting - scheduler may be waiting)")

    log(f"Scheduler healthy: PID {pid} running, heartbeat {heartbeat_age.total_seconds():.0f}s ago")
    return True


def main():
    """Main entry point"""
    loop_mode = "--loop" in sys.argv
    loop_interval = 2  # minutes

    # Check for custom interval
    for i, arg in enumerate(sys.argv):
        if arg == "--loop" and i + 1 < len(sys.argv):
            try:
                loop_interval = int(sys.argv[i + 1])
            except ValueError:
                pass

    if loop_mode:
        log(f"Watchdog starting in loop mode (every {loop_interval} minutes)")
        log("Press Ctrl+C to stop")

        while True:
            try:
                check_and_restart()
                time.sleep(loop_interval * 60)
            except KeyboardInterrupt:
                log("Watchdog stopped by user")
                break
            except Exception as e:
                log(f"Watchdog error: {e}")
                time.sleep(60)  # Wait a minute before retrying
    else:
        # Single check
        check_and_restart()


if __name__ == "__main__":
    main()
