# Task ID: 51

**Title:** Enhance Error Classification with Two-Level Category System

**Status:** done

**Dependencies:** 46 ✓

**Priority:** high

**Description:** Expand ERROR_PATTERNS in progress_tracker.py to ERROR_CATEGORIES with two top-level categories ('account' for non-retryable and 'infrastructure' for retryable errors), update _classify_error() to return tuple (category, error_type), and add error_category and pass_number columns to the CSV schema.

**Details:**

## Overview

This task implements Phase 1 of the Retry Loop Implementation plan from `reviews/RETRY_LOOP_IMPLEMENTATION_REVIEW.md`. The current `ERROR_PATTERNS` dict maps error_type -> patterns, but doesn't distinguish between account-level failures (permanent) and infrastructure hiccups (retryable). This enhancement enables future multi-pass retry logic.

## Implementation Details

### 1. Replace ERROR_PATTERNS with ERROR_CATEGORIES

**File:** `progress_tracker.py` (lines 95-103)

Replace the current flat dict:
```python
ERROR_PATTERNS = {
    'suspended': ['suspended', 'account has been suspended'],
    'captcha': ['captcha', 'verify'],
    'loggedout': ['log in', 'logged out', 'sign up'],
    'actionblocked': ['action blocked', 'try again later'],
    'banned': ['banned', 'disabled'],
}
```

With a nested two-level dict:
```python
ERROR_CATEGORIES = {
    'account': {  # Non-retryable - account itself is broken
        'suspended': ['suspended', 'account has been suspended'],
        'disabled': ['disabled', 'your account has been disabled'],
        'verification': ['verify your identity', 'verification required', 'captcha', 'verify'],
        'logged_out': ['log in', 'logged out', 'sign up', 'session expired'],
        'action_blocked': ['action blocked', 'try again later'],
        'banned': ['banned', 'permanently banned'],
    },
    'infrastructure': {  # Retryable - transient failures
        'adb_timeout': ['adb timeout', 'connection timed out', 'device offline'],
        'appium_crash': ['session not created', 'uiautomator', 'instrumentation'],
        'connection_dropped': ['connection dropped', 'socket hang up'],
        'claude_stuck': ['post returned false', 'max steps reached'],
        'glogin_expired': ['glogin', 'login first'],
    }
}
```

### 2. Update NON_RETRYABLE_ERRORS

Update the constant to derive from ERROR_CATEGORIES:
```python
# Non-retryable error types - derived from ERROR_CATEGORIES['account']
NON_RETRYABLE_ERRORS = set(ERROR_CATEGORIES['account'].keys())
```

### 3. Modify _classify_error() Return Type

**Current signature (line 551):**
```python
def _classify_error(self, error: str) -> str:
```

**New signature:**
```python
def _classify_error(self, error: str) -> tuple[str, str]:
    """
    Classify an error message into category and error type.
    
    Returns:
        Tuple of (category, error_type) where:
        - category: 'account', 'infrastructure', or 'unknown'
        - error_type: specific type like 'suspended', 'adb_timeout', or ''
    
    Examples:
        ('account', 'suspended') - non-retryable account issue
        ('infrastructure', 'adb_timeout') - retryable transient failure
        ('unknown', '') - unclassified error (treated as retryable)
    """
    error_lower = error.lower() if error else ''
    
    for category, types_dict in self.ERROR_CATEGORIES.items():
        for error_type, patterns in types_dict.items():
            if any(pattern in error_lower for pattern in patterns):
                return category, error_type
    
    return 'unknown', ''  # Unclassified errors are retryable
```

### 4. Update CSV Schema (COLUMNS constant)

**Current (line 78-82):**
```python
COLUMNS = [
    'job_id', 'account', 'video_path', 'caption', 'status',
    'worker_id', 'claimed_at', 'completed_at', 'error',
    'attempts', 'max_attempts', 'retry_at', 'error_type'
]
```

**New:**
```python
COLUMNS = [
    'job_id', 'account', 'video_path', 'caption', 'status',
    'worker_id', 'claimed_at', 'completed_at', 'error',
    'attempts', 'max_attempts', 'retry_at', 'error_type',
    'error_category', 'pass_number'
]
```

### 5. Update update_job_status() Method

**File:** `progress_tracker.py` (lines 566-650)

Update the failure handling section to store both category and error_type:
```python
elif status == self.STATUS_FAILED:
    # ... existing attempts logic ...
    
    # Classify the error - now returns tuple
    error_category, error_type = self._classify_error(error)
    job['error_type'] = error_type
    job['error_category'] = error_category
    
    if error_category == 'account':  # Use category instead of checking NON_RETRYABLE_ERRORS
        # Non-retryable error - fail permanently
        job['status'] = self.STATUS_FAILED
        logger.warning(f"Worker {worker_id} job {job_id} FAILED (non-retryable: {error_category}/{error_type})")
    # ... rest of retry logic ...
```

### 6. Update Callers of _classify_error()

Search for any direct calls to `_classify_error()` and update to handle tuple return:
- `update_job_status()` - already updated above
- `retry_all_failed()` (line 791) - reads `error_type` from job dict, no change needed

### 7. Initialize New Columns in seed_from_scheduler_state()

Add default empty values for new columns in the job dict (around line 361):
```python
new_jobs.append({
    # ... existing fields ...
    'error_type': '',
    'error_category': '',
    'pass_number': ''
})
```

### 8. Backward Compatibility

The `_read_all_jobs()` method already handles missing columns gracefully via `job.get(col, '')`. Old CSV files will work with empty values for new columns.

## Files Modified

- `progress_tracker.py` - Main implementation file

## Dependencies on Other Tasks

- Task 46 (done): Already converted _classify_error to dict-based pattern - this task builds on that foundation
- Task 22 (done): Fixed per-account daily cap enforcement - this task uses the same update_job_status path

**Test Strategy:**

## Test Strategy

### 1. Syntax and Import Verification
```bash
python -c "from progress_tracker import ProgressTracker; print('Import successful')"
```

### 2. Verify ERROR_CATEGORIES Structure
```bash
python -c "
from progress_tracker import ProgressTracker
pt = ProgressTracker('test.csv')
print('ERROR_CATEGORIES:', ProgressTracker.ERROR_CATEGORIES)
print('Account types:', list(pt.ERROR_CATEGORIES['account'].keys()))
print('Infra types:', list(pt.ERROR_CATEGORIES['infrastructure'].keys()))
"
```

### 3. Verify NON_RETRYABLE_ERRORS Derivation
```bash
python -c "
from progress_tracker import ProgressTracker
print('NON_RETRYABLE_ERRORS:', ProgressTracker.NON_RETRYABLE_ERRORS)
# Should match ERROR_CATEGORIES['account'].keys()
assert ProgressTracker.NON_RETRYABLE_ERRORS == set(ProgressTracker.ERROR_CATEGORIES['account'].keys())
print('PASS: NON_RETRYABLE_ERRORS derived correctly')
"
```

### 4. Test _classify_error() Returns Tuple
```bash
python -c "
from progress_tracker import ProgressTracker
pt = ProgressTracker('test.csv')

# Test account errors
cat, etype = pt._classify_error('Your account has been suspended')
assert cat == 'account' and etype == 'suspended', f'Got ({cat}, {etype})'

cat, etype = pt._classify_error('Please log in to continue')
assert cat == 'account' and etype == 'logged_out', f'Got ({cat}, {etype})'

# Test infrastructure errors
cat, etype = pt._classify_error('ADB timeout: device offline')
assert cat == 'infrastructure' and etype == 'adb_timeout', f'Got ({cat}, {etype})'

cat, etype = pt._classify_error('Post returned False after 30 steps')
assert cat == 'infrastructure' and etype == 'claude_stuck', f'Got ({cat}, {etype})'

# Test unknown error
cat, etype = pt._classify_error('Some random error')
assert cat == 'unknown' and etype == '', f'Got ({cat}, {etype})'

print('PASS: All _classify_error tests passed')
"
```

### 5. Verify CSV COLUMNS Include New Fields
```bash
python -c "
from progress_tracker import ProgressTracker
cols = ProgressTracker.COLUMNS
assert 'error_category' in cols, 'Missing error_category'
assert 'pass_number' in cols, 'Missing pass_number'
print('COLUMNS:', cols)
print('PASS: New columns present')
"
```

### 6. Integration Test: Failure Updates Category
```bash
python -c "
import os
from progress_tracker import ProgressTracker

# Create test tracker
pt = ProgressTracker('test_category.csv')
pt.seed_from_jobs([{'job_id': 'test1', 'account': 'acc1', 'video_path': 'v.mp4', 'caption': 'test'}])

# Claim and fail with account error
job = pt.claim_next_job(worker_id=0)
pt.update_job_status('test1', 'failed', worker_id=0, error='Account suspended')

# Read back and verify
jobs = pt._read_all_jobs()
assert jobs[0]['error_category'] == 'account', f'Got {jobs[0][\"error_category\"]}'
assert jobs[0]['error_type'] == 'suspended', f'Got {jobs[0][\"error_type\"]}'
print('PASS: error_category saved correctly')

# Cleanup
os.remove('test_category.csv')
os.remove('test_category.csv.lock')
"
```

### 7. Backward Compatibility Test
```bash
python -c "
import os
from progress_tracker import ProgressTracker

# Create old-format CSV without new columns
with open('test_old.csv', 'w') as f:
    f.write('job_id,account,video_path,caption,status,worker_id,claimed_at,completed_at,error,attempts,max_attempts,retry_at,error_type\n')
    f.write('job1,acc1,v.mp4,test,pending,,,,,0,3,,\n')

# Read with new tracker
pt = ProgressTracker('test_old.csv')
jobs = pt._read_all_jobs()
assert len(jobs) == 1
assert jobs[0]['job_id'] == 'job1'
print('PASS: Old CSV format compatible')

os.remove('test_old.csv')
"
```

### 8. Full End-to-End Test
Run the existing test demo at the bottom of progress_tracker.py:
```bash
python progress_tracker.py
```

This should complete without errors and demonstrate the new classification system in action.
