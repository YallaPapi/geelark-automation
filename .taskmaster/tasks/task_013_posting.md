# Task ID: 13

**Title:** Apply Appium stability fixes with extended timeouts and crash recovery

**Status:** done

**Dependencies:** 11 ✓, 12 ✓

**Priority:** medium

**Description:** Improve Appium connection reliability in post_reel_smart.py by adding missing timeout capabilities, increasing existing timeouts, implementing phone restart logic for UiAutomator2 crashes, and creating a typed exception for startup failures.

**Details:**

## Implementation Details

### 1. Create typed UiAutomatorStartupError exception (top of file, after imports ~line 35)

```python
class UiAutomatorStartupError(Exception):
    """Raised when UiAutomator2 fails to start on the device"""
    pass
```

### 2. Update connect_appium() function (lines 730-763) with new capabilities

Add these capabilities to the `options` object:

```python
def connect_appium(self, retries=3):
    """Connect Appium driver - REQUIRED for automation to work"""
    print("Connecting Appium driver...")

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.device_name = self.device
    options.udid = self.device
    options.no_reset = True
    options.new_command_timeout = 60
    
    # Extended timeouts for stability (Android 15 devices need longer)
    options.set_capability("appium:uiautomator2ServerLaunchTimeout", 90000)  # NEW: 90s (was missing, defaulted to 30s)
    options.set_capability("appium:uiautomator2ServerInstallTimeout", 120000)  # INCREASED: 120s (was 60s)
    options.set_capability("appium:adbExecTimeout", 120000)  # INCREASED: 120s (was 30s)
    options.set_capability("appium:androidDeviceReadyTimeout", 60000)  # NEW: 60s device ready wait

    last_error = None
    for attempt in range(retries):
        try:
            self.appium_driver = webdriver.Remote(
                command_executor=APPIUM_SERVER,
                options=options
            )
            platform_ver = self.appium_driver.capabilities.get('platformVersion', 'unknown')
            print(f"  Appium connected! (Android {platform_ver})")
            return True
        except Exception as e:
            last_error = e
            print(f"  Appium connection failed (attempt {attempt + 1}/{retries}): {e}")
            self.appium_driver = None
            
            # Check if UiAutomator2 crashed - may need phone restart
            if self.is_uiautomator2_crash(e):
                print(f"  [RECOVERY] UiAutomator2 crash detected, attempting phone restart...")
                self._restart_phone_for_recovery()
            
            if attempt < retries - 1:
                print(f"  Retrying in 15 seconds...")  # INCREASED: 15s (was 5s)
                time.sleep(15)

    # All retries failed - raise typed exception
    raise UiAutomatorStartupError(f"Appium connection failed after {retries} attempts: {last_error}")
```

### 3. Add phone restart recovery method (new method in SmartInstagramPoster class)

Add this method after `reconnect_appium()` (around line 84):

```python
def _restart_phone_for_recovery(self):
    """Restart the Geelark phone to recover from UiAutomator2 crash"""
    if not self.phone_id:
        print("    Cannot restart phone - phone_id not set")
        return False
    
    try:
        print("    Stopping phone...")
        self.client.stop_phone(self.phone_id)
        time.sleep(5)
        
        print("    Starting phone...")
        self.client.start_phone(self.phone_id)
        
        # Wait for phone to boot (similar to connect() logic)
        print("    Waiting for phone to boot...")
        for i in range(60):
            time.sleep(2)
            status_result = self.client.get_phone_status([self.phone_id])
            items = status_result.get("successDetails", [])
            if items and items[0].get("status") == 0:
                print(f"    Phone ready after restart! (took ~{(i+1)*2}s)")
                break
            if i % 5 == 0:
                print(f"    Booting... ({(i+1)*2}s)")
        else:
            print("    Warning: Phone boot timeout after restart")
            return False
        
        # Re-enable ADB after restart
        time.sleep(3)
        print("    Re-enabling ADB...")
        self.client.enable_adb(self.phone_id)
        time.sleep(5)
        
        # Reconnect ADB
        adb_info = self.client.get_adb_info(self.phone_id)
        self.device = f"{adb_info['ip']}:{adb_info['port']}"
        password = adb_info['pwd']
        
        import subprocess
        subprocess.run([ADB_PATH, "connect", self.device], capture_output=True)
        self.adb(f"glogin {password}")
        time.sleep(3)
        
        print("    Phone restart recovery complete")
        return True
        
    except Exception as e:
        print(f"    Phone restart failed: {e}")
        return False
```

### 4. Update reconnect_appium() to use new exception (line 74-84)

```python
def reconnect_appium(self):
    """Reconnect Appium driver after UiAutomator2 crash"""
    print("  [RECOVERY] Reconnecting Appium driver...")
    try:
        if self.appium_driver:
            self.appium_driver.quit()
    except:
        pass
    self.appium_driver = None
    time.sleep(2)
    try:
        return self.connect_appium()
    except UiAutomatorStartupError:
        # If reconnect also fails, try phone restart
        if self._restart_phone_for_recovery():
            return self.connect_appium()
        raise
```

### Summary of Changes

| Item | Before | After |
|------|--------|-------|
| `uiautomator2ServerLaunchTimeout` | Missing (30s default) | 90000ms |
| `uiautomator2ServerInstallTimeout` | 60000ms | 120000ms |
| `adbExecTimeout` | 30000ms | 120000ms |
| `androidDeviceReadyTimeout` | Missing | 60000ms |
| Retry sleep | 5s | 15s |
| Phone restart on crash | Not implemented | Implemented |
| Typed exception | Generic Exception | UiAutomatorStartupError |

### Files Modified
- `post_reel_smart.py`: Add exception class, update `connect_appium()`, add `_restart_phone_for_recovery()`, update `reconnect_appium()`

**Test Strategy:**

## Test Strategy

### 1. Unit Tests for Exception Class
- Verify `UiAutomatorStartupError` can be raised and caught
- Verify it inherits from `Exception`
- Verify error message is preserved correctly

### 2. Timeout Configuration Tests
- Start Appium with a mock device and verify the capabilities are set correctly:
  - `uiautomator2ServerLaunchTimeout == 90000`
  - `uiautomator2ServerInstallTimeout == 120000`
  - `adbExecTimeout == 120000`
  - `androidDeviceReadyTimeout == 60000`
- Log the capabilities object before connection to verify values

### 3. Retry Logic Tests
- Mock Appium connection failures and verify:
  - Retry happens 3 times
  - Sleep between retries is 15 seconds (measure with time.time())
  - `UiAutomatorStartupError` is raised after all retries fail

### 4. Phone Restart Recovery Tests
- Mock `is_uiautomator2_crash()` to return `True`
- Verify `_restart_phone_for_recovery()` is called
- Mock GeelarkClient methods (`stop_phone`, `start_phone`, `get_phone_status`, `enable_adb`, `get_adb_info`)
- Verify the correct sequence of recovery calls

### 5. Integration Test with Real Device
```bash
# Test on a Geelark Android 15 device
python -c "
from post_reel_smart import SmartInstagramPoster

poster = SmartInstagramPoster('test_phone_name')
poster.connect()

# Verify capabilities by checking the driver
caps = poster.appium_driver.capabilities
print(f'Platform: {caps.get(\"platformVersion\")}')
print(f'Appium connected successfully with extended timeouts')

poster.cleanup()
"
```

### 6. Crash Recovery Simulation
- Force a UiAutomator2 crash by killing the server process
- Verify the recovery logic kicks in:
  ```bash
  # In a separate terminal while test is running:
  adb shell "pkill -f uiautomator"
  ```
- Observe that phone restart and Appium reconnection occur

### 7. End-to-End Test
- Run full posting flow: `python post_reel_smart.py <phone> <video> <caption>`
- Monitor logs for timeout-related errors
- Verify no more "30s timeout" errors appear
- Verify successful connection even under slow network conditions

### 8. Regression Testing
- Run the existing test suite to ensure no regressions
- Verify `posting_scheduler.py` still works with the updated `connect_appium()`
- Test with multiple concurrent phones to verify stability
