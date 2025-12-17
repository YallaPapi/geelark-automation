# Task ID: 21

**Title:** Port retry logic from PostingScheduler to parallel orchestrator/worker system

**Status:** done

**Dependencies:** 19 ✓

**Priority:** high

**Description:** Add automatic retry capabilities to the parallel posting system by porting the existing retry patterns from PostingScheduler, including attempts tracking, RETRYING status, retry delay configuration, and periodic retry job reclamation.

**Details:**

## Overview
The existing `posting_scheduler.py` has a robust auto-retry mechanism (lines 294-300, 809-924) that needs to be ported to the parallel orchestrator/worker architecture. Currently, jobs that fail in the parallel system remain permanently failed.

## Implementation Details

### 1. Extend progress_tracker.py with retry fields and status

**Add new status constant (around line 83):**
```python
STATUS_RETRYING = 'retrying'
```

**Extend COLUMNS list (line 73-76) to include retry tracking:**
```python
COLUMNS = [
    'job_id', 'account', 'video_path', 'caption', 'status',
    'worker_id', 'claimed_at', 'completed_at', 'error',
    'attempts', 'max_attempts', 'last_attempt', 'error_type'  # NEW
]
```

**Add new method `get_retry_jobs()` to ProgressTracker class:**
```python
def get_retry_jobs(self, retry_delay_minutes: float = 0.25) -> List[Dict[str, Any]]:
    """Get jobs that are in RETRYING status and ready for retry.
    
    A job is ready for retry if:
    1. status == STATUS_RETRYING
    2. (now - last_attempt) >= retry_delay_minutes
    
    Args:
        retry_delay_minutes: Minimum time since last attempt before retry
        
    Returns:
        List of jobs ready to be retried
    """
    jobs = self._read_all_jobs()
    ready_jobs = []
    now = datetime.now()
    
    for job in jobs:
        if job.get('status') == self.STATUS_RETRYING:
            last_attempt = job.get('last_attempt', '')
            if last_attempt:
                try:
                    attempt_time = datetime.fromisoformat(last_attempt)
                    elapsed_minutes = (now - attempt_time).total_seconds() / 60
                    if elapsed_minutes >= retry_delay_minutes:
                        ready_jobs.append(job)
                except:
                    ready_jobs.append(job)  # If can't parse, allow retry
            else:
                ready_jobs.append(job)
    
    return ready_jobs
```

**Update seed_from_scheduler_state() to initialize retry fields in new jobs (around line 307-317):**
```python
new_jobs.append({
    'job_id': job.get('id', ''),
    'account': assigned_account,
    'video_path': job.get('video_path', ''),
    'caption': job.get('caption', ''),
    'status': self.STATUS_PENDING,
    'worker_id': '',
    'claimed_at': '',
    'completed_at': '',
    'error': '',
    'attempts': '0',           # NEW
    'max_attempts': '3',       # NEW - default from posting_scheduler.py
    'last_attempt': '',        # NEW
    'error_type': ''           # NEW
})
```

### 2. Extend parallel_config.py with retry settings

Add these fields to ParallelConfig dataclass:
```python
@dataclass
class ParallelConfig:
    # ... existing fields ...
    retry_delay_minutes: float = 0.25  # 15 seconds, same as PostingScheduler
    max_attempts: int = 3  # Same as PostJob.max_attempts default
    non_retryable_errors: tuple = ('suspended', 'captcha', 'logged_out', 'action_blocked')
```

### 3. Update parallel_worker.py to handle retries

**Modify the main job processing loop (around lines 279-340) to:**

a) **Increment attempts when claiming a job:**
   - After claiming, increment the `attempts` field
   - Update `last_attempt` timestamp

b) **Check claim_next_job AND get_retry_jobs:**
```python
# First try to claim a pending job
job = tracker.claim_next_job(worker_id, max_posts_per_account_per_day=config.max_posts_per_account_per_day)

# If no pending jobs, check for retry jobs that are ready
if job is None:
    retry_jobs = tracker.get_retry_jobs(retry_delay_minutes=config.retry_delay_minutes)
    if retry_jobs:
        # Claim the first ready retry job
        job = tracker.claim_retry_job(retry_jobs[0]['job_id'], worker_id)
```

c) **After job failure, decide retry vs permanent fail (port logic from posting_scheduler.py lines 905-915):**
```python
def should_retry(job: dict, error_type: str, config: ParallelConfig) -> bool:
    """Determine if a failed job should be retried."""
    # Don't retry account-level errors
    if error_type in config.non_retryable_errors:
        return False
    
    attempts = int(job.get('attempts', 0))
    max_attempts = int(job.get('max_attempts', config.max_attempts))
    
    return attempts < max_attempts
```

d) **Update job status based on retry decision:**
```python
if success:
    tracker.update_job_status(job_id, 'success', worker_id)
else:
    error_type = extract_error_type(error)  # Parse error message
    if should_retry(job, error_type, config):
        tracker.update_job_status(
            job_id, 
            tracker.STATUS_RETRYING,  # Move to RETRYING instead of FAILED
            worker_id, 
            error=error,
            attempts=int(job.get('attempts', 0)) + 1,
            error_type=error_type
        )
        logger.info(f"Job {job_id} will retry (attempt {attempts}/{max_attempts})")
    else:
        tracker.update_job_status(job_id, 'failed', worker_id, error=error)
        logger.info(f"Job {job_id} permanently failed: {error_type}")
```

### 4. Add claim_retry_job method to ProgressTracker

```python
def claim_retry_job(self, job_id: str, worker_id: int, max_posts_per_account_per_day: int = 1) -> Optional[Dict[str, Any]]:
    """Claim a specific job that is in RETRYING status.
    
    This is similar to claim_next_job but for a specific retry job.
    Still enforces account-in-use and daily limit checks.
    """
    def _claim_retry_operation(jobs):
        # Build accounts in use and success counts (same as claim_next_job)
        accounts_in_use = set()
        success_counts = {}
        for job in jobs:
            if job.get('status') == self.STATUS_CLAIMED:
                if job.get('account'):
                    accounts_in_use.add(job.get('account'))
            elif job.get('status') == self.STATUS_SUCCESS:
                acc = job.get('account', '')
                if acc:
                    success_counts[acc] = success_counts.get(acc, 0) + 1
        
        # Find and claim the target job
        for job in jobs:
            if job.get('job_id') == job_id and job.get('status') == self.STATUS_RETRYING:
                account = job.get('account', '')
                
                # Safety checks
                if not account:
                    return jobs, None
                if account in accounts_in_use:
                    return jobs, None
                if success_counts.get(account, 0) >= max_posts_per_account_per_day:
                    return jobs, None
                
                # Claim the job
                job['status'] = self.STATUS_CLAIMED
                job['worker_id'] = str(worker_id)
                job['claimed_at'] = datetime.now().isoformat()
                return jobs, dict(job)
        
        return jobs, None
    
    return self._locked_operation(_claim_retry_operation)
```

### 5. Update update_job_status to handle retry fields

Modify `update_job_status` method signature and implementation:
```python
def update_job_status(
    self,
    job_id: str,
    status: str,
    worker_id: int,
    error: str = '',
    attempts: int = None,
    error_type: str = ''
) -> bool:
    """Update job status with optional retry tracking fields."""
    def _update_operation(jobs):
        for job in jobs:
            if job.get('job_id') == job_id:
                job['status'] = status
                job['worker_id'] = str(worker_id)
                job['completed_at'] = datetime.now().isoformat()
                job['error'] = error[:500] if error else ''
                job['last_attempt'] = datetime.now().isoformat()  # Always update
                
                if attempts is not None:
                    job['attempts'] = str(attempts)
                if error_type:
                    job['error_type'] = error_type
                    
                return jobs, True
        return jobs, False
    
    return self._locked_operation(_update_operation)
```

### 6. Update get_stats to include retrying count

```python
def get_stats(self) -> Dict[str, int]:
    """Get job status statistics."""
    jobs = self._read_all_jobs()
    stats = {
        'total': len(jobs),
        'pending': 0,
        'claimed': 0,
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'retrying': 0  # NEW
    }
    for job in jobs:
        status = job.get('status', '')
        if status in stats:
            stats[status] += 1
    return stats
```

### Reference Files
- Source patterns: `posting_scheduler.py` lines 294-300 (PostStatus enum), 809-924 (execute_job retry logic), 793-795 (get_retry_jobs)
- Target files: `progress_tracker.py`, `parallel_worker.py`, `parallel_config.py`

**Test Strategy:**

## Testing Strategy

### 1. Unit Tests for ProgressTracker

**Test new STATUS_RETRYING constant:**
```python
def test_status_retrying_exists():
    assert ProgressTracker.STATUS_RETRYING == 'retrying'
```

**Test get_retry_jobs() method:**
- Create progress file with jobs in various states (pending, claimed, success, failed, retrying)
- Set `last_attempt` timestamps at different times
- Verify only RETRYING jobs with elapsed delay are returned
- Test edge cases: missing last_attempt, unparseable timestamps

**Test claim_retry_job() method:**
- Verify it claims only RETRYING jobs (not pending/claimed/failed)
- Verify account-in-use check prevents claiming
- Verify daily limit check prevents claiming
- Verify job transitions to CLAIMED status after successful claim

**Test updated update_job_status():**
- Verify attempts field is updated correctly
- Verify error_type field is stored
- Verify last_attempt is updated

### 2. Integration Tests for Parallel Worker

**Test retry flow end-to-end:**
1. Seed progress file with test jobs
2. Manually claim a job
3. Call update_job_status with RETRYING status
4. Verify job appears in get_retry_jobs() after delay
5. Verify worker can claim the retry job
6. Complete job, verify it reaches success or permanent fail

**Test non-retryable errors:**
1. Simulate failure with error_type='suspended'
2. Verify job goes directly to FAILED (not RETRYING)
3. Verify job does NOT appear in get_retry_jobs()

**Test max_attempts exhaustion:**
1. Create job with attempts=2, max_attempts=3
2. Fail the job
3. Verify it moves to RETRYING (attempt 3)
4. Fail again
5. Verify it moves to FAILED (exhausted retries)

### 3. Live Tests (Per CLAUDE.md Instructions)

**Run with actual orchestrator:**
```bash
# Seed with a few test accounts
python parallel_orchestrator.py --seed-only

# Manually edit one job in parallel_progress.csv to have a bad video path (will fail)
# Run with 1 worker to observe retry behavior
python parallel_orchestrator.py --run --workers 1
```

**Verify in logs:**
- Check worker log for "will retry" messages
- Check progress CSV for RETRYING status entries
- Verify retrying jobs get re-claimed after delay
- Verify jobs eventually succeed or reach permanent failure

### 4. Regression Tests

**Verify backward compatibility:**
- Progress files without new columns should still work
- Workers should handle missing attempts/max_attempts gracefully (use defaults)
- Existing pending/claimed/success/failed flows unchanged

### 5. Stress Test

**Run with 5 workers as specified in review1.txt:**
```bash
python parallel_orchestrator.py --run --workers 5
```
Verify:
- Multiple workers can claim retry jobs without conflicts
- No duplicate posts occur during retry handling
- Stats correctly show retrying count
