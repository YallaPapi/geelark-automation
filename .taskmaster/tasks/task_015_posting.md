# Task ID: 15

**Title:** Integrate reliability features into posting_scheduler worker loop

**Status:** done

**Dependencies:** 9 ✓, 11 ✓, 13 ✓

**Priority:** high

**Description:** Wire up existing but unused reliability mechanisms (Appium health checks, account cooldown backoff) into the scheduler's worker loop, add a heartbeat thread to keep the lock file fresh, and classify infrastructure errors to trigger account-level backoff.

**Details:**

## Current State Analysis

The codebase already has several reliability features that are **implemented but NOT wired up**:

1. **Single-instance lock** (lines 30-111): Fully working but uses static lock file without heartbeat
2. **Appium health checks** (lines 114-170): `check_appium_health()` and `restart_appium()` exist but never called
3. **Account cooldown** (lines 435-471): `is_on_cooldown()` and `record_post(is_infra_error)` exist but:
   - `is_on_cooldown()` is NOT checked in `get_next_job()` (line 661-703)
   - `record_post()` is always called with just `False`, never passing `is_infra_error=True` (line 815)

## Implementation Details

### 1. Add Heartbeat Thread for Lock Freshness

Update the lock file with a timestamp periodically so other instances can detect truly stale locks:

```python
# Add to PostingScheduler.__init__()
self.heartbeat_thread: Optional[threading.Thread] = None
self.heartbeat_interval = 30  # seconds

# Add heartbeat method
def _heartbeat_loop(self):
    """Periodically update lock file to prove we're still alive"""
    while self.running:
        try:
            if os.path.exists(LOCK_FILE):
                with open(LOCK_FILE, 'r') as f:
                    lock_data = json.load(f)
                if lock_data.get('pid') == os.getpid():
                    lock_data['last_heartbeat'] = datetime.now().isoformat()
                    with open(LOCK_FILE, 'w') as f:
                        json.dump(lock_data, f)
        except Exception as e:
            logger.warning(f"Heartbeat error: {e}")
        time.sleep(self.heartbeat_interval)
```

Update `acquire_lock()` to check heartbeat staleness:
```python
# In acquire_lock(), after is_process_running check:
last_heartbeat = lock_data.get('last_heartbeat')
if last_heartbeat:
    hb_time = datetime.fromisoformat(last_heartbeat)
    stale_threshold = timedelta(minutes=2)  # 2 minutes without heartbeat = stale
    if datetime.now() - hb_time > stale_threshold:
        print(f"[LOCK] Lock heartbeat stale ({hb_time}). Taking over.")
        # Proceed to take over
```

### 2. Integrate Appium Health Check into Worker Loop

In `_worker_loop()`, before processing a job:

```python
def _worker_loop(self):
    """Main worker loop"""
    self._log("Worker started")
    
    # Track consecutive Appium failures for restart logic
    appium_consecutive_failures = 0
    max_appium_failures_before_restart = 3
    
    while self.running:
        if self.paused:
            time.sleep(1)
            continue
        
        # Check Appium health before each job
        if not check_appium_health():
            self._log("[APPIUM] Health check failed")
            appium_consecutive_failures += 1
            
            if appium_consecutive_failures >= max_appium_failures_before_restart:
                self._log("[APPIUM] Attempting auto-restart...")
                if restart_appium():
                    appium_consecutive_failures = 0
                else:
                    self._log("[APPIUM] Restart failed, waiting 60s...")
                    time.sleep(60)
                    continue
            else:
                time.sleep(10)
                continue
        else:
            appium_consecutive_failures = 0  # Reset on success
        
        job = self.get_next_job()
        # ... rest of loop
```

### 3. Integrate Account Cooldown into get_next_job()

Update `get_next_job()` to filter out accounts on cooldown:

```python
def get_next_job(self) -> Optional[PostJob]:
    """Get next job that's ready to post"""
    accounts_posted_today = get_accounts_posted_today()
    
    # Filter: can post today AND not on cooldown
    available_accounts = [
        acc for acc in self.accounts.values()
        if acc.can_post_today(self.posts_per_account_per_day)
        and acc.name not in accounts_posted_today
        and not acc.is_on_cooldown()  # ADD THIS LINE
    ]
    # ... rest of method unchanged
```

### 4. Classify Infrastructure Errors in execute_job()

Update the error handling in `execute_job()` to detect infrastructure errors:

```python
# In execute_job(), in the except block (around line 783):
except Exception as e:
    error_msg = str(e)
    error_type_name = type(e).__name__
    
    # Classify infrastructure errors
    infra_error_patterns = [
        'ADB', 'adb', 'device offline', 'glogin', 'phone not running',
        'Appium', 'appium', 'UiAutomator', 'WebDriver', 
        'connection refused', 'timeout', 'Timeout'
    ]
    is_infra_error = any(pattern in error_msg for pattern in infra_error_patterns) or \
                     any(pattern in error_type_name for pattern in infra_error_patterns)
    
    job.last_error = f"[{phase}] {error_type_name}: {error_msg}"
    
    # ... existing error handling ...
    
    # Pass is_infra_error to trigger backoff
    self.accounts[job.account].record_post(False, is_infra_error=is_infra_error)
```

### 5. Start Heartbeat Thread in start()

```python
def start(self):
    """Start the scheduler"""
    if self.running:
        return
    
    # ... existing phone cleanup ...
    
    self.running = True
    self.paused = False
    
    # Start heartbeat thread
    self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
    self.heartbeat_thread.start()
    self._log("[HEARTBEAT] Started heartbeat thread")
    
    # Start worker thread
    self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
    self.worker_thread.start()
    self._log("Scheduler started")
```

### 6. Add Account Cooldown Status to get_stats()

```python
def get_stats(self) -> dict:
    """Get current statistics"""
    accounts_on_cooldown = [acc.name for acc in self.accounts.values() if acc.is_on_cooldown()]
    
    return {
        # ... existing stats ...
        'accounts_on_cooldown': accounts_on_cooldown,
    }
```

## Files to Modify

- `posting_scheduler.py`: All changes concentrated in this single file

**Test Strategy:**

## Test Strategy

### 1. Single-Instance Lock with Heartbeat Tests

**Test stale lock detection:**
```bash
# Create a stale lock file manually
echo '{"pid": 99999, "started": "2024-01-01T00:00:00", "last_heartbeat": "2024-01-01T00:00:00"}' > scheduler.lock

# Run scheduler - should take over the stale lock
python posting_scheduler.py --status
# Expected: "Lock heartbeat stale" message, then acquires lock
```

**Test heartbeat updates:**
```bash
# Start scheduler in background
python posting_scheduler.py --add-folder chunk_test --add-accounts test1 --run &

# Check lock file updates every 30s
watch -n 10 'cat scheduler.lock | python -m json.tool | grep last_heartbeat'
# Expected: last_heartbeat timestamp updates every ~30 seconds
```

**Test duplicate instance prevention:**
```bash
# Terminal 1: Start scheduler
python posting_scheduler.py --run

# Terminal 2: Try to start another
python posting_scheduler.py --run
# Expected: "[LOCK ERROR] Another scheduler instance is already running!"
```

### 2. Appium Health Check Integration Tests

**Test health check detection:**
```bash
# Stop Appium server
taskkill /F /IM node.exe

# Run scheduler - should detect Appium down
python posting_scheduler.py --run
# Expected: "[APPIUM] Health check failed" messages
```

**Test auto-restart:**
```bash
# With Appium stopped, scheduler should attempt restart after 3 failures
# Expected log sequence:
# [APPIUM] Health check failed (1)
# [APPIUM] Health check failed (2) 
# [APPIUM] Health check failed (3)
# [APPIUM] Attempting auto-restart...
# [APPIUM] Server ready on port 4723
```

### 3. Account Cooldown Integration Tests

**Test cooldown filtering in get_next_job:**
```python
# Unit test
scheduler = PostingScheduler()
scheduler.add_account("test1")
scheduler.accounts["test1"].cooldown_until = (datetime.now() + timedelta(minutes=10)).isoformat()

# get_next_job should not return jobs for test1
job = scheduler.get_next_job()
assert job is None or job.account != "test1"
```

**Test infrastructure error classification:**
```python
# Simulate infra error in execute_job
# After 3 consecutive failures, account should be on cooldown
assert scheduler.accounts["test1"].is_on_cooldown() == True
assert scheduler.accounts["test1"].consecutive_failures >= 3
```

### 4. Status Command Verification

```bash
python posting_scheduler.py --status
# Expected output includes:
# - Lock status with last_heartbeat timestamp
# - Accounts on cooldown list (if any)
# - Appium health status
```

### 5. Error Log Verification

After a test run with simulated failures:
```bash
grep "is_infra_error" geelark_batch.log
# Should show infrastructure errors being correctly classified

grep "on cooldown" geelark_batch.log  
# Should show accounts being put on cooldown after consecutive failures
```

### 6. Integration Test with Real Posting

```bash
# Run with a small test batch
python posting_scheduler.py --add-folder chunk_test --add-accounts phone1 --run

# Monitor logs for:
# 1. Heartbeat updates
# 2. Appium health checks before each job
# 3. Proper cooldown behavior if failures occur
# 4. Clean shutdown releasing lock
```
