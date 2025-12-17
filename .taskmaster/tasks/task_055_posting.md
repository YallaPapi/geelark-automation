# Task ID: 55

**Title:** Update parallel_worker.py to propagate error categories

**Status:** done

**Dependencies:** 51 ✓, 25 ✓

**Priority:** high

**Description:** Modify parallel_worker.py to propagate error classification (category, error_type) from execute_posting_job() through to the progress tracker, enabling the multi-pass retry system to distinguish infrastructure failures from account-level failures.

**Details:**

## Overview

This task implements Phase 4 of the Retry Loop Implementation plan from `reviews/RETRY_LOOP_IMPLEMENTATION_REVIEW.md`. The goal is to modify `parallel_worker.py` to properly propagate error categories (account vs infrastructure) so the retry system can make informed decisions about which failures to retry.

## Implementation Details

### 1. Update execute_posting_job() Return Signature

**File:** `parallel_worker.py` (lines 162-247)

Change the return type from `tuple[bool, str]` to `tuple[bool, str, str, str]`:

```python
def execute_posting_job(
    job: dict,
    worker_config: WorkerConfig,
    config: ParallelConfig,
    logger: logging.Logger,
    tracker=None,
    worker_id: int = None
) -> tuple:
    """
    Execute a single posting job.

    Returns:
        (success: bool, error_message: str, error_category: str, error_type: str)
        
        error_category is one of: 'account', 'infrastructure', 'unknown', or ''
        error_type is the specific error (e.g., 'suspended', 'adb_timeout')
    """
```

### 2. Import ProgressTracker for Error Classification

Add import at top of file (after line 39):

```python
from progress_tracker import ProgressTracker
```

### 3. Wrap Main Try Block with Specific Exception Handling

Replace the generic exception handler (lines 231-235) with specific exception mapping:

```python
    except TimeoutError as e:
        error_msg = f"TimeoutError: {str(e)}"
        logger.error(f"Job {job_id} timeout: {error_msg}")
        logger.debug(traceback.format_exc())
        return False, error_msg, 'infrastructure', 'adb_timeout'
        
    except ConnectionError as e:
        error_msg = f"ConnectionError: {str(e)}"
        logger.error(f"Job {job_id} connection error: {error_msg}")
        logger.debug(traceback.format_exc())
        return False, error_msg, 'infrastructure', 'connection_dropped'
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Job {job_id} exception: {error_msg}")
        logger.debug(traceback.format_exc())
        
        # Use tracker's error classification for unknown exceptions
        category, error_type = '', ''
        if tracker:
            category, error_type = tracker._classify_error(error_msg)
        return False, error_msg, category, error_type
```

### 4. Update Success and Failure Return Paths

**Success case (line 223-225):**
```python
if success:
    logger.info(f"Job {job_id} completed successfully!")
    return True, "", "", ""
```

**Failure from poster (lines 226-229):**
```python
else:
    error = poster.last_error_message or "Post returned False"
    logger.error(f"Job {job_id} failed: {error}")
    # Classify the error
    category, error_type = '', ''
    if tracker:
        category, error_type = tracker._classify_error(error)
    return False, error, category, error_type
```

### 5. Update Pre-Post Verification Failure (lines 198-200)

```python
if not is_valid:
    logger.warning(f"Job {job_id} failed pre-post verification: {error}")
    return False, f"Pre-post verification failed: {error}", 'infrastructure', 'verification_race'
```

### 6. Update run_worker() Main Loop (lines 354-383)

Modify the job execution and status update logic:

```python
# Execute the job
job_id = job['job_id']
attempt_info = f" (retry attempt {job.get('attempts', '?')})" if is_retry else ""
logger.info(f"Processing job {job_id}{attempt_info}")

try:
    success, error, error_category, error_type = execute_posting_job(
        job, worker_config, config, logger,
        tracker=tracker, worker_id=worker_id
    )

    if success:
        tracker.update_job_status(job_id, 'success', worker_id)
        stats['jobs_completed'] += 1
    else:
        # Pass error_category and error_type for retry logic
        tracker.update_job_status(
            job_id, 'failed', worker_id, error=error,
            retry_delay_minutes=config.retry_delay_minutes,
            error_category=error_category,
            error_type=error_type
        )
        stats['jobs_failed'] += 1

except Exception as e:
    error_msg = f"{type(e).__name__}: {str(e)}"
    logger.error(f"Unhandled exception processing job {job_id}: {error_msg}")
    # Classify the exception
    category, etype = '', ''
    if tracker:
        category, etype = tracker._classify_error(error_msg)
    tracker.update_job_status(
        job_id, 'failed', worker_id, error=error_msg,
        retry_delay_minutes=config.retry_delay_minutes,
        error_category=category,
        error_type=etype
    )
    stats['jobs_failed'] += 1
```

### 7. Update update_job_status() Signature in progress_tracker.py

**File:** `progress_tracker.py` (lines 566-573)

Add `error_category` and `error_type` parameters:

```python
def update_job_status(
    self,
    job_id: str,
    status: str,
    worker_id: int,
    error: str = '',
    retry_delay_minutes: float = None,
    error_category: str = '',
    error_type: str = ''
) -> bool:
```

Then in the update logic (around line 620), use provided values or fall back to classification:

```python
# Use provided error_category/error_type if available, otherwise classify
if error_category and error_type:
    job['error_category'] = error_category
    job['error_type'] = error_type
else:
    category, etype = self._classify_error(error)
    job['error_category'] = category
    job['error_type'] = etype
```

### 8. Add error_category to COLUMNS List

**File:** `progress_tracker.py` (line 78-82)

```python
COLUMNS = [
    'job_id', 'account', 'video_path', 'caption', 'status',
    'worker_id', 'claimed_at', 'completed_at', 'error',
    'attempts', 'max_attempts', 'retry_at', 'error_type',
    'error_category', 'pass_number'  # New columns for multi-pass retry
]
```

## Dependencies on Task 51

This task requires Task 51 (Enhance Error Classification with Two-Level Category System) to be completed first, as it:
1. Defines the `ERROR_CATEGORIES` structure with 'account' and 'infrastructure' top-level categories
2. Updates `_classify_error()` to return `(category, error_type)` tuple
3. Adds `error_category` and `pass_number` columns to the CSV schema

## Error Category Mapping Reference

| Exception Type | error_category | error_type |
|---------------|----------------|------------|
| TimeoutError | infrastructure | adb_timeout |
| ConnectionError | infrastructure | connection_dropped |
| Account suspended | account | suspended |
| Captcha required | account | captcha |
| Logged out | account | loggedout |
| Post returned False | infrastructure | claude_stuck |
| Unknown | unknown | (empty) |

**Test Strategy:**

## Test Strategy

### 1. Syntax and Import Verification
```bash
python -c "import parallel_worker; print('Import OK')"
```

### 2. Verify 4-Tuple Return Signature
```bash
python -c "
import inspect
from parallel_worker import execute_posting_job
sig = inspect.signature(execute_posting_job)
print(f'execute_posting_job signature: {sig}')
# Manual verification: docstring should mention 4-tuple return
"
```

### 3. Unit Test - Error Category Propagation
Create a mock test to verify error categories flow through:
```bash
python -c "
from progress_tracker import ProgressTracker
import tempfile
import os

# Create temp progress file
with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    temp_file = f.name

tracker = ProgressTracker(temp_file)
tracker.seed_from_jobs([{
    'job_id': 'test1',
    'account': 'test_account',
    'video_path': '/test.mp4',
    'caption': 'Test'
}])

# Update with explicit error category
tracker.update_job_status(
    'test1', 'failed', worker_id=0,
    error='TimeoutError: ADB timeout',
    error_category='infrastructure',
    error_type='adb_timeout'
)

# Read back and verify
jobs = tracker._read_all_jobs()
job = jobs[0]
assert job['error_category'] == 'infrastructure', f\"Expected 'infrastructure', got '{job['error_category']}'\"
assert job['error_type'] == 'adb_timeout', f\"Expected 'adb_timeout', got '{job['error_type']}'\"
print('Error category propagation test PASSED')

# Cleanup
os.unlink(temp_file)
os.unlink(temp_file + '.lock')
"
```

### 4. Integration Test - TimeoutError Mapping
```bash
python -c "
# Verify TimeoutError is mapped to infrastructure/adb_timeout
# This tests the exception handler mapping in execute_posting_job

# Note: Full integration test requires actual Appium/device
# This verifies the structure is in place
from parallel_worker import execute_posting_job
print('execute_posting_job function exists and can be imported')
print('Integration test: Run with --workers 1 and observe error categorization in logs')
"
```

### 5. CSV Column Verification
```bash
python -c "
from progress_tracker import ProgressTracker
assert 'error_category' in ProgressTracker.COLUMNS, 'error_category column missing'
assert 'pass_number' in ProgressTracker.COLUMNS, 'pass_number column missing'
print(f'COLUMNS: {ProgressTracker.COLUMNS}')
print('CSV columns verification PASSED')
"
```

### 6. End-to-End Test with Real Worker
```bash
# Run a single worker with a test job that will fail
# Verify the CSV shows proper error categorization
python parallel_orchestrator.py --workers 1 --run

# After completion, check the CSV:
python -c "
import csv
with open('parallel_progress.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['status'] == 'failed':
            print(f\"Job {row['job_id']}: category={row.get('error_category', 'N/A')}, type={row.get('error_type', 'N/A')}\")
"
```

### 7. Backward Compatibility Test
Verify old CSV files without error_category column still work:
```bash
python -c "
from progress_tracker import ProgressTracker
import tempfile
import os

# Create an 'old' CSV without error_category column
old_csv = '''job_id,account,video_path,caption,status,worker_id,claimed_at,completed_at,error,attempts,max_attempts,retry_at,error_type
test1,account1,/test.mp4,caption,pending,,,,,,3,,
'''
with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    f.write(old_csv)
    temp_file = f.name

tracker = ProgressTracker(temp_file)
jobs = tracker._read_all_jobs()
print(f'Read {len(jobs)} jobs from old-format CSV')
print('Backward compatibility test PASSED')

os.unlink(temp_file)
"
```

### 8. Verify Logging Shows Categories
After running workers, grep logs for error categorization:
```bash
grep -E "error_category|infrastructure|account" logs/worker_0.log
```

Expected log output format:
```
Job ABC123 failed: TimeoutError: ADB timeout (category: infrastructure, type: adb_timeout)
```
