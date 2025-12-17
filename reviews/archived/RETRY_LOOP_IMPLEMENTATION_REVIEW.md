# Geelark Automation: Retry Loop Implementation Review

**Date:** December 2024
**Author:** Staff Engineer Review
**Scope:** Error handling architecture and multi-pass retry system design

---

## Executive Summary

The Geelark Instagram automation codebase demonstrates solid foundational patterns—particularly file-based locking for multi-process coordination and a strategy pattern for error classification. However, the current error handling conflates **account-level failures** (suspended, logged out) with **infrastructure hiccups** (ADB timeout, Appium crash), leading to unnecessary retries of permanently-broken accounts and insufficient retries of transient failures.

**The core ask:** Implement a multi-pass retry loop that:
1. Tries all pending jobs
2. Classifies failures into account issues (permanent) vs infrastructure issues (retryable)
3. Retries only infrastructure failures
4. Repeats until done or max passes reached

**Estimated effort:** 2-3 focused development sessions
**Risk:** Low—changes are additive and backward-compatible

---

## Best Practices Already in Place

### 1. Strategy Pattern for Error Classification
**File:** `progress_tracker.py`

```python
ERROR_PATTERNS = {
    'suspended': ['suspended', 'account has been suspended'],
    'captcha': ['captcha', 'verify'],
    'loggedout': ['log in', 'logged out', 'sign up'],
    'actionblocked': ['action blocked', 'try again later'],
    'banned': ['banned', 'disabled'],
}
NON_RETRYABLE_ERRORS = {'suspended', 'captcha', 'loggedout', 'actionblocked', 'banned'}
```

**Why it's good:** Declarative, extensible, centralizes error knowledge. New patterns can be added without touching classification logic.

### 2. File-Locked Multi-Process Coordination
**File:** `progress_tracker.py`

The `_locked_operation(callback)` pattern wraps all CSV operations with platform-safe file locking. Workers can't double-claim jobs.

### 3. Single-Instance Lock with Heartbeat
**File:** `posting_scheduler.py`

Stale-lock detection using heartbeats prevents orphaned locks from blocking the system after crashes.

### 4. Process Isolation for Workers
**File:** `parallel_worker.py`

Each worker runs as a separate process with its own Appium server and systemPort range. Cascading failures are impossible.

### 5. Defensive Pre-Post Verification
**File:** `progress_tracker.py`

`verify_job_before_post()` double-checks job ownership immediately before posting, preventing duplicates even under race conditions.

---

## Problem Areas

### 1. Missing Infrastructure Error Category

**Current state:** Only account errors are classified. Everything else is "retryable by default."

**Gap:** No explicit patterns for:
- ADB timeouts / device offline
- Appium session failures
- Claude navigation stuck ("Post returned False")
- glogin expiration

**Impact:** Infrastructure failures exhaust per-job retry limits, then the job is abandoned. Real success rate is artificially lowered.

### 2. No Multi-Pass Orchestration

**Current state:** Jobs retry within a single pass. Once a pass completes, failed jobs sit in `failed` status forever.

**Gap:** No mechanism to:
- Aggregate pass-level stats
- Filter account failures from infrastructure failures
- Reset retryable jobs for a second pass
- Decide when to stop (all done, only non-retryable remain, max passes)

### 3. Inconsistent Error Message Formats

Error messages come from multiple sources (Appium exceptions, Claude responses, ADB commands) with no normalization. Pattern matching is fragile.

---

## Retry Loop Implementation Plan

### The Mental Model

```
PASS 1: Try all pending jobs
         ↓
     CATEGORIZE FAILURES
         ↓
     account broken? → mark failed forever
     infrastructure hiccup? → queue for retry
         ↓
PASS 2: Retry infrastructure failures only
         ↓
     REPEAT until:
       - All jobs succeeded, OR
       - Only non-retryable remain, OR
       - Max passes reached (default: 3)
```

---

### Phase 1: Enhance Error Classification

**File:** `progress_tracker.py`

**Change:** Add infrastructure error patterns alongside account errors.

```python
ERROR_CATEGORIES = {
    'account': {  # Non-retryable
        'suspended': ['suspended', 'account has been suspended'],
        'disabled': ['disabled', 'your account has been disabled'],
        'verification': ['verify your identity', 'verification required'],
        'logged_out': ['log in', 'logged out', 'session expired'],
        'action_blocked': ['action blocked', 'try again later'],
        'banned': ['banned', 'permanently banned'],
    },
    'infrastructure': {  # Retryable
        'adb_timeout': ['adb timeout', 'connection timed out', 'device offline'],
        'appium_crash': ['session not created', 'uiautomator', 'instrumentation'],
        'connection_dropped': ['connection dropped', 'socket hang up'],
        'claude_stuck': ['post returned false', 'max steps reached'],
        'glogin_expired': ['glogin', 'login first'],
    }
}
```

**Update `_classify_error()`:**

```python
def _classify_error(self, error: str) -> tuple[str, str]:
    """Returns (category, error_type) e.g. ('account', 'suspended')"""
    error_lower = error.lower() if error else ''
    for category, types in ERROR_CATEGORIES.items():
        for error_type, patterns in types.items():
            if any(p in error_lower for p in patterns):
                return category, error_type
    return 'unknown', ''
```

**Add CSV columns:** `error_category`, `pass_number`

---

### Phase 2: Create RetryPassManager

**New file:** `retry_manager.py`

```python
@dataclass
class RetryConfig:
    max_passes: int = 3
    retry_delay_seconds: int = 30
    infrastructure_retry_limit: int = 3

class RetryPassManager:
    def __init__(self, tracker: ProgressTracker, config: RetryConfig):
        self.tracker = tracker
        self.config = config
        self.current_pass = 0

    def start_new_pass(self) -> int:
        """Returns pass number. Pass 1 = all pending. Pass 2+ = retryable failed only."""
        self.current_pass += 1
        if self.current_pass == 1:
            jobs = self._get_pending_jobs()
        else:
            jobs = self._get_retryable_failed_jobs()
        return self.current_pass

    def end_pass(self) -> PassResult:
        """Categorize failures, reset retryable jobs, return what to do next."""
        stats = self._gather_stats()

        retryable = stats['failed_infrastructure'] + stats['failed_unknown']

        if retryable == 0:
            if stats['failed_account'] > 0:
                return PassResult.ONLY_NON_RETRYABLE
            return PassResult.ALL_COMPLETE

        if self.current_pass >= self.config.max_passes:
            return PassResult.MAX_PASSES_REACHED

        self._reset_retryable_jobs()
        return PassResult.RETRYABLE_REMAINING
```

---

### Phase 3: Integrate into Orchestrator

**File:** `parallel_orchestrator.py`

```python
def run_with_retry(num_workers: int, retry_config: RetryConfig):
    tracker = ProgressTracker(PROGRESS_FILE)
    retry_mgr = RetryPassManager(tracker, retry_config)

    result = PassResult.RETRYABLE_REMAINING

    while result == PassResult.RETRYABLE_REMAINING:
        pass_num = retry_mgr.start_new_pass()
        logger.info(f"=== PASS {pass_num} ===")

        # Run workers (existing logic)
        processes = start_all_workers(num_workers)
        monitor_workers(processes)

        # End pass
        result = retry_mgr.end_pass()

        if result == PassResult.RETRYABLE_REMAINING:
            logger.info(f"Waiting {retry_config.retry_delay_seconds}s before next pass")
            time.sleep(retry_config.retry_delay_seconds)

    logger.info(f"DONE: {result.value}")
```

---

### Phase 4: Worker Error Propagation

**File:** `parallel_worker.py`

Workers must return error category to tracker:

```python
def execute_posting_job(job, tracker, worker_id):
    try:
        success = poster.post_reel(...)
        if success:
            return True, "", None, None
        else:
            error = poster.last_error or "Post returned False"
            cat, etype = tracker._classify_error(error)
            return False, error, cat, etype
    except TimeoutError as e:
        return False, str(e), "infrastructure", "adb_timeout"
    except Exception as e:
        cat, etype = tracker._classify_error(str(e))
        return False, str(e), cat, etype

# In run_worker main loop:
success, error, category, error_type = execute_posting_job(...)
tracker.update_job_status(
    job_id, 'failed' if not success else 'success',
    worker_id, error=error,
    error_category=category,
    error_type=error_type
)
```

---

### Phase 5: CLI Flags

```bash
python parallel_orchestrator.py --run \
    --max-passes 3 \
    --retry-delay 30 \
    --infra-retry-limit 3
```

---

## Test Scenarios

| Scenario | Jobs | Expected Passes | Final State |
|----------|------|-----------------|-------------|
| All succeed | 5 | 1 | `ALL_COMPLETE` |
| 2 suspended | 5 | 1 | `ONLY_NON_RETRYABLE`, 3 success, 2 failed |
| 2 ADB timeout | 5 | 2-3 | Most succeed after retry |
| Mixed | 10 | 2-3 | Account failures stay failed, infra retried |

---

## Migration Notes

1. **Backward compatible:** Old CSV files work (new columns default empty)
2. **Rollback:** Use `--max-passes 1` to disable retry loop
3. **No breaking CLI changes**

---

## Summary

| Item | Status | Action |
|------|--------|--------|
| Error classification | Good foundation | Expand with infrastructure patterns |
| File locking | Production-ready | No change |
| Multi-pass retry | Missing | Implement `RetryPassManager` |
| Error propagation | Partial | Add category to worker → tracker flow |
| CLI integration | Ready | Add retry flags |

The key insight: separate **"what went wrong"** (classification) from **"what to do about it"** (retry policy). This makes both concerns independently testable and extensible.
