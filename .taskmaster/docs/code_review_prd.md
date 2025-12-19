# Code Review Implementation PRD - Self-Healing Automation System

## Overview

This PRD implements recommendations from a high-level code review to make the Instagram posting automation "fire and forget" - fully self-healing without manual intervention. The current system has ~54% success rate due to navigation failures, JSON parsing issues, and lack of inline recovery mechanisms.

## Goals

1. Achieve 85%+ success rate through automatic error detection and recovery
2. Eliminate need for separate test scripts - all testing logic inline
3. Make the system recover from common failures (ADB drops, Appium crashes, UI navigation issues)
4. Improve Claude AI response parsing reliability

---

## Task 1: Add Pre-Flight Checks to Parallel Worker

### Description
Add a `pre_flight_checks()` function that runs before processing any jobs. This integrates the logic from test scripts (test_connection.py, test_appium.py, test_dump_ui_fix.py) directly into the main posting flow.

### Requirements
- Create `pre_flight_checks()` function in `parallel_worker.py`
- Verify Appium server is healthy and restart if needed
- Test ADB connection to the assigned phone
- Do a quick UI dump test to verify parsing works
- Return True only if all checks pass
- Call this function at worker startup before claiming any jobs

### Files to Modify
- `parallel_worker.py`

### Implementation Details
```python
def pre_flight_checks(worker_id: int, appium_url: str, phone_name: str) -> bool:
    """Run system checks before processing jobs. Returns True if ready."""
    logger.info(f"[PRE-FLIGHT] Worker {worker_id} running system checks...")

    # 1. Check Appium health
    # 2. Test ADB connection to phone
    # 3. Quick UI dump test (optional - can be done at job start)

    return True  # All checks passed
```

---

## Task 2: Add Per-Job Checks and Auto-Fixes

### Description
Before each post attempt, verify the system is ready and automatically fix common issues. This provides defense-in-depth beyond pre-flight checks.

### Requirements
- Create `per_job_checks_and_fixes(job, conn_manager)` function
- Verify ADB connection is still alive, reconnect if dropped
- Check Appium session health
- On ADB failure: call reconnect logic from device_connection.py
- On Appium failure: restart Appium server
- Return True if system is ready, False if unfixable

### Files to Modify
- `parallel_worker.py`

### Implementation Details
```python
def per_job_checks_and_fixes(job: dict, conn_manager: DeviceConnectionManager, appium_url: str) -> Tuple[bool, str]:
    """Per-job checks and auto-fixes. Returns (ready, error_message)."""

    # 1. Verify ADB connection
    if not conn_manager.verify_adb_connection():
        logger.warning("ADB dropped - reconnecting...")
        if not conn_manager.reconnect_adb():
            return False, "ADB reconnect failed"

    # 2. Check Appium health
    if not check_appium_health(appium_url):
        logger.warning("Appium unhealthy - needs restart")
        return False, "Appium unhealthy"

    return True, ""
```

---

## Task 3: Add ADB Verification and Reconnection Methods to DeviceConnectionManager

### Description
Add methods to DeviceConnectionManager for verifying ADB connection health and reconnecting if dropped. These are called by per-job checks.

### Requirements
- Add `verify_adb_connection()` method - quick check if ADB is responsive
- Add `reconnect_adb()` method - full reconnection sequence
- Use simple ADB command (like `adb devices`) to verify
- On reconnect: disable ADB, re-enable, reconnect
- Handle timeout gracefully

### Files to Modify
- `device_connection.py`

### Implementation Details
```python
def verify_adb_connection(self, timeout: int = 5) -> bool:
    """Quick check if ADB connection is still alive."""
    if not self.device:
        return False
    try:
        result = subprocess.run(
            [ADB_PATH, "-s", self.device, "shell", "echo", "ping"],
            capture_output=True, timeout=timeout, text=True
        )
        return result.returncode == 0 and "ping" in result.stdout
    except:
        return False

def reconnect_adb(self, max_retries: int = 3) -> bool:
    """Full ADB reconnection sequence."""
    # Disconnect existing
    # Disable ADB via Geelark API
    # Re-enable ADB
    # Reconnect
    pass
```

---

## Task 4: Add UiAutomator2 Crash Detection and Recovery

### Description
Detect UiAutomator2 crashes during posting and automatically recover by restarting the Appium session.

### Requirements
- Add `is_uiautomator2_crash(error)` method to detect crash signatures
- Add `reconnect_appium()` method to restart Appium session
- Call recovery automatically when crash detected in dump_ui or other operations
- Common crash signatures: "UiAutomator2 server not running", "instrumentation", "session died"

### Files to Modify
- `post_reel_smart.py`

### Implementation Details
```python
def is_uiautomator2_crash(self, error: Exception) -> bool:
    """Detect if error indicates UiAutomator2 crash."""
    error_str = str(error).lower()
    crash_signatures = [
        'uiautomator2 server not running',
        'instrumentation run failed',
        'session not created',
        'original error: could not proxy',
        'session died',
        'uiautomator exited'
    ]
    return any(sig in error_str for sig in crash_signatures)

def reconnect_appium(self) -> bool:
    """Reconnect Appium session after crash."""
    logger.warning("Reconnecting Appium session...")
    try:
        if self.appium_driver:
            try:
                self.appium_driver.quit()
            except:
                pass
        # Recreate session
        self.appium_driver = self._create_appium_driver()
        return True
    except Exception as e:
        logger.error(f"Failed to reconnect Appium: {e}")
        return False
```

---

## Task 5: Verify and Fix dump_ui() Parsing for Android 15

### Description
Ensure dump_ui() uses the correct XML parsing method (iter() not iter('node')) for Android 15 compatibility. This was identified in test_dump_ui_fix.py.

### Requirements
- Verify dump_ui() uses `root.iter()` not `root.iter('node')`
- Add automatic UiAutomator2 crash recovery in dump_ui()
- Ensure elements are parsed correctly from Appium's page_source
- Add logging for element count

### Files to Modify
- `post_reel_smart.py`

### Implementation Details
The critical fix is:
```python
# WRONG (breaks on Android 15):
for elem in root.iter('node'):

# CORRECT:
for elem in root.iter():
```

Also add crash recovery:
```python
def dump_ui(self) -> Tuple[List[Dict], str]:
    try:
        xml_str = self.appium_driver.page_source
        # ... parsing ...
    except Exception as e:
        if self.is_uiautomator2_crash(e):
            logger.warning("[UI DUMP] UiAutomator2 crashed - recovering...")
            if self.reconnect_appium():
                # Retry once after recovery
                xml_str = self.appium_driver.page_source
            else:
                raise
        else:
            raise
```

---

## Task 6: Improve JSON Parsing Robustness in Claude Analyzer

### Description
The current JSON parser fails when Claude adds explanatory text before the JSON block. Implement robust extraction that finds JSON anywhere in the response.

### Requirements
- Extract JSON from ```json blocks anywhere in response (not just at start)
- Find raw JSON objects { ... } if no code block
- Handle nested braces correctly
- Fall back to direct parse as last resort
- Log extracted JSON for debugging

### Files to Modify
- `claude_analyzer.py`

### Status
ALREADY IMPLEMENTED in previous session. Verify implementation is complete and working.

### Implementation Details
The fix adds multiple extraction methods:
1. Find ```json ... ``` blocks anywhere
2. Split on ``` and check each part
3. Find raw { ... } with brace matching
4. Direct parse fallback

---

## Task 7: Tighten Claude System Prompt to Output Only JSON

### Description
Update the Claude prompt to explicitly instruct it to respond ONLY with JSON, no explanatory text. This reduces parsing failures.

### Requirements
- Add explicit instruction: "Respond ONLY with the JSON block. Do NOT add any explanatory text before or after."
- Make this instruction prominent (at the end of prompt, after examples)
- Keep it brief but clear

### Files to Modify
- `claude_analyzer.py` (in build_prompt method)

### Implementation Details
Add at the end of the prompt:
```
CRITICAL: Respond with ONLY the JSON object. Do NOT include any text, explanation, or markdown formatting before or after the JSON. Start your response with { and end with }.
```

---

## Task 8: Increase Max Steps from 20 to 30

### Description
Increase the default max_steps from 20 to 30 to give Claude more chances to complete navigation on tricky screens.

### Requirements
- Change default max_steps from 20 to 30 in post() method
- This gives more buffer for complex UI states
- Still prevents infinite loops but allows recovery from temporary issues

### Files to Modify
- `post_reel_smart.py`

### Implementation Details
```python
def post(self, video_path, caption, max_steps=30, humanize=False):
```

---

## Task 9: Add Full Flow Restart on Max Steps Reached

### Description
When "max steps reached" occurs, instead of failing immediately, try restarting the entire posting flow from scratch (close Instagram, reopen, start over).

### Requirements
- Add `restart_posting_flow()` method
- On max steps reached, attempt one full restart before failing
- Close Instagram app
- Reopen Instagram
- Reset state flags (video_uploaded, caption_entered, share_clicked)
- Continue from step 1

### Files to Modify
- `post_reel_smart.py`

### Implementation Details
```python
def restart_posting_flow(self) -> bool:
    """Restart the posting flow from scratch."""
    logger.warning("Restarting posting flow from scratch...")
    try:
        # Close Instagram
        self.appium_driver.terminate_app("com.instagram.android")
        time.sleep(2)

        # Reopen Instagram
        self.appium_driver.activate_app("com.instagram.android")
        time.sleep(3)

        # Reset state
        self.video_uploaded = False
        self.caption_entered = False
        self.share_clicked = False

        return True
    except Exception as e:
        logger.error(f"Failed to restart posting flow: {e}")
        return False
```

In the main post() loop:
```python
if step >= max_steps:
    if not flow_restarted:
        logger.warning("Max steps reached - attempting flow restart...")
        if self.restart_posting_flow():
            flow_restarted = True
            step = 0  # Reset step counter
            continue
    # If already restarted or restart failed, give up
    return False, "Max steps reached after restart attempt"
```

---

## Task 10: Add Inline Error Recovery in Posting Loop

### Description
Add try-except blocks around key operations in the posting loop to catch and auto-fix issues inline rather than failing the entire job.

### Requirements
- Wrap upload_video, tap, type_text operations in try-except
- On ADB-related errors: attempt ADB reconnection
- On UiAutomator2 errors: attempt Appium reconnection
- Track recovery attempts to prevent infinite loops
- Only bubble up errors if recovery fails

### Files to Modify
- `post_reel_smart.py`

### Implementation Details
```python
# In posting loop:
try:
    self.tap(x, y)
except Exception as e:
    if "adb" in str(e).lower() or "device" in str(e).lower():
        logger.warning(f"ADB issue in tap: {e} - attempting recovery")
        if self._conn and self._conn.reconnect_adb():
            self.tap(x, y)  # Retry
        else:
            raise
    elif self.is_uiautomator2_crash(e):
        logger.warning(f"UiAutomator2 crash in tap: {e} - recovering")
        if self.reconnect_appium():
            self.tap(x, y)  # Retry
        else:
            raise
    else:
        raise
```

---

## Task 11: Fix Error Classification Priority Order

### Description
Ensure "max steps reached" is classified as infrastructure/claude_stuck BEFORE checking for "action blocked" pattern, since Vision analysis text may contain "action blocked" in a negative context.

### Requirements
- Check for "max steps reached" at the very top of _classify_error()
- Return ('infrastructure', 'claude_stuck') immediately if found
- This prevents misclassification when Vision analysis says "no action blocked warnings"

### Files to Modify
- `progress_tracker.py`

### Status
ALREADY IMPLEMENTED in previous session. Verify implementation is in place.

---

## Task 12: Add Appium Health Check Function

### Description
Create a standalone function to check if Appium server is healthy and responding.

### Requirements
- Create `check_appium_health(appium_url)` function
- Make HTTP request to Appium status endpoint
- Return True if responsive, False otherwise
- Set short timeout (5 seconds) to avoid blocking

### Files to Modify
- `parallel_worker.py` or create `appium_utils.py`

### Implementation Details
```python
def check_appium_health(appium_url: str, timeout: int = 5) -> bool:
    """Check if Appium server is healthy."""
    try:
        import requests
        status_url = f"{appium_url}/status"
        response = requests.get(status_url, timeout=timeout)
        return response.status_code == 200
    except:
        return False
```

---

## Task 13: Add Connection Manager Reference to SmartInstagramPoster

### Description
Pass the DeviceConnectionManager to SmartInstagramPoster so it can call reconnection methods during posting.

### Requirements
- Add optional `conn_manager` parameter to SmartInstagramPoster.__init__()
- Store as self._conn
- Use for ADB recovery in posting loop
- Maintain backward compatibility (conn_manager can be None)

### Files to Modify
- `post_reel_smart.py`
- `parallel_worker.py` (pass conn_manager when creating poster)

### Implementation Details
```python
class SmartInstagramPoster:
    def __init__(self, appium_driver, phone_name: str = "unknown", conn_manager=None):
        self.appium_driver = appium_driver
        self.phone_name = phone_name
        self._conn = conn_manager  # For ADB recovery
```

---

## Task 14: Consolidate Test Script Logic into Main Modules

### Description
The test scripts (test_connection.py, test_appium.py, test_dump_ui_fix.py) contain useful logic that should be available in the main modules. Ensure the core logic is accessible without running separate test scripts.

### Requirements
- Verify DeviceConnectionManager has all connection test logic
- Verify appium health check is available as a function
- Verify UI dump parsing fix is in place
- Document which test scripts are now obsolete

### Files to Review
- `device_connection.py`
- `parallel_worker.py`
- `post_reel_smart.py`

---

## Summary of Changes by File

### parallel_worker.py
- Add `pre_flight_checks()` function
- Add `per_job_checks_and_fixes()` function
- Add `check_appium_health()` function
- Call pre-flight at worker startup
- Call per-job checks before each job
- Pass conn_manager to SmartInstagramPoster

### device_connection.py
- Add `verify_adb_connection()` method
- Add `reconnect_adb()` method

### post_reel_smart.py
- Add `is_uiautomator2_crash()` method
- Add `reconnect_appium()` method
- Add `restart_posting_flow()` method
- Add `conn_manager` parameter to __init__
- Verify dump_ui() uses iter() correctly
- Add inline error recovery in posting loop
- Change max_steps default from 20 to 30

### claude_analyzer.py
- Verify robust JSON parser is in place
- Add "ONLY output JSON" instruction to prompt

### progress_tracker.py
- Verify "max steps reached" classification fix is in place

---

## Success Criteria

1. Pre-flight checks run automatically at worker startup
2. ADB drops are detected and reconnected automatically
3. UiAutomator2 crashes are detected and recovered
4. JSON parsing succeeds even with explanatory text
5. Max steps reached triggers flow restart before failing
6. Success rate improves from ~54% to 85%+
7. No manual intervention required for common failures
