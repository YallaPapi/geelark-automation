# Task ID: 46

**Title:** Convert _classify_error to dict-based pattern lookup table

**Status:** done

**Dependencies:** 40 ✓

**Priority:** medium

**Description:** Refactor the _classify_error() method in progress_tracker.py from a 5-condition if/elif chain to a Strategy pattern using an ERROR_PATTERNS dict that maps error types to lists of matching patterns, improving maintainability and extensibility.

**Details:**

## Current State Analysis

The `_classify_error()` method in `progress_tracker.py` (lines 541-560) uses an if/elif chain with 5 conditions:

```python
def _classify_error(self, error: str) -> str:
    error_lower = error.lower() if error else ''
    
    if 'suspended' in error_lower or 'account has been suspended' in error_lower:
        return 'suspended'
    elif 'captcha' in error_lower or 'verify' in error_lower:
        return 'captcha'
    elif 'log in' in error_lower or 'logged out' in error_lower or 'sign up' in error_lower:
        return 'loggedout'
    elif 'action blocked' in error_lower or 'try again later' in error_lower:
        return 'actionblocked'
    elif 'banned' in error_lower or 'disabled' in error_lower:
        return 'banned'
    else:
        return ''  # Retryable
```

## Implementation Plan

### Step 1: Define ERROR_PATTERNS class constant

Add a new class constant after `NON_RETRYABLE_ERRORS` (line 93):

```python
# Non-retryable error types - these failures should not be retried
NON_RETRYABLE_ERRORS = {'suspended', 'captcha', 'loggedout', 'actionblocked', 'banned'}

# Error classification patterns - maps error_type to list of substrings to match
# Order matters: first matching error type wins
ERROR_PATTERNS = {
    'suspended': ['suspended', 'account has been suspended'],
    'captcha': ['captcha', 'verify'],
    'loggedout': ['log in', 'logged out', 'sign up'],
    'actionblocked': ['action blocked', 'try again later'],
    'banned': ['banned', 'disabled'],
}
```

### Step 2: Refactor _classify_error() method

Replace the if/elif chain with a dict-based lookup:

```python
def _classify_error(self, error: str) -> str:
    """
    Classify an error message into an error type.

    Uses ERROR_PATTERNS dict for pattern matching. Returns the first
    matching error type from NON_RETRYABLE_ERRORS, or empty string
    for retryable errors.
    """
    if not error:
        return ''
    
    error_lower = error.lower()
    
    for error_type, patterns in self.ERROR_PATTERNS.items():
        if any(pattern in error_lower for pattern in patterns):
            return error_type
    
    return ''  # Retryable
```

### Step 3: Ensure consistency between ERROR_PATTERNS and NON_RETRYABLE_ERRORS

Add a validation assertion in `__init__` (optional but recommended):

```python
def __init__(self, progress_file: str, lock_timeout: float = 30.0):
    # Validate ERROR_PATTERNS keys match NON_RETRYABLE_ERRORS
    assert set(self.ERROR_PATTERNS.keys()) == self.NON_RETRYABLE_ERRORS, \
        f"ERROR_PATTERNS keys must match NON_RETRYABLE_ERRORS"
    # ... rest of __init__
```

## Benefits

1. **Easier to add new error types**: Add a single line to ERROR_PATTERNS dict
2. **Self-documenting**: The dict clearly shows all patterns for each error type
3. **Maintainable**: Patterns are grouped by error type, not scattered in elif branches
4. **DRY**: Error types are defined once in ERROR_PATTERNS, used via iteration
5. **Testable**: Can easily test individual patterns without mocking the whole method

## Location

- File: `progress_tracker.py`
- Lines to modify: 93-97 (add ERROR_PATTERNS), 541-560 (refactor method)

**Test Strategy:**

## Test Strategy

### 1. Syntax and Import Verification
```bash
python -c "from progress_tracker import ProgressTracker; print('Import successful')"
```

### 2. Verify ERROR_PATTERNS Constant Exists
```bash
python -c "
from progress_tracker import ProgressTracker
print('ERROR_PATTERNS:', ProgressTracker.ERROR_PATTERNS)
print('Keys match NON_RETRYABLE_ERRORS:', set(ProgressTracker.ERROR_PATTERNS.keys()) == ProgressTracker.NON_RETRYABLE_ERRORS)
"
```

### 3. Unit Test All Error Classifications
```bash
python -c "
from progress_tracker import ProgressTracker

tracker = ProgressTracker('test_progress.csv')

# Test each error type with various patterns
test_cases = [
    # Suspended
    ('Your account has been suspended', 'suspended'),
    ('Account suspended', 'suspended'),
    
    # Captcha
    ('Please complete the captcha', 'captcha'),
    ('Verify your identity', 'captcha'),
    
    # Logged out
    ('Please log in to continue', 'loggedout'),
    ('You have been logged out', 'loggedout'),
    ('Sign up to continue', 'loggedout'),
    
    # Action blocked
    ('Action blocked. Please try again later', 'actionblocked'),
    ('Try again later', 'actionblocked'),
    
    # Banned
    ('Your account has been banned', 'banned'),
    ('Account disabled for violating terms', 'banned'),
    
    # Retryable (empty string)
    ('Connection timeout', ''),
    ('Network error', ''),
    ('', ''),
    (None, ''),
]

all_passed = True
for error_msg, expected in test_cases:
    result = tracker._classify_error(error_msg)
    status = '✓' if result == expected else '✗'
    if result != expected:
        all_passed = False
    print(f'{status} \"{error_msg}\" -> \"{result}\" (expected \"{expected}\")')

print(f'\nAll tests passed: {all_passed}')

# Cleanup
import os
if os.path.exists('test_progress.csv'):
    os.remove('test_progress.csv')
if os.path.exists('test_progress.csv.lock'):
    os.remove('test_progress.csv.lock')
"
```

### 4. Integration Test with update_job_status()
```bash
python -c "
from progress_tracker import ProgressTracker
import os

tracker = ProgressTracker('test_integration.csv')

# Seed a test job
tracker.seed_jobs([{
    'job_id': 'test_job_1',
    'account': 'test_account',
    'video_path': '/fake/video.mp4',
    'caption': 'Test caption'
}])

# Claim the job
job = tracker.claim_next_job(worker_id=0)
print(f'Claimed job: {job[\"job_id\"]}')

# Fail with a non-retryable error
tracker.update_job_status('test_job_1', 'failed', worker_id=0, error='Account suspended')

# Verify error_type was set correctly
jobs = tracker._read_all_jobs()
job = next(j for j in jobs if j['job_id'] == 'test_job_1')
print(f'Status: {job[\"status\"]}')
print(f'Error type: {job[\"error_type\"]}')
assert job['error_type'] == 'suspended', f'Expected suspended, got {job[\"error_type\"]}'
print('Integration test passed!')

# Cleanup
for f in ['test_integration.csv', 'test_integration.csv.lock']:
    if os.path.exists(f):
        os.remove(f)
"
```

### 5. Verify No Regression in Live System
```bash
# Check current progress file still works
python -c "
from progress_tracker import ProgressTracker
tracker = ProgressTracker('parallel_progress.csv')
stats = tracker.get_statistics()
print(f'Progress file loads correctly: {stats}')
"
```
