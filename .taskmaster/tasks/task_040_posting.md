# Task ID: 40

**Title:** Consolidate ADB operations into DeviceConnectionManager

**Status:** done

**Dependencies:** 37 ✓, 25 ✓

**Priority:** medium

**Description:** Extract all ADB subprocess calls from SmartInstagramPoster and route them through DeviceConnectionManager, establishing a clear boundary where the posting engine never calls subprocess directly for ADB operations.

**Details:**

## Current State Analysis

### SmartInstagramPoster.adb() - Lines 113-120 in post_reel_smart.py:
```python
def adb(self, cmd, timeout=30):
    """Run ADB shell command"""
    result = subprocess.run(
        [ADB_PATH, "-s", self.device, "shell", cmd],
        capture_output=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""
```

### DeviceConnectionManager.adb_command() - Lines 53-62 in device_connection.py:
```python
def adb_command(self, cmd: str, timeout: int = 30) -> str:
    """Run ADB shell command on the connected device."""
    if not self.device:
        raise Exception("No device connected - call connect() first")
    result = subprocess.run(
        [ADB_PATH, "-s", self.device, "shell", cmd],
        capture_output=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""
```

Both methods are functionally identical. SmartInstagramPoster already has `self._conn` which is a DeviceConnectionManager instance.

## Implementation Steps

### Step 1: Update SmartInstagramPoster.adb() to delegate
Replace lines 113-120 in `post_reel_smart.py`:
```python
def adb(self, cmd, timeout=30):
    """Run ADB shell command - delegates to DeviceConnectionManager"""
    return self._conn.adb_command(cmd, timeout=timeout)
```

### Step 2: Remove subprocess import
Remove line 23 from `post_reel_smart.py`:
```python
import subprocess  # REMOVE THIS LINE
```

### Step 3: Verify all ADB callers work unchanged
The following calls in `post_reel_smart.py` use `self.adb()` and should continue working:
- Line 459: `self.adb("dumpsys input_method | grep mInputShown")` in `is_keyboard_visible()`
- Line 464: `self.adb("dumpsys window | grep -i keyboard")` in `is_keyboard_visible()`
- Line 469: `self.adb("dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'")` in `is_keyboard_visible()`
- Line 586: `self.adb("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE...")` in `upload_video()`
- Lines 590-591: `self.adb("rm -f /sdcard/DCIM/Camera/IMG_*.png")` and screenshot cleanup in `upload_video()`
- Line 612: `self.adb("am force-stop com.instagram.android")` in `post()`
- Line 614: `self.adb("monkey -p com.instagram.android 1")` in `post()`
- Lines 695, 697, 771, 773: More `adb input swipe` and app control commands in `post()`
- Lines 804, 806: App restart commands in loop recovery
- Line 822: `self.adb("rm -f /sdcard/Download/*.mp4")` in `cleanup()`

## Architecture After Change

```
Before:
SmartInstagramPoster.adb() -> subprocess.run() [direct infrastructure coupling]

After:
SmartInstagramPoster.adb() -> self._conn.adb_command() -> subprocess.run()
                              [single point of ADB access via DeviceConnectionManager]
```

## Benefits
1. **Clear boundary**: SmartInstagramPoster becomes a pure posting logic class
2. **Single responsibility**: DeviceConnectionManager owns ALL device communication
3. **Testability**: Can mock DeviceConnectionManager for unit testing SmartInstagramPoster
4. **Consistency**: All ADB operations go through the same path with consistent error handling

**Test Strategy:**

## Test Strategy

### 1. Syntax and Import Verification
```bash
# Verify the file has no syntax errors and imports correctly
python -c "from post_reel_smart import SmartInstagramPoster; print('Import successful')"
```

### 2. Verify subprocess is NOT imported in post_reel_smart.py
```bash
# This should return empty (no matches)
python -c "
with open('post_reel_smart.py') as f:
    content = f.read()
    lines = [l for l in content.split('\n') if 'import subprocess' in l and not l.strip().startswith('#')]
    if lines:
        print('FAIL: subprocess still imported:', lines)
        exit(1)
    print('PASS: subprocess not imported')
"
```

### 3. Verify adb() method delegates to DeviceConnectionManager
```bash
# Inspect the adb method to confirm it calls self._conn.adb_command
python -c "
import inspect
from post_reel_smart import SmartInstagramPoster
source = inspect.getsource(SmartInstagramPoster.adb)
if 'self._conn.adb_command' in source:
    print('PASS: adb() delegates to self._conn.adb_command()')
else:
    print('FAIL: adb() does not delegate to DeviceConnectionManager')
    print(source)
    exit(1)
"
```

### 4. Integration Test - Existing Scripts Work Unchanged
```bash
# Test that posting_scheduler.py still imports and runs
python -c "from posting_scheduler import PostingScheduler; print('PostingScheduler import OK')"

# Test that parallel_worker.py still imports and runs
python -c "from parallel_worker import ParallelWorker; print('ParallelWorker import OK')"

# Test that parallel_orchestrator.py still imports and runs
python -c "from parallel_orchestrator import run_orchestrator; print('Orchestrator import OK')"
```

### 5. Manual Test - Full Posting Flow (Optional)
```bash
# Run a single phone posting test to verify all ADB commands work
# This requires a running Appium server and available Geelark phone
python post_reel_smart.py <test_phone_name> <test_video.mp4> "Test caption"
```

### 6. Verify DeviceConnectionManager.adb_command() Still Works
```bash
# Unit test the underlying adb_command method
python -c "
from device_connection import DeviceConnectionManager
# Just verify the method exists and has correct signature
import inspect
sig = inspect.signature(DeviceConnectionManager.adb_command)
params = list(sig.parameters.keys())
assert 'cmd' in params, 'Missing cmd parameter'
assert 'timeout' in params, 'Missing timeout parameter'
print('PASS: DeviceConnectionManager.adb_command() has correct signature')
"
```

### 7. Regression Check - No Other subprocess Usages
```bash
# Ensure no stray subprocess calls remain in post_reel_smart.py
grep -n "subprocess" post_reel_smart.py && echo "FAIL: Found subprocess references" || echo "PASS: No subprocess references"
```
