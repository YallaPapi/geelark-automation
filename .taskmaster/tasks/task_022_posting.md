# Task ID: 22

**Title:** Fix per-account daily cap enforcement with robust progress file handling

**Status:** done

**Dependencies:** 19 ✓, 20 ✓

**Priority:** high

**Description:** Strengthen the per-account daily posting limits by implementing claim-time enforcement that considers both success and claimed job counts, preventing same-account reuse during reseeding, hardening progress file validation to never delete non-empty files, and requiring --reset-day when using --force-reseed.

**Details:**

## Overview

This task addresses 4 specific violations identified in the code review (review1.txt Section 1.1-1.4) that can cause accounts to exceed daily posting limits or lose posting history.

## Implementation Details

### 1.1 Modify `claim_next_job()` to check success+claimed counts at claim time

**File:** `progress_tracker.py`
**Function:** `claim_next_job()` (lines 374-451)

The current implementation checks success counts and accounts_in_use separately. Modify to combine both for total count comparison:

```python
def claim_next_job(self, worker_id: int, max_posts_per_account_per_day: int = 1) -> Optional[Dict[str, Any]]:
    def _claim_operation(jobs):
        # Build combined counts: success + currently claimed
        total_assigned_by_account = {}
        accounts_in_use = set()
        
        for job in jobs:
            account = job.get('account', '')
            if not account:
                continue
            status = job.get('status', '')
            
            if status == self.STATUS_SUCCESS:
                total_assigned_by_account[account] = total_assigned_by_account.get(account, 0) + 1
            elif status == self.STATUS_CLAIMED:
                total_assigned_by_account[account] = total_assigned_by_account.get(account, 0) + 1
                accounts_in_use.add(account)
        
        # Find accounts at daily limit (success + claimed >= max)
        accounts_at_limit = {
            acc for acc, cnt in total_assigned_by_account.items() 
            if cnt >= max_posts_per_account_per_day
        }
        
        # Find pending job where:
        # 1. Has assigned account
        # 2. Account not currently claimed by another worker  
        # 3. Account total (success+claimed) < daily limit
        for job in jobs:
            if job.get('status') != self.STATUS_PENDING:
                continue
            account = job.get('account', '')
            if not account:
                continue
            if account in accounts_in_use:
                logger.debug(f"Skipping job {job['job_id']} - account {account} in use")
                continue
            if account in accounts_at_limit:
                logger.warning(f"Skipping job {job['job_id']} - account {account} at daily limit")
                continue
            
            # Claim the job
            job['status'] = self.STATUS_CLAIMED
            job['worker_id'] = str(worker_id)
            job['claimed_at'] = datetime.now().isoformat()
            logger.info(f"Worker {worker_id} claimed job {job['job_id']} (account: {account})")
            return jobs, dict(job)
        
        return jobs, None
    
    return self._locked_operation(_claim_operation)
```

### 1.2 In `seed_from_scheduler_state()`, consider existing pending/claimed jobs

**File:** `progress_tracker.py`
**Function:** `seed_from_scheduler_state()` (lines 212-330)

Currently only checks success counts. Modify to also exclude accounts with existing pending/claimed jobs for the day:

```python
def seed_from_scheduler_state(self, state_file: str, ...):
    # ... existing code to load state ...
    
    # CRITICAL: Build success_count AND assigned_accounts from existing progress
    success_count_by_account = self._load_success_counts()
    existing_job_ids = set()
    existing_jobs = []
    assigned_accounts_today = set()  # NEW: Track accounts with any job status
    
    if os.path.exists(self.progress_file):
        existing_jobs = self._read_all_jobs()
        for job in existing_jobs:
            existing_job_ids.add(job.get('job_id', ''))
            # NEW: Track accounts that already have ANY job (pending/claimed/success)
            acc = job.get('account', '')
            status = job.get('status', '')
            if acc and status in (self.STATUS_PENDING, self.STATUS_CLAIMED, self.STATUS_SUCCESS):
                assigned_accounts_today.add(acc)
    
    # Filter accounts - exclude those at success limit OR already assigned
    available_accounts = [
        acc for acc in accounts
        if (success_count_by_account.get(acc, 0) < max_posts_per_account_per_day 
            and acc not in assigned_accounts_today)  # NEW condition
    ]
    
    logger.info(f"Available accounts: {len(available_accounts)} "
                f"(excluded {len(assigned_accounts_today)} with existing jobs)")
    
    # ... rest of seeding logic ...
```

### 1.3 Tighten `validate_progress_file()` to NEVER delete non-empty files

**File:** `parallel_orchestrator.py`
**Function:** `validate_progress_file()` (lines 491-522)

Replace the current aggressive deletion behavior with error logging and abort:

```python
def validate_progress_file(progress_file: str) -> bool:
    """
    Check if progress file is valid.
    
    CRITICAL: This function NEVER deletes files. It only validates and reports.
    If the file is empty or corrupt, it logs an error and returns False.
    The operator must manually resolve using --reset-day.
    
    Returns:
        True if file is valid or doesn't exist
        False if file exists but is empty/corrupt (requires manual intervention)
    """
    if not os.path.exists(progress_file):
        return True
    
    try:
        import csv
        with open(progress_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            if len(rows) == 0:
                # CHANGED: Log error and return False instead of deleting
                logger.error(
                    f"VALIDATION FAILED: Progress file {progress_file} is empty (header only).\n"
                    f"  This may indicate a crash during write.\n"
                    f"  ACTION REQUIRED: Run with --reset-day to archive and start fresh,\n"
                    f"  or manually inspect the file before proceeding."
                )
                return False
        return True
        
    except Exception as e:
        # CHANGED: Log error and return False instead of deleting
        logger.error(
            f"VALIDATION FAILED: Progress file {progress_file} appears corrupt: {e}\n"
            f"  ACTION REQUIRED: Run with --reset-day to archive and start fresh,\n"
            f"  or manually inspect/repair the file."
        )
        return False
```

Also update `full_cleanup()` (line 557) to check the return value:

```python
# In full_cleanup():
# 4. Validate progress file - but DO NOT delete it
if not validate_progress_file(config.progress_file):
    logger.warning("Progress file validation failed - manual intervention may be required")
```

### 1.4 Make `--force-reseed` require `--reset-day`

**File:** `parallel_orchestrator.py`
**Functions:** `main()` (lines 921-1016) and `run_parallel_posting()` (lines 820-918)

Add validation in `main()` before executing:

```python
def main():
    # ... argparse setup ...
    args = parser.parse_args()
    
    # NEW: Validate --force-reseed requires --reset-day
    if args.force_reseed and not args.reset_day:
        logger.error("="*60)
        logger.error("SAFETY CHECK FAILED: --force-reseed requires --reset-day")
        logger.error("="*60)
        logger.error("")
        logger.error("Using --force-reseed without --reset-day would wipe posting history")
        logger.error("for the current day, allowing duplicate posts to accounts.")
        logger.error("")
        logger.error("If you intend to start a new day, run:")
        logger.error("  python parallel_orchestrator.py --reset-day --force-reseed --run")
        logger.error("")
        logger.error("If you need to reseed mid-day (DANGEROUS), manually archive the")
        logger.error("progress file first, then run with both flags.")
        logger.error("="*60)
        sys.exit(1)
    
    # ... rest of main() ...
```

Also update `run_parallel_posting()` to validate similarly when called programmatically.

## Files to Modify

1. **`progress_tracker.py`**:
   - `claim_next_job()` (lines 374-451): Add success+claimed counting
   - `seed_from_scheduler_state()` (lines 212-330): Consider pending/claimed jobs in seeding

2. **`parallel_orchestrator.py`**:
   - `validate_progress_file()` (lines 491-522): Remove deletion, only log errors
   - `full_cleanup()` (line 557): Handle validation failure gracefully
   - `main()` (lines 921-1016): Add --force-reseed + --reset-day requirement
   - `run_parallel_posting()` (lines 820-918): Validate force_reseed parameter

## Constants/Config Changes

No new configuration needed - these changes enforce existing `max_posts_per_account_per_day` more strictly.

**Test Strategy:**

## Test Strategy

### 1. Unit Tests for `claim_next_job()` Daily Limit Enforcement

**Test: Claimed jobs count toward daily limit**
```python
# Setup: Create progress CSV with account_a having 1 success
# Add pending job for account_a
# Call claim_next_job with max_posts_per_account_per_day=1
# Expected: Job should NOT be claimed (account at limit)

# Verify with max_posts_per_account_per_day=2
# Expected: Job SHOULD be claimed (1 success < 2 limit)
```

**Test: Account with claimed job cannot get second claim**
```python
# Setup: Create progress CSV with account_a having status=claimed
# Add another pending job for account_a
# Call claim_next_job
# Expected: Second job NOT claimed (account already has 1 claimed)
```

### 2. Unit Tests for `seed_from_scheduler_state()` Reuse Prevention

**Test: Existing pending jobs block reseeding**
```python
# Setup: Create progress CSV with pending job for account_a
# Run seed_from_scheduler_state with jobs for account_a
# Expected: No new jobs added for account_a (already has pending)
```

**Test: Only success jobs were previously counted**
```python
# Regression test: Verify failed jobs don't block seeding
# Setup: Progress CSV with failed job for account_a
# Expected: New job CAN be seeded for account_a
```

### 3. Integration Test for `validate_progress_file()` Safety

**Test: Empty file is NOT deleted**
```bash
# Create empty progress file (header only)
echo "job_id,account,video_path,caption,status,worker_id,claimed_at,completed_at,error" > parallel_progress.csv

# Run orchestrator
python parallel_orchestrator.py --status

# Expected: Error logged, file still exists, orchestrator does NOT proceed
test -f parallel_progress.csv && echo "PASS: File preserved"
```

**Test: Corrupt file is NOT deleted**
```bash
# Create corrupt progress file
echo "garbage data" > parallel_progress.csv

# Run validation
python -c "from parallel_orchestrator import validate_progress_file; print(validate_progress_file('parallel_progress.csv'))"

# Expected: Returns False, file still exists
```

### 4. CLI Validation Test for --force-reseed Safety

**Test: --force-reseed alone is rejected**
```bash
python parallel_orchestrator.py --force-reseed --run 2>&1 | grep -q "requires --reset-day"
# Expected: Exit code 1, error message shown
```

**Test: --force-reseed with --reset-day is accepted**
```bash
# Create dummy progress file
touch parallel_progress.csv

# Run with both flags (won't actually post without accounts)
python parallel_orchestrator.py --force-reseed --reset-day --status
# Expected: No error about --force-reseed
```

### 5. End-to-End Scenario Tests

**Scenario A: Mid-day reseed attempt blocked**
1. Run orchestrator, let some jobs complete
2. Attempt `--force-reseed --run` without `--reset-day`
3. Verify: Rejected with clear error message
4. Verify: Progress file unchanged, history preserved

**Scenario B: Same account cannot get 2 posts in one day**
1. Seed with account_a having 1 pending job
2. Worker claims and completes job (status=success)
3. Run `--force-reseed --reset-day` to start new batch
4. Seed new jobs
5. Verify: account_a gets NO new job (already at limit=1 success)

**Scenario C: Crash recovery preserves limits**
1. Seed jobs, worker claims job for account_a
2. Simulate crash (kill worker mid-job, claim status remains)
3. Restart orchestrator
4. Verify: account_a job NOT re-claimed until stale claim released
5. Verify: After release, account_a can be claimed again (was only claimed, not success)

### 6. Logging Verification

For each test, verify appropriate log messages:
- `claim_next_job`: "Skipping job X - account Y at daily limit of N"
- `seed_from_scheduler_state`: "excluded N with existing jobs"
- `validate_progress_file`: "VALIDATION FAILED" with action instructions
- `main()`: "SAFETY CHECK FAILED: --force-reseed requires --reset-day"
