# Task ID: 27

**Title:** Add retry_all_failed() convenience methods to ProgressTracker

**Status:** done

**Dependencies:** 19 ✓, 20 ✓

**Priority:** medium

**Description:** Implement retry_failed_job(job_id) and retry_all_failed() methods that reset failed jobs back to RETRYING status for another attempt, with automatic invocation when the orchestrator starts with --run.

**Details:**

## NOTE: This task is ALREADY IMPLEMENTED

After analyzing the codebase, I found that both methods and the orchestrator integration already exist:

### Existing Implementation in progress_tracker.py

**1. retry_failed_job(job_id: str) -> bool (lines 753-786):**
- Resets a single failed job back to RETRYING status
- Clears attempts counter to '0', error_type, retry_at, worker_id, and completed_at
- Returns True if job was found and reset, False otherwise
- Only operates on jobs with STATUS_FAILED status

**2. retry_all_failed(include_non_retryable: bool = False) -> int (lines 788-833):**
- Bulk-resets ALL failed jobs back to RETRYING status
- Uses NON_RETRYABLE_ERRORS set: {'suspended', 'captcha', 'loggedout', 'actionblocked', 'banned'}
- When include_non_retryable=False (default), skips jobs with non-retryable error types
- When include_non_retryable=True, also retries suspended/captcha/loggedout jobs
- Returns count of jobs reset

### Existing Integration in parallel_orchestrator.py

**Automatic invocation on --run (lines 886-899):**
```python
if retry_all_failed and tracker.exists():
    stats_before = tracker.get_stats()
    if stats_before['failed'] > 0:
        logger.info("RETRYING FAILED JOBS FROM PREVIOUS RUNS")
        count = tracker.retry_all_failed(include_non_retryable=retry_include_non_retryable)
```

**CLI flag support (lines 984-987):**
- `--retry-all-failed`: Standalone command to reset failed jobs
- `--retry-include-non-retryable`: Include non-retryable errors when retrying

**run_parallel_posting() parameters (lines 832-834):**
- `retry_all_failed: bool = True` - Always enabled by default on --run
- `retry_include_non_retryable: bool = False` - Respects non-retryable classification by default

### If Task Requires Changes, Consider:
1. **No changes needed** - Mark this task as already done
2. **Enhancement requests**: Add additional retry options like retry delay, max retry count override, or selective retry by error type

**Test Strategy:**

## Verification of Existing Implementation

### 1. Unit Test retry_failed_job()
```bash
python -c "
from progress_tracker import ProgressTracker
import tempfile, os

# Create temp progress file with failed job
tracker = ProgressTracker(tempfile.mktemp(suffix='.csv'))
tracker.seed_from_jobs([{'job_id': 'test1', 'account': 'acc1', 'video_path': '/v1.mp4', 'caption': 'test'}])
tracker.claim_next_job(worker_id=0)
tracker.update_job_status('test1', 'failed', worker_id=0, error='Test error')

# Verify job is failed
stats = tracker.get_stats()
assert stats['failed'] == 1, f'Expected 1 failed, got {stats}'

# Retry the failed job
result = tracker.retry_failed_job('test1')
assert result == True, 'retry_failed_job should return True'

# Verify job is now retrying
stats = tracker.get_stats()
assert stats['retrying'] == 1, f'Expected 1 retrying, got {stats}'
assert stats['failed'] == 0, f'Expected 0 failed, got {stats}'

print('PASS: retry_failed_job() works correctly')
"
```

### 2. Unit Test retry_all_failed() with non-retryable filtering
```bash
python -c "
from progress_tracker import ProgressTracker
import tempfile

tracker = ProgressTracker(tempfile.mktemp(suffix='.csv'))
tracker.seed_from_jobs([
    {'job_id': 'j1', 'account': 'a1', 'video_path': '/v1.mp4', 'caption': 't1'},
    {'job_id': 'j2', 'account': 'a2', 'video_path': '/v2.mp4', 'caption': 't2'},
    {'job_id': 'j3', 'account': 'a3', 'video_path': '/v3.mp4', 'caption': 't3'},
])

# Claim and fail with different error types
for jid, err in [('j1', 'timeout'), ('j2', 'account suspended'), ('j3', 'network error')]:
    tracker.claim_next_job(worker_id=0)
    tracker.update_job_status(jid, 'failed', worker_id=0, error=err)

# Without include_non_retryable: should retry j1, j3 but NOT j2 (suspended)
count = tracker.retry_all_failed(include_non_retryable=False)
stats = tracker.get_stats()
assert count == 2, f'Expected 2 retried, got {count}'
assert stats['failed'] == 1, f'Expected 1 still failed (suspended), got {stats}'

# With include_non_retryable: should retry j2 too
count2 = tracker.retry_all_failed(include_non_retryable=True)
assert count2 == 1, f'Expected 1 more retried, got {count2}'

print('PASS: retry_all_failed() respects non-retryable errors')
"
```

### 3. Integration Test with Orchestrator --run
```bash
# Create a test scenario with failed jobs
python -c "
from progress_tracker import ProgressTracker
tracker = ProgressTracker('parallel_progress.csv')
if tracker.exists():
    stats = tracker.get_stats()
    print(f'Before: {stats[\"failed\"]} failed, {stats[\"retrying\"]} retrying')
"

# Run orchestrator - verify it auto-retries failed jobs
python parallel_orchestrator.py --status

# If failed > 0, run with --run (dry) to see retry logic trigger:
# python parallel_orchestrator.py --workers 1 --run
# Look for log: "RETRYING FAILED JOBS FROM PREVIOUS RUNS"
```

### 4. Manual CLI Test
```bash
# Test standalone retry command
python parallel_orchestrator.py --retry-all-failed
python parallel_orchestrator.py --retry-all-failed --retry-include-non-retryable
```
