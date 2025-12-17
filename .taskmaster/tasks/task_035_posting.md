# Task ID: 35

**Title:** Move timedelta import to top of progress_tracker.py per PEP8

**Status:** done

**Dependencies:** None

**Priority:** low

**Description:** Move the `from datetime import timedelta` import statement from inside the `update_job_status()` method (line 632) to the module-level imports at the top of progress_tracker.py, alongside the existing `from datetime import datetime` import on line 40.

**Details:**

## Problem Statement

The `progress_tracker.py` module has an import statement inside a function, violating PEP8 style guidelines:

**Location: Line 632 (inside `update_job_status()` method)**
```python
# Lines 629-633 in update_job_status():
else:
    # Retryable - set to retrying with delay
    job['status'] = self.STATUS_RETRYING
    from datetime import timedelta  # <-- THIS SHOULD BE AT TOP
    retry_at = datetime.now() + timedelta(minutes=retry_delay_minutes)
```

## Existing Import (Line 40)
```python
from datetime import datetime
```

## Implementation Steps

### Step 1: Modify the existing datetime import at line 40
Change:
```python
from datetime import datetime
```
To:
```python
from datetime import datetime, timedelta
```

### Step 2: Remove the inline import at line 632
Delete the entire line:
```python
from datetime import timedelta
```

The surrounding code (lines 629-635) should become:
```python
else:
    # Retryable - set to retrying with delay
    job['status'] = self.STATUS_RETRYING
    retry_at = datetime.now() + timedelta(minutes=retry_delay_minutes)
    job['retry_at'] = retry_at.isoformat()
```

## Why This Matters

1. **PEP8 Compliance**: All imports should be at the top of the module
2. **Performance**: While Python caches imports, having them at module level makes the import cost explicit at load time rather than hidden in function execution
3. **Readability**: Developers can see all dependencies at the top of the file
4. **Consistency**: The module already imports `datetime` from the `datetime` module - adding `timedelta` to the same import follows a clean pattern

**Test Strategy:**

## Test Strategy

### 1. Syntax and Import Verification
```bash
# Verify the file has no syntax errors and imports correctly
python -c "import progress_tracker; print('Import successful')"
```

### 2. Verify timedelta is in module-level imports
```bash
# Check that timedelta is imported at module level
python -c "from progress_tracker import ProgressTracker; import progress_tracker; print('timedelta' in dir(progress_tracker))"
```

### 3. Verify no inline import remains
```bash
# Search for any remaining inline imports of timedelta
grep -n "from datetime import timedelta" progress_tracker.py
# Should return NO results after the fix
```

### 4. Functional Test - Retry Logic
```bash
# Test that the retry functionality still works correctly
python -c "
from progress_tracker import ProgressTracker
import os
import tempfile

# Create a temp progress file
with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    test_file = f.name

tracker = ProgressTracker(test_file)

# Seed a test job
tracker.seed_from_jobs([{
    'job_id': 'test123',
    'account': 'test_account',
    'video_path': '/fake/path.mp4',
    'caption': 'Test caption'
}])

# Claim the job
job = tracker.claim_next_job(worker_id=0)
assert job is not None, 'Failed to claim job'
assert job['job_id'] == 'test123', 'Wrong job claimed'

# Fail the job - this triggers the timedelta usage for retry scheduling
tracker.update_job_status('test123', 'failed', worker_id=0, error='Test error', retry_delay_minutes=5)

# Verify job is in retrying status with retry_at set
jobs = tracker._read_all_jobs()
assert len(jobs) == 1, f'Expected 1 job, got {len(jobs)}'
assert jobs[0]['status'] == 'retrying', f'Expected retrying status, got {jobs[0][\"status\"]}'
assert jobs[0]['retry_at'], 'retry_at should be set'

print('SUCCESS: Retry logic works correctly with moved import')

# Cleanup
os.remove(test_file)
if os.path.exists(test_file + '.lock'):
    os.remove(test_file + '.lock')
"
```

### 5. Verify PEP8 compliance
```bash
# Run flake8 or pycodestyle on the imports section
python -m py_compile progress_tracker.py && echo "Compilation successful"
```

### 6. Line 40 structure verification
```bash
# Confirm the new import structure at line 40
python -c "
with open('progress_tracker.py', 'r') as f:
    lines = f.readlines()
    # Check line 40 (0-indexed: line 39)
    import_line = lines[39]
    assert 'from datetime import datetime, timedelta' in import_line, f'Expected combined import, got: {import_line}'
    print(f'Line 40: {import_line.strip()}')
    print('SUCCESS: Import structure correct')
"
```
