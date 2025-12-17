# Task ID: 18

**Title:** Fix Appium Connection Failures with Device-Ready Checks and Thread Cleanup

**Status:** cancelled

**Dependencies:** 13 ✓, 16 ✓, 17 ✓

**Priority:** medium

**Description:** Resolve Appium connection instability by ensuring device readiness before glogin execution, fixing ThreadPoolExecutor cleanup to prevent orphaned sessions, and managing stale ADB connections through robust connect() flow improvements.

**Details:**

Implement comprehensive fixes for the three identified Appium connection failure root causes following Appium best practices for ADB stability and resource management[1][2][6].

## 1. Device Readiness Check Before glogin (Primary Fix)

**Current Problem**: glogin executes before ADB reports device as 'device' status, causing connection failures[1].

**Implementation**:
```python
# In connect_appium() or connect() flow (~lines 730+ from Task 13)
import subprocess
import time

from typing import Optional

def wait_for_device_ready(udid: str, timeout: int = 60) -> bool:
    """Wait for device to report 'device' status in ADB"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        result = subprocess.run(
            ['adb', '-s', udid, 'get-state'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and 'device' in result.stdout.strip().lower():
            return True
        time.sleep(2)
    return False

def safe_glogin(udid: str) -> None:
    """Only run glogin after device is confirmed ready"""
    if not wait_for_device_ready(udid):
        raise UiAutomatorStartupError(f"Device {udid} never reached 'device' state")
    # Run glogin subprocess here (existing logic)
    subprocess.run(['glogin', udid], check=True)
```

**Integration**: Call `safe_glogin(self.device_udid)` **before** Appium driver initialization in `connect_appium()`.

## 2. Fix/Remove ThreadPoolExecutor Wrapper

**Current Problem**: ThreadPoolExecutor timeouts leave orphaned Appium sessions/threads[6].

**Best Practice**: Use context managers for guaranteed cleanup. Remove ThreadPoolExecutor wrapper entirely[6].

**Implementation**:
```python
# REPLACE ThreadPoolExecutor wrapper pattern with direct context-managed sessions

class AppiumSessionManager:
    def __enter__(self):
        self.driver = self.connect_appium(retries=3)
        return self.driver
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Guaranteed cleanup - even on exceptions/timeouts"""
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
                # Force ADB session cleanup
                subprocess.run(['adb', 'kill-server'])
                subprocess.run(['adb', 'start-server'])
            except Exception as e:
                logger.warning(f"Cleanup failed: {e}")

# Usage in posting logic:
with AppiumSessionManager() as driver:
    # All automation here
    pass  # Auto-cleanup guaranteed
```

## 3. Stale ADB Connection Management

**Implementation**:
```python
def refresh_adb_connection(udid: Optional[str] = None) -> None:
    """Kill/restart ADB server to clear stale connections[1][2]"""
    subprocess.run(['adb', 'kill-server'])
    time.sleep(2)
    subprocess.run(['adb', 'start-server'])
    if udid:
        # Wait for specific device
        wait_for_device_ready(udid)

# Call refresh_adb_connection() at start of connect_appium() and on UiAutomatorStartupError
```

## 4. Updated connect_appium() Flow
```python
def connect_appium(self, retries=3):
    for attempt in range(retries):
        try:
            refresh_adb_connection(self.device_udid)
            safe_glogin(self.device_udid)
            
            # Existing Appium connection logic with 10s UiAutomator2 timeout (Task 17)
            options = UiAutomator2Options()
            options.set_capability('uiautomator2ServerLaunchTimeout', 10000)  # 10s
            self.driver = u2.connect(options)
            return self.driver
        except (UiAutomatorStartupError, Exception) as e:
            logger.warning(f"Attempt {attempt+1} failed: {e}")
            if attempt == retries - 1:
                raise
            time.sleep(5)
```

**Dependencies**: Builds directly on Task 13 (connect_appium() structure, UiAutomatorStartupError), Task 17 (10s timeout), Task 16 (ADB env vars).[1][2]

**Test Strategy:**

**Comprehensive Test Strategy** (Critical for production stability)

### 1. Device Readiness Tests
```bash
# Test 1: Simulate offline→online transition
adb disconnect <udid>
sleep 5
# Start device connection
python -m pytest test_appium_connect.py::test_wait_device_ready
```
- Verify `wait_for_device_ready()` polls correctly
- Confirm `safe_glogin()` blocks until 'device' state
- Test 60s timeout raises `UiAutomatorStartupError`

### 2. ThreadPoolExecutor Replacement Tests
- Create unit test simulating timeout during session
```python
from contextlib import contextmanager

@contextmanager
def failing_appium():
    yield
    raise TimeoutError("Simulated timeout")

# Verify __exit__ still executes cleanup
```
- Confirm `driver.quit()` and `adb kill-server` called even on exceptions

### 3. End-to-End Connection Tests
```bash
# Test full connect() flow 50x
for i in {1..50}; do
    python test_appium_stability.py --device <udid> || echo "FAIL $i"
done
```
**Success Criteria**:
- 100% success rate (0 connection failures)
- No orphaned Appium processes (`ps aux | grep appium`)
- No stale ADB connections (`adb devices -l` shows clean list)

### 4. ADB Stale Connection Tests
```bash
# Force stale connections
adb kill-server
adb start-server
# Run multiple parallel sessions
pytest test_adb_cleanup.py -n auto
```
- Verify `refresh_adb_connection()` restores clean state
- Confirm no 'offline' devices after cleanup

### 5. Integration with Existing Codebase
- Run full scheduler loop (Task 15) for 2+ hours
- Monitor `batch_results_*.csv` for zero Appium connection errors
- Validate no lockfile/heartbeat issues (Task 15)

**Tools**:
- `lsof -i :5037` (ADB port conflicts)
- `ps aux | grep -E 'appium|glogin'` (orphaned processes)
- Appium logs with `--log-level debug`
