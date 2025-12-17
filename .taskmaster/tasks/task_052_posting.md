# Task ID: 52

**Title:** Integrate RetryPassManager into parallel_orchestrator.py

**Status:** done

**Dependencies:** 9 ✓, 25 ✓, 51 ✓, 54 ✓

**Priority:** high

**Description:** Create a run_with_retry() function that wraps the existing worker loop in a multi-pass retry system, looping while PassResult == RETRYABLE_REMAINING, with configurable delays between passes and pass-level summary logging.

**Details:**

## Implementation Overview

This task integrates the `RetryPassManager` (from Task 52's `retry_manager.py`) into `parallel_orchestrator.py` to enable automatic multi-pass retry of infrastructure failures.

## Files to Modify

**parallel_orchestrator.py** - Add the following:

### 1. Import the RetryPassManager

```python
# Add near top with other imports
from retry_manager import RetryPassManager, RetryConfig, PassResult
```

### 2. Create run_with_retry() Function

Add a new function that wraps the existing single-pass logic:

```python
def run_with_retry(
    num_workers: int = 3,
    state_file: str = "scheduler_state.json",
    accounts: List[str] = None,
    retry_config: RetryConfig = None,
    force_kill_ports: bool = False
) -> Dict:
    """
    Run parallel posting with automatic multi-pass retry for infrastructure failures.
    
    This function implements the retry loop described in RETRY_LOOP_IMPLEMENTATION_REVIEW.md:
    - Pass 1: Try all pending jobs
    - Categorize failures (account vs infrastructure)
    - Pass 2+: Retry only infrastructure failures
    - Repeat until ALL_COMPLETE, ONLY_NON_RETRYABLE, or MAX_PASSES_REACHED
    
    Args:
        num_workers: Number of parallel workers
        state_file: Path to scheduler_state.json
        accounts: List of accounts for job distribution
        retry_config: RetryConfig with max_passes, retry_delay_seconds, etc.
                     Defaults to RetryConfig() if not provided
        force_kill_ports: Force kill processes blocking required ports
    
    Returns:
        Dict with final stats and pass history
    """
    global _active_config, _shutdown_requested
    
    # Use default config if not provided
    if retry_config is None:
        retry_config = RetryConfig()
    
    setup_signal_handlers()
    config = get_config(num_workers=num_workers)
    _active_config = config
    
    # Pre-run checks (same as run_parallel_posting)
    has_conflicts, conflicts = check_for_running_orchestrators()
    if has_conflicts:
        logger.error("CONFLICT: Other orchestrator processes running!")
        return {'error': 'orchestrator_conflict', 'conflicts': conflicts}
    
    print_config(config)
    config.ensure_logs_dir()
    
    # Initial cleanup
    full_cleanup(config)
    
    # Initialize tracker and retry manager
    tracker = ProgressTracker(config.progress_file)
    retry_manager = RetryPassManager(tracker, retry_config)
    
    # Seed progress file if needed
    if not tracker.exists():
        if not accounts:
            logger.error("No accounts specified")
            return {'error': 'no_accounts'}
        count = seed_progress_file(config, state_file, accounts)
        if count == 0:
            return {'error': 'no_jobs'}
    
    # Multi-pass retry loop
    result = PassResult.RETRYABLE_REMAINING
    
    try:
        while result == PassResult.RETRYABLE_REMAINING and not _shutdown_requested:
            # Start new pass
            pass_num = retry_manager.start_new_pass()
            
            logger.info("=" * 60)
            logger.info(f"=== PASS {pass_num} OF {retry_config.max_passes} ===")
            logger.info("=" * 60)
            
            # Start workers for this pass
            processes = start_all_workers(config)
            
            # Monitor until all workers complete
            monitor_workers(processes, config)
            
            # End pass and determine next action
            result = retry_manager.end_pass()
            
            # Log pass summary
            pass_stats = retry_manager.get_current_pass_stats()
            _log_pass_summary(pass_num, pass_stats, result)
            
            # Delay between passes if continuing
            if result == PassResult.RETRYABLE_REMAINING:
                delay = retry_config.retry_delay_seconds
                logger.info(f"Waiting {delay}s before next pass...")
                
                # Interruptible sleep
                for _ in range(delay):
                    if _shutdown_requested:
                        break
                    time.sleep(1)
                
                # Clean up between passes
                full_cleanup(config)
                
    finally:
        # Final cleanup
        full_cleanup(config)
    
    # Build final results
    final_stats = tracker.get_stats()
    return {
        **final_stats,
        'pass_count': retry_manager.current_pass,
        'final_result': result.value,
        'pass_history': [vars(ps) for ps in retry_manager.pass_history]
    }
```

### 3. Add Pass Summary Logger Helper

```python
def _log_pass_summary(pass_num: int, stats: 'PassStats', result: PassResult) -> None:
    """Log a summary of the completed pass."""
    logger.info("-" * 60)
    logger.info(f"PASS {pass_num} SUMMARY")
    logger.info("-" * 60)
    logger.info(f"  Jobs processed: {stats.jobs_processed}")
    logger.info(f"  Successes:      {stats.success_count}")
    logger.info(f"  Failed (account):        {stats.failed_account}")
    logger.info(f"  Failed (infrastructure): {stats.failed_infrastructure}")
    logger.info(f"  Failed (unknown):        {stats.failed_unknown}")
    logger.info(f"  Result: {result.value}")
    logger.info("-" * 60)
```

### 4. Update CLI Arguments in main()

Add new CLI arguments for retry configuration:

```python
# In argument parser section
parser.add_argument('--max-passes', type=int, default=3,
                    help='Maximum retry passes (default: 3)')
parser.add_argument('--retry-delay', type=int, default=30,
                    help='Seconds between retry passes (default: 30)')
parser.add_argument('--infra-retry-limit', type=int, default=3,
                    help='Max retries per job for infrastructure errors (default: 3)')
```

### 5. Update --run Handler

Modify the `--run` branch to use `run_with_retry()`:

```python
elif args.run:
    # Build retry config from CLI args
    retry_config = RetryConfig(
        max_passes=args.max_passes,
        retry_delay_seconds=args.retry_delay,
        infrastructure_retry_limit=args.infra_retry_limit
    )
    
    results = run_with_retry(
        num_workers=args.workers,
        state_file=args.state_file,
        accounts=accounts_list,
        retry_config=retry_config,
        force_kill_ports=args.force_kill_ports
    )
    
    if results.get('error'):
        sys.exit(1)
```

## Key Design Decisions

1. **Interruptible delays**: The delay between passes checks `_shutdown_requested` every second to allow clean Ctrl+C handling

2. **Full cleanup between passes**: Call `full_cleanup(config)` between passes to stop phones and free resources before next pass

3. **Pass stats logging**: Log detailed pass summaries with error category breakdowns to help diagnose patterns

4. **Backward compatibility**: Keep `run_parallel_posting()` available for single-pass use; `run_with_retry()` is the new default

5. **Configurable via CLI**: All retry parameters exposed via command line for operational flexibility

## Integration with Existing Code

- Reuses existing `start_all_workers()`, `monitor_workers()`, `full_cleanup()` functions
- Relies on `RetryPassManager` from retry_manager.py (Task 52) for pass state management
- Uses enhanced `ProgressTracker._classify_error()` returning (category, error_type) from Task 51
- Maintains all existing safety checks (orchestrator conflict detection, daily limits, etc.)

**Test Strategy:**

## Test Strategy

### 1. Unit Test - Import and Instantiation
```bash
python -c "
from parallel_orchestrator import run_with_retry
from retry_manager import RetryConfig, PassResult
print('Import OK')
config = RetryConfig(max_passes=2, retry_delay_seconds=10)
print(f'RetryConfig: max_passes={config.max_passes}, delay={config.retry_delay_seconds}')
"
```

### 2. Unit Test - CLI Argument Parsing
```bash
# Verify new arguments are recognized
python parallel_orchestrator.py --help 2>&1 | grep -E "(max-passes|retry-delay|infra-retry-limit)"
```

### 3. Integration Test - Single Pass (All Success)
```bash
# Create test state with 2 jobs that will succeed
# Expect: 1 pass, result = ALL_COMPLETE
python parallel_orchestrator.py --run --workers 1 --max-passes 3 --accounts test_account
# Verify logs show "PASS 1 SUMMARY" and final result ALL_COMPLETE
```

### 4. Integration Test - Multi-Pass (Infrastructure Retry)
```bash
# Mock scenario: first pass has ADB timeout errors
# Expect: Pass 1 fails some jobs with infrastructure errors
#         Pass 2 retries those jobs
#         Final result shows reduced failures
```

Manual verification steps:
1. Start with jobs that will fail with infrastructure errors (e.g., device not ready)
2. Observe pass 1 completing with failures
3. Observe delay message between passes
4. Observe pass 2 starting and retrying failed jobs
5. Check final summary shows pass_count > 1

### 5. Integration Test - Non-Retryable Errors
```bash
# Scenario: Account suspended errors
# Expect: 1 pass only, result = ONLY_NON_RETRYABLE
# Jobs with suspended accounts should NOT be retried in pass 2
```

### 6. Integration Test - Max Passes Reached
```bash
python parallel_orchestrator.py --run --workers 1 --max-passes 2 --retry-delay 5
# Force infrastructure failures that persist
# Expect: Pass 1 fails, Pass 2 fails, result = MAX_PASSES_REACHED
```

### 7. Graceful Shutdown Test
```bash
# Start with --max-passes 5 and jobs that will fail
python parallel_orchestrator.py --run --workers 2 --max-passes 5 &
sleep 10
# Send Ctrl+C during delay between passes
# Verify: Clean shutdown, phones stopped, no orphaned processes
```

### 8. Pass Summary Logging Verification
Run any test and verify logs contain:
- "=== PASS N OF M ===" header
- "PASS N SUMMARY" section with:
  - Jobs processed count
  - Success/failure breakdown by category
  - Result string (all_complete/retryable_remaining/etc.)
- Delay message if continuing to next pass

### 9. CLI Parameter Verification
```bash
# Test custom retry parameters
python parallel_orchestrator.py --run --workers 1 --max-passes 5 --retry-delay 60 --infra-retry-limit 2 --status
# Verify config shows correct values
```

### 10. Backward Compatibility Test
```bash
# Ensure old invocation style still works (defaults applied)
python parallel_orchestrator.py --run --workers 2
# Should use default RetryConfig values
```
