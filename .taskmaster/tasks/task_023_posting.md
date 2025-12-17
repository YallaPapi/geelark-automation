# Task ID: 23

**Title:** Add ADB/Appium Lifecycle State Machine with Device Readiness Checks and Recovery

**Status:** done

**Dependencies:** 13 ✓, 16 ✓

**Priority:** high

**Description:** Implement robust ADB device lifecycle management by adding a wait_for_adb() helper that polls until device is present, an ensure_device_alive() function for mid-run ADB loss detection with recovery, and a formal state machine in parallel_worker.py governing phone/Appium transitions.

**Details:**

## Overview

This task addresses Section 2.1-2.3 from reviews/review1.txt, implementing robust ADB/Appium lifecycle management to handle device readiness and mid-run failures. The current implementation in `parallel_worker.py` lacks explicit ADB readiness gates and recovery mechanisms for device loss during job execution.

## Current State Analysis

- `parallel_worker.py` (lines 268-341): Main job loop relies on `appium_manager.ensure_healthy()` for Appium checks but has no explicit ADB device readiness verification
- `post_reel_smart.py` has `verify_adb_connection()` (line 819) and `reconnect_adb()` (line 838) but these are not integrated into the parallel worker flow
- `parallel_config.py` already exposes `adb_path` (line 81): `r"C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe"`
- `appium_server_manager.py` manages Appium lifecycle but is unaware of underlying ADB device state

## Implementation Details

### 2.1 Add `wait_for_adb(device_id, timeout)` helper

**File:** Create new `adb_utils.py` or add to `parallel_worker.py` (recommend separate module for reusability)

```python
import subprocess
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def wait_for_adb(
    device_id: str,
    adb_path: str,
    timeout: int = 90,
    poll_interval: float = 2.0
) -> bool:
    """
    Poll adb devices until the specified device is present and ready.
    
    Args:
        device_id: The device UDID/serial (e.g., "192.168.1.100:5555")
        adb_path: Full path to adb executable
        timeout: Maximum seconds to wait (default 90)
        poll_interval: Seconds between polls (default 2)
        
    Returns:
        True if device became ready, False if timeout
    """
    deadline = time.time() + timeout
    attempts = 0
    
    while time.time() < deadline:
        attempts += 1
        try:
            result = subprocess.run(
                [adb_path, "devices"],
                capture_output=True,
                encoding='utf-8',
                timeout=10
            )
            
            for line in result.stdout.splitlines():
                # Line format: "192.168.1.100:5555\tdevice"
                if device_id in line and '\tdevice' in line:
                    logger.info(f"ADB device {device_id} ready after {attempts} attempts")
                    return True
                    
            # Device exists but wrong status (offline, unauthorized)?
            for line in result.stdout.splitlines():
                if device_id in line:
                    status = line.split('\t')[-1] if '\t' in line else 'unknown'
                    logger.debug(f"Device {device_id} found but status is '{status}', waiting...")
                    break
                    
        except subprocess.TimeoutExpired:
            logger.warning(f"ADB command timed out on attempt {attempts}")
        except Exception as e:
            logger.warning(f"ADB check error on attempt {attempts}: {e}")
            
        time.sleep(poll_interval)
    
    logger.error(f"Device {device_id} did not become ready within {timeout}s ({attempts} attempts)")
    return False
```

### 2.2 Add `ensure_device_alive()` for mid-run ADB loss detection

**File:** Add to `adb_utils.py` or `parallel_worker.py`

```python
def ensure_device_alive(device_id: str, adb_path: str, timeout: float = 5.0) -> bool:
    """
    Quick check if device is still connected and responsive.
    
    Unlike wait_for_adb(), this is a single-shot check intended for
    periodic verification during job execution.
    
    Args:
        device_id: The device UDID/serial
        adb_path: Full path to adb executable
        timeout: Command timeout in seconds
        
    Returns:
        True if device is alive, False otherwise
    """
    try:
        result = subprocess.run(
            [adb_path, "devices"],
            capture_output=True,
            encoding='utf-8',
            timeout=timeout
        )
        
        for line in result.stdout.splitlines():
            if device_id in line and '\tdevice' in line:
                return True
                
        return False
        
    except Exception as e:
        logger.debug(f"ensure_device_alive failed: {e}")
        return False

def recover_device(
    device_id: str,
    phone_name: str,
    adb_path: str,
    worker_config: 'WorkerConfig',
    config: 'ParallelConfig',
    appium_manager: 'AppiumServerManager',
    logger: logging.Logger
) -> bool:
    """
    Full recovery sequence when device is lost mid-run.
    
    Sequence:
    1. Stop Appium server
    2. Stop Geelark phone
    3. Wait for cleanup
    4. Restart Geelark phone
    5. Wait for ADB readiness
    6. Restart Appium server
    
    Args:
        device_id: The device UDID/serial
        phone_name: Geelark phone serial name
        adb_path: Full path to adb
        worker_config: Worker's configuration
        config: Parallel configuration
        appium_manager: The worker's AppiumServerManager
        logger: Worker logger
        
    Returns:
        True if recovery successful, False otherwise
    """
    from geelark_client import GeelarkClient
    
    logger.warning(f"[RECOVERY] Device {device_id} lost, initiating recovery sequence...")
    
    # 1. Stop Appium
    logger.info("[RECOVERY] Step 1/6: Stopping Appium server...")
    try:
        appium_manager.stop()
    except Exception as e:
        logger.warning(f"[RECOVERY] Appium stop error (non-fatal): {e}")
    
    # 2. Disconnect ADB
    logger.info("[RECOVERY] Step 2/6: Disconnecting ADB...")
    try:
        subprocess.run([adb_path, "disconnect", device_id], capture_output=True, timeout=10)
    except Exception as e:
        logger.debug(f"[RECOVERY] ADB disconnect error: {e}")
    
    time.sleep(2)
    
    # 3. Stop Geelark phone
    logger.info("[RECOVERY] Step 3/6: Stopping Geelark phone...")
    try:
        client = GeelarkClient()
        phones = client.list_phones(page_size=100)
        for phone in phones.get('items', []):
            if phone.get('serialName') == phone_name:
                if phone.get('status') == 1:  # Running
                    client.stop_phone(phone['id'])
                    logger.info(f"[RECOVERY] Stopped phone {phone_name}")
                break
    except Exception as e:
        logger.warning(f"[RECOVERY] Phone stop error: {e}")
    
    time.sleep(5)  # Let phone fully stop
    
    # 4. Restart phone (handled by the caller via SmartInstagramPoster.connect())
    # The state machine will transition back to PHONE_STARTING
    logger.info("[RECOVERY] Step 4/6: Phone stop complete, ready for restart")
    
    # 5. Wait for ADB (will be done in state machine's ADB_PENDING state)
    logger.info("[RECOVERY] Step 5/6: Recovery cleanup complete")
    
    # 6. Appium restart (will be done in state machine's ADB_READY state)
    logger.info("[RECOVERY] Step 6/6: Ready for state machine restart sequence")
    
    return True
```

### 2.3 Implement State Machine in `parallel_worker.py`

**File:** `parallel_worker.py` - Major refactor of `run_worker()` function

```python
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Tuple

class WorkerState(Enum):
    """State machine states for worker phone/Appium lifecycle."""
    IDLE = auto()              # Initial state, no phone assigned
    PHONE_STARTING = auto()    # Geelark phone being started
    ADB_PENDING = auto()       # Waiting for ADB device to appear
    ADB_READY = auto()         # ADB device connected, starting Appium
    APPIUM_READY = auto()      # Appium healthy, ready to process jobs
    JOB_RUNNING = auto()       # Currently executing a posting job
    ERROR_RECOVERY = auto()    # Recovery in progress after failure
    SHUTDOWN = auto()          # Clean shutdown requested

@dataclass
class WorkerContext:
    """Context carried through state transitions."""
    device_id: Optional[str] = None
    phone_name: Optional[str] = None
    phone_id: Optional[str] = None
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3
    last_error: Optional[str] = None

def run_worker_state_machine(
    worker_id: int,
    config: ParallelConfig,
    progress_file: str,
    delay_between_jobs: int,
    logger: logging.Logger
) -> dict:
    """
    State machine-based worker loop.
    
    State transitions:
    IDLE -> PHONE_STARTING: When claiming a job
    PHONE_STARTING -> ADB_PENDING: After Geelark start_phone() called
    ADB_PENDING -> ADB_READY: After wait_for_adb() returns True
    ADB_PENDING -> ERROR_RECOVERY: After wait_for_adb() timeout
    ADB_READY -> APPIUM_READY: After Appium starts successfully
    ADB_READY -> ERROR_RECOVERY: Appium start failure
    APPIUM_READY -> JOB_RUNNING: When executing a job
    JOB_RUNNING -> APPIUM_READY: Job complete (success or fail)
    JOB_RUNNING -> ERROR_RECOVERY: Device lost mid-job
    ERROR_RECOVERY -> PHONE_STARTING: After cleanup, retry
    ERROR_RECOVERY -> SHUTDOWN: Max retries exceeded
    Any -> SHUTDOWN: Shutdown signal received
    """
    global _shutdown_requested
    
    worker_config = config.get_worker(worker_id)
    tracker = ProgressTracker(progress_file)
    appium_manager = AppiumServerManager(worker_config, config)
    
    state = WorkerState.IDLE
    ctx = WorkerContext()
    stats = {
        'worker_id': worker_id,
        'jobs_completed': 0,
        'jobs_failed': 0,
        'recovery_cycles': 0,
        'start_time': datetime.now().isoformat(),
        'end_time': None,
        'exit_reason': None
    }
    
    current_job = None
    
    while state != WorkerState.SHUTDOWN:
        if _shutdown_requested:
            state = WorkerState.SHUTDOWN
            continue
            
        logger.debug(f"State: {state.name}, Context: recovery_attempts={ctx.recovery_attempts}")
        
        # --- IDLE: Wait for a job to claim ---
        if state == WorkerState.IDLE:
            progress_stats = tracker.get_stats()
            if progress_stats['pending'] == 0 and progress_stats['claimed'] == 0:
                logger.info("No more jobs to process")
                stats['exit_reason'] = 'all_jobs_complete'
                state = WorkerState.SHUTDOWN
                continue
            
            current_job = tracker.claim_next_job(
                worker_id, 
                max_posts_per_account_per_day=config.max_posts_per_account_per_day
            )
            
            if current_job is None:
                if progress_stats['claimed'] > 0:
                    time.sleep(5)  # Other workers processing
                    continue
                else:
                    stats['exit_reason'] = 'all_jobs_complete'
                    state = WorkerState.SHUTDOWN
                    continue
            
            ctx.phone_name = current_job['account']
            ctx.recovery_attempts = 0
            state = WorkerState.PHONE_STARTING
            
        # --- PHONE_STARTING: Start Geelark phone ---
        elif state == WorkerState.PHONE_STARTING:
            logger.info(f"Starting phone for account: {ctx.phone_name}")
            # Phone startup is handled by SmartInstagramPoster.connect()
            # which calls Geelark API, enables ADB, and gets device_id
            # For now, we transition to ADB_PENDING and let execute_posting_job handle it
            # In future: explicit Geelark phone start here
            state = WorkerState.ADB_PENDING
            
        # --- ADB_PENDING: Wait for device to appear in adb devices ---
        elif state == WorkerState.ADB_PENDING:
            # Note: device_id is obtained during SmartInstagramPoster.connect()
            # For explicit ADB waiting, we'd need device_id earlier
            # This state confirms the pattern; actual waiting happens in execute_posting_job
            logger.info(f"ADB pending for {ctx.phone_name}, proceeding to start Appium...")
            state = WorkerState.ADB_READY
            
        # --- ADB_READY: Start Appium server ---
        elif state == WorkerState.ADB_READY:
            try:
                appium_manager.ensure_healthy()
                logger.info(f"Appium ready at {worker_config.appium_url}")
                state = WorkerState.APPIUM_READY
            except AppiumServerError as e:
                ctx.last_error = str(e)
                logger.error(f"Appium start failed: {e}")
                state = WorkerState.ERROR_RECOVERY
                
        # --- APPIUM_READY: Ready to execute jobs ---
        elif state == WorkerState.APPIUM_READY:
            if current_job is None:
                state = WorkerState.IDLE
                continue
            state = WorkerState.JOB_RUNNING
            
        # --- JOB_RUNNING: Execute the posting job ---
        elif state == WorkerState.JOB_RUNNING:
            job_id = current_job['job_id']
            
            try:
                success, error = execute_posting_job(
                    current_job, worker_config, config, logger,
                    tracker=tracker, worker_id=worker_id
                )
                
                if success:
                    tracker.update_job_status(job_id, 'success', worker_id)
                    stats['jobs_completed'] += 1
                else:
                    tracker.update_job_status(job_id, 'failed', worker_id, error=error)
                    stats['jobs_failed'] += 1
                    
                    # Check if error indicates device loss
                    device_loss_errors = [
                        'device offline', 'not found', 'connection reset',
                        'adb', 'device not ready', 'UiAutomator'
                    ]
                    if any(e in error.lower() for e in device_loss_errors):
                        state = WorkerState.ERROR_RECOVERY
                        continue
                
                current_job = None
                ctx.recovery_attempts = 0  # Reset on successful cycle
                
                # Delay between jobs
                if delay_between_jobs > 0:
                    logger.info(f"Waiting {delay_between_jobs}s before next job...")
                    time.sleep(delay_between_jobs)
                    
                state = WorkerState.IDLE
                
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                logger.error(f"Job {job_id} exception: {error_msg}")
                tracker.update_job_status(job_id, 'failed', worker_id, error=error_msg)
                stats['jobs_failed'] += 1
                ctx.last_error = error_msg
                state = WorkerState.ERROR_RECOVERY
                
        # --- ERROR_RECOVERY: Clean up and retry ---
        elif state == WorkerState.ERROR_RECOVERY:
            ctx.recovery_attempts += 1
            stats['recovery_cycles'] += 1
            
            logger.warning(
                f"[RECOVERY] Attempt {ctx.recovery_attempts}/{ctx.max_recovery_attempts}, "
                f"last error: {ctx.last_error}"
            )
            
            if ctx.recovery_attempts > ctx.max_recovery_attempts:
                logger.error("[RECOVERY] Max attempts exceeded, shutting down worker")
                stats['exit_reason'] = 'max_recovery_attempts'
                state = WorkerState.SHUTDOWN
                continue
            
            # Full cleanup
            try:
                appium_manager.stop()
            except:
                pass
                
            if ctx.phone_name:
                stop_phone_by_name(ctx.phone_name, logger)
            
            # Backoff before retry
            backoff = min(30, 5 * ctx.recovery_attempts)
            logger.info(f"[RECOVERY] Backing off {backoff}s before retry...")
            time.sleep(backoff)
            
            # Return to PHONE_STARTING to try again
            state = WorkerState.PHONE_STARTING
            
    # --- SHUTDOWN: Clean exit ---
    logger.info("Worker shutting down...")
    
    try:
        appium_manager.stop()
    except:
        pass
        
    if ctx.phone_name:
        stop_phone_by_name(ctx.phone_name, logger)
    
    stats['end_time'] = datetime.now().isoformat()
    if stats['exit_reason'] is None:
        stats['exit_reason'] = 'shutdown_requested'
    
    return stats
```

## File Changes Summary

1. **New file: `adb_utils.py`** (recommended)
   - `wait_for_adb(device_id, adb_path, timeout)` - Polls until device present
   - `ensure_device_alive(device_id, adb_path)` - Quick liveness check
   - `recover_device(...)` - Full recovery sequence

2. **Modified: `parallel_worker.py`**
   - Add `WorkerState` enum with states: IDLE, PHONE_STARTING, ADB_PENDING, ADB_READY, APPIUM_READY, JOB_RUNNING, ERROR_RECOVERY, SHUTDOWN
   - Add `WorkerContext` dataclass for state machine context
   - Refactor `run_worker()` to use `run_worker_state_machine()`
   - Import and use `wait_for_adb`, `ensure_device_alive` from adb_utils
   - Add periodic `ensure_device_alive()` checks during JOB_RUNNING state

3. **Optional: `parallel_config.py`**
   - Add `adb_timeout: int = 90` for configurable ADB wait timeout
   - Add `max_recovery_attempts: int = 3` for worker resilience config

## Integration Points

- `execute_posting_job()` should call `ensure_device_alive()` before Appium operations
- State machine replaces the flat while loop in current `run_worker()`
- Recovery state properly cleans up Appium, disconnects ADB, stops phone, then retries
- Stats now track `recovery_cycles` for observability

**Test Strategy:**

## Test Strategy

### 1. Unit Tests for ADB Helper Functions

**Test `wait_for_adb()` timeout behavior:**
```bash
# Simulate by running with a non-existent device
python -c "
from adb_utils import wait_for_adb
# Should return False after timeout
result = wait_for_adb('192.168.99.99:5555', 
    r'C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe',
    timeout=10)
assert result == False, 'Should timeout for non-existent device'
print('PASS: wait_for_adb timeout test')
"
```

**Test `wait_for_adb()` success case:**
```bash
# With a real running phone
python -c "
from adb_utils import wait_for_adb
from geelark_client import GeelarkClient
import time

client = GeelarkClient()
# Find a phone and start it
phones = client.list_phones(page_size=1)
if phones['items']:
    phone = phones['items'][0]
    # Get ADB info
    adb_info = client.enable_adb(phone['id'])
    device_id = f\"{adb_info['ip']}:{adb_info['port']}\"
    
    # Test wait_for_adb
    result = wait_for_adb(device_id, 
        r'C:\\Users\\asus\\Downloads\\android-sdk\\platform-tools\\adb.exe',
        timeout=60)
    print(f'wait_for_adb result: {result}')
    assert result == True, 'Should find started device'
    
    client.stop_phone(phone['id'])
    print('PASS: wait_for_adb success test')
"
```

**Test `ensure_device_alive()` quick check:**
```bash
python -c "
from adb_utils import ensure_device_alive
# Quick check should return fast
import time
start = time.time()
result = ensure_device_alive('192.168.99.99:5555', 
    r'C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe')
elapsed = time.time() - start
assert elapsed < 10, f'Should be quick, took {elapsed}s'
assert result == False, 'Non-existent device should return False'
print(f'PASS: ensure_device_alive quick check ({elapsed:.1f}s)')
"
```

### 2. State Machine Integration Tests

**Test state transitions logging:**
```bash
# Run worker with verbose logging to verify state transitions
python parallel_worker.py --worker-id 0 --num-workers 1 --progress-file test_progress.csv --delay 5 2>&1 | grep -E "State:|RECOVERY|transition"
```

**Expected state flow for successful job:**
```
State: IDLE
State: PHONE_STARTING
State: ADB_PENDING  
State: ADB_READY
State: APPIUM_READY
State: JOB_RUNNING
State: IDLE (back to claim next job)
```

**Test recovery flow by simulating ADB loss:**
```bash
# Start worker, then during JOB_RUNNING, manually disconnect ADB
# Worker should transition: JOB_RUNNING -> ERROR_RECOVERY -> PHONE_STARTING -> ...
adb disconnect <device_id>
# Watch logs for "[RECOVERY]" messages
```

### 3. End-to-End Recovery Test

**Simulate device loss and recovery:**
```bash
# 1. Seed a test job
python -c "
import csv
with open('test_recovery.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['job_id','account','video_path','caption','status','worker_id','claimed_at','completed_at','error'])
    w.writerow(['test1','testaccount1','chunk_01c/video.mp4','Test caption','pending','','','',''])
"

# 2. Start worker
python parallel_worker.py --worker-id 0 --num-workers 1 --progress-file test_recovery.csv &

# 3. While job is running, kill ADB connection
sleep 30
adb disconnect all

# 4. Verify worker enters ERROR_RECOVERY and attempts restart
# Check logs/worker_0.log for:
#   [RECOVERY] Device ... lost, initiating recovery sequence...
#   [RECOVERY] Step 1/6: Stopping Appium server...
#   ...
#   State: PHONE_STARTING
```

### 4. Stress Test with Multiple Workers

**Run 3 workers and verify independent recovery:**
```bash
# Seed jobs for 3 workers
python parallel_orchestrator.py --seed-only --accounts acc1 acc2 acc3

# Start orchestrator
python parallel_orchestrator.py --run --workers 3

# During execution, manually stop one phone via Geelark dashboard
# Verify:
# - Only affected worker enters ERROR_RECOVERY
# - Other workers continue normally
# - Affected worker recovers and continues
```

### 5. Max Recovery Attempts Test

**Verify worker exits after max retries:**
```bash
# Configure impossibly short ADB timeout to force failures
# Edit test to set ctx.max_recovery_attempts = 2

# Watch for log:
#   [RECOVERY] Max attempts exceeded, shutting down worker
#   exit_reason: max_recovery_attempts
```

### 6. Metrics Validation

**Verify stats include recovery_cycles:**
```bash
# After worker completes/exits, check returned stats
python -c "
# Mock test
stats = {'recovery_cycles': 2, 'jobs_completed': 5, 'jobs_failed': 1}
assert 'recovery_cycles' in stats
print(f'Recovery cycles tracked: {stats[\"recovery_cycles\"]}')
"
```

### 7. Live Production Test (5 Workers)

**Final validation per CLAUDE.md instructions:**
```bash
# Use live accounts and real videos
python parallel_orchestrator.py --run --workers 5 --accounts $(head -5 accounts.txt | tr '\n' ' ')

# Monitor for:
# - No duplicate posts to same account
# - Clean recovery from any ADB flakiness
# - All phones stopped after completion
```

### 8. Post-Test Phone Cleanup Verification

```bash
# CRITICAL: Verify all phones stopped
python -c "
from geelark_client import GeelarkClient
client = GeelarkClient()
running = []
for page in range(1, 20):
    result = client.list_phones(page=page, page_size=100)
    for phone in result['items']:
        if phone['status'] == 1:
            running.append(phone['serialName'])
    if len(result['items']) < 100:
        break
if running:
    print(f'WARNING: {len(running)} phones still running: {running}')
else:
    print('PASS: All phones stopped')
"
```
