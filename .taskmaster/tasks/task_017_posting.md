# Task ID: 17

**Title:** Reduce UiAutomator2 launch timeout from 90s to 10s

**Status:** done

**Dependencies:** 13 ✓

**Priority:** medium

**Description:** Optimize the Appium UiAutomator2 server launch timeout based on the observation that instrumentation either starts immediately (~1s) or times out completely - there is no middle ground, so waiting 90 seconds on failure wastes time unnecessarily.

**Details:**

## Background

Analysis documented in `geelark_uiautomator2_timeout_report.txt` reveals a **binary behavior pattern** for UiAutomator2 initialization on Geelark cloud phones:

- **Success case**: Instrumentation starts in ~1 second (observed: 1104ms)
- **Failure case**: Times out after the full timeout period (previously 90s)
- **No middle ground**: There are no cases where initialization takes 30s, 50s, or any intermediate time

This means the previous 90-second timeout was wasteful - if UiAutomator2 doesn't start within a few seconds, it won't start at all until retry.

## Implementation

In `post_reel_smart.py`, update the `connect_appium()` method (around line 743):

### Before (Task 13 implementation):
```python
options.set_capability("appium:uiautomator2ServerLaunchTimeout", 90000)  # 90s
```

### After:
```python
options.set_capability("appium:uiautomator2ServerLaunchTimeout", 10000)  # 10s for launch - binary: works in ~1s or not at all
```

## Rationale

1. **Time savings**: Failed attempts now waste 10s instead of 90s (80s saved per failure)
2. **Faster retry cycle**: With 15s delay between retries, a full 3-attempt cycle takes:
   - Before: 90s + 15s + 90s + 15s + 90s = 300s (5 minutes)
   - After: 10s + 15s + 10s + 15s + 10s = 60s (1 minute)
3. **No false negatives**: 10s is still generous given the observed ~1s success time
4. **Buffer for edge cases**: 10s provides 10x buffer over the ~1s typical success time

## Other timeouts remain unchanged

The following timeouts in `connect_appium()` should NOT be reduced as they serve different purposes:

- `newCommandTimeout: 120` - For slow cloud phone operations during the session
- `adbExecTimeout: 120000` - For slow ADB commands over network tunnels
- `uiautomator2ServerInstallTimeout: 120000` - First-time APK installation can be slow
- `androidDeviceReadyTimeout: 60` - Device boot/ready detection

Only `uiautomator2ServerLaunchTimeout` exhibits the binary behavior pattern.

**Test Strategy:**

## Test Strategy

### 1. Verify timeout value is correctly set

Run a quick Appium session and check the capabilities:
```bash
python -c "
from post_reel_smart import SmartInstagramPoster
poster = SmartInstagramPoster('test_phone')
# Connect to a phone and check capabilities
poster.connect()
caps = poster.appium_driver.capabilities
print(f'Launch timeout: {caps.get(\"uiautomator2ServerLaunchTimeout\", \"not set\")}')
poster.cleanup()
"
```

### 2. Timing verification on success

Start a cloud phone and time the Appium connection:
```bash
time python -c "
from post_reel_smart import SmartInstagramPoster
poster = SmartInstagramPoster('podclipcrafters')
poster.connect()
print('Connected successfully')
poster.cleanup()
"
```

Expected: Total connection time should be well under 60 seconds on success.

### 3. Timing verification on failure

Simulate a failure scenario by connecting to an invalid device:
```bash
timeout 20 python -c "
from appium import webdriver
from appium.options.android import UiAutomator2Options
options = UiAutomator2Options()
options.device_name = 'invalid:12345'
options.udid = 'invalid:12345'
options.set_capability('appium:uiautomator2ServerLaunchTimeout', 10000)
driver = webdriver.Remote('http://127.0.0.1:4723', options=options)
" 2>&1 | grep -i timeout
```

Expected: Should timeout within ~15 seconds (10s timeout + overhead), not 90+ seconds.

### 4. Full retry cycle timing

Run a posting operation to a phone that may have intermittent connectivity:
```bash
time python posting_scheduler.py --add-accounts podclipcrafters --add-folder test_videos --run --max-accounts 1
```

Monitor `geelark_batch.log` for retry timing. Expected:
- If first attempt fails, retry should start within 25-30 seconds (10s timeout + 15s delay)
- Full 3-attempt cycle should complete in under 2 minutes even with all failures

### 5. Regression test - no false negatives

Run the scheduler on 5-10 phones overnight and compare:
- Success rate should remain the same or improve (not decrease)
- Average time per attempt should decrease significantly
