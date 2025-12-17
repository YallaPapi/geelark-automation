# Task ID: 53

**Title:** Add CLI flags to parallel_orchestrator.py for retry configuration

**Status:** done

**Dependencies:** 2 ✓, 9 ✓, 25 ✓, 52 ✓, 55 ✓

**Priority:** medium

**Description:** Add argparse arguments for retry configuration (--max-passes, --retry-delay, --infra-retry-limit, --no-retry-unknown), create RetryConfig from CLI args, pass it to run_with_retry(), and update --help documentation.

**Details:**

## Implementation Plan

### 1. Add New argparse Arguments (lines ~964-988)

Add the following arguments to the existing ArgumentParser in `main()`:

```python
# Retry Configuration (Phase 5)
retry_group = parser.add_argument_group('Retry Configuration',
    'Options for controlling multi-pass retry behavior')
    
retry_group.add_argument('--max-passes', type=int, default=3,
    help='Maximum retry passes for failed jobs (default: 3)')
    
retry_group.add_argument('--retry-delay', type=int, default=30,
    help='Delay in seconds between retry passes (default: 30)')
    
retry_group.add_argument('--infra-retry-limit', type=int, default=3,
    help='Max retries for infrastructure errors before giving up (default: 3)')
    
retry_group.add_argument('--no-retry-unknown', action='store_true',
    help='Do not retry jobs with unknown/unclassified errors')
```

### 2. Create RetryConfig from CLI Args

After parsing args, create RetryConfig (from retry_manager.py created in Task 52):

```python
from retry_manager import RetryConfig

# In main(), after args = parser.parse_args()
retry_config = RetryConfig(
    max_passes=args.max_passes,
    retry_delay_seconds=args.retry_delay,
    infrastructure_retry_limit=args.infra_retry_limit,
    retry_unknown_errors=not args.no_retry_unknown
)
```

Note: Task 52's RetryConfig needs `retry_unknown_errors: bool = True` field added to support --no-retry-unknown flag.

### 3. Update run_parallel_posting() Signature

Modify `run_parallel_posting()` (lines 826-940) to accept retry_config:

```python
def run_parallel_posting(
    num_workers: int = 3,
    state_file: str = "scheduler_state.json",
    force_reseed: bool = False,
    force_kill_ports: bool = False,
    accounts: List[str] = None,
    retry_all_failed: bool = True,
    retry_include_non_retryable: bool = False,
    retry_config: 'RetryConfig' = None  # NEW parameter
) -> Dict:
```

### 4. Pass RetryConfig to RetryPassManager

Inside `run_parallel_posting()`, pass the retry_config to RetryPassManager:

```python
from retry_manager import RetryPassManager, RetryConfig

# Default if not provided
if retry_config is None:
    retry_config = RetryConfig()

# Create manager with config
retry_mgr = RetryPassManager(tracker, retry_config)

# Use run_with_retry pattern from Task 52
while True:
    pass_num = retry_mgr.start_new_pass()
    logger.info(f"Starting pass {pass_num}/{retry_config.max_passes}")
    
    # ... run workers ...
    
    result = retry_mgr.end_pass()
    if result != PassResult.RETRYABLE_REMAINING:
        break
    
    logger.info(f"Waiting {retry_config.retry_delay_seconds}s before next pass...")
    time.sleep(retry_config.retry_delay_seconds)
```

### 5. Update CLI Call to run_parallel_posting()

In `main()` under `elif args.run:` (lines 1044-1066):

```python
elif args.run:
    # Create RetryConfig from CLI args
    from retry_manager import RetryConfig
    retry_config = RetryConfig(
        max_passes=args.max_passes,
        retry_delay_seconds=args.retry_delay,
        infrastructure_retry_limit=args.infra_retry_limit,
        retry_unknown_errors=not args.no_retry_unknown
    )
    
    results = run_parallel_posting(
        num_workers=args.workers,
        state_file=args.state_file,
        force_reseed=args.force_reseed,
        force_kill_ports=args.force_kill_ports,
        accounts=accounts_list,
        retry_all_failed=True,
        retry_include_non_retryable=args.retry_include_non_retryable,
        retry_config=retry_config  # NEW parameter
    )
```

### 6. Update --help Epilog with Examples

Update the `epilog` in ArgumentParser (lines 948-961) to include retry examples:

```python
epilog="""
Examples:
  # Run with 3 workers
  python parallel_orchestrator.py --workers 3 --run

  # Run with custom retry settings
  python parallel_orchestrator.py --workers 3 --max-passes 5 --retry-delay 60 --run

  # Run with strict mode (no unknown error retries)
  python parallel_orchestrator.py --workers 3 --no-retry-unknown --run

  # Check current status
  python parallel_orchestrator.py --status

  # Stop everything
  python parallel_orchestrator.py --stop-all

  # Just seed progress file
  python parallel_orchestrator.py --seed-only
"""
```

### 7. Update print_config() to Show Retry Settings

Modify `print_config()` in parallel_config.py (lines 183-200) or create a new `print_retry_config()` function to show retry settings at startup:

```python
# In parallel_orchestrator.py run_parallel_posting()
logger.info("Retry Configuration:")
logger.info(f"  Max passes: {retry_config.max_passes}")
logger.info(f"  Retry delay: {retry_config.retry_delay_seconds}s")
logger.info(f"  Infra retry limit: {retry_config.infrastructure_retry_limit}")
logger.info(f"  Retry unknown errors: {retry_config.retry_unknown_errors}")
```

### 8. Validation

Add validation for retry config values:

```python
# In main(), after creating retry_config
if retry_config.max_passes < 1:
    logger.error("--max-passes must be at least 1")
    sys.exit(1)
if retry_config.retry_delay_seconds < 0:
    logger.error("--retry-delay cannot be negative")
    sys.exit(1)
if retry_config.infrastructure_retry_limit < 1:
    logger.error("--infra-retry-limit must be at least 1")
    sys.exit(1)
```

### 9. Import Updates

At the top of parallel_orchestrator.py:

```python
from retry_manager import RetryConfig, RetryPassManager, PassResult
```

Note: This import will only work after Task 52 is completed. Consider using a try/except for backward compatibility during development.

### 10. Update RetryConfig in Task 52

Task 52's RetryConfig dataclass needs the `retry_unknown_errors` field added:

```python
@dataclass
class RetryConfig:
    """Configuration for multi-pass retry behavior."""
    max_passes: int = 3
    retry_delay_seconds: int = 30
    infrastructure_retry_limit: int = 3
    retry_unknown_errors: bool = True  # NEW: Controls --no-retry-unknown
```

**Test Strategy:**

## Test Strategy

### 1. Syntax and Import Verification
```bash
python -c "import parallel_orchestrator; print('Import OK')"
```

### 2. Verify New CLI Arguments Exist
```bash
python parallel_orchestrator.py --help | grep -E "max-passes|retry-delay|infra-retry-limit|no-retry-unknown"
# Expected: All 4 arguments should appear in help output
```

### 3. Test Default Values
```bash
python -c "
import argparse
import sys
sys.argv = ['parallel_orchestrator.py', '--status']
from parallel_orchestrator import main
# Parse args to verify defaults
parser = argparse.ArgumentParser()
parser.add_argument('--max-passes', type=int, default=3)
parser.add_argument('--retry-delay', type=int, default=30)
parser.add_argument('--infra-retry-limit', type=int, default=3)
parser.add_argument('--no-retry-unknown', action='store_true')
args = parser.parse_args([])
assert args.max_passes == 3, f'Expected 3, got {args.max_passes}'
assert args.retry_delay == 30, f'Expected 30, got {args.retry_delay}'
assert args.infra_retry_limit == 3
assert args.no_retry_unknown == False
print('✓ Default values correct')
"
```

### 4. Test Custom Values via CLI
```bash
python -c "
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--max-passes', type=int, default=3)
parser.add_argument('--retry-delay', type=int, default=30)
parser.add_argument('--infra-retry-limit', type=int, default=3)
parser.add_argument('--no-retry-unknown', action='store_true')
args = parser.parse_args(['--max-passes', '5', '--retry-delay', '60', '--infra-retry-limit', '2', '--no-retry-unknown'])
assert args.max_passes == 5
assert args.retry_delay == 60
assert args.infra_retry_limit == 2
assert args.no_retry_unknown == True
print('✓ Custom CLI values parsed correctly')
"
```

### 5. Integration Test - RetryConfig Created from Args
```bash
python -c "
from retry_manager import RetryConfig

# Simulate CLI args
class Args:
    max_passes = 5
    retry_delay = 45
    infra_retry_limit = 2
    no_retry_unknown = True

args = Args()
config = RetryConfig(
    max_passes=args.max_passes,
    retry_delay_seconds=args.retry_delay,
    infrastructure_retry_limit=args.infra_retry_limit,
    retry_unknown_errors=not args.no_retry_unknown
)
assert config.max_passes == 5
assert config.retry_delay_seconds == 45
assert config.infrastructure_retry_limit == 2
assert config.retry_unknown_errors == False
print('✓ RetryConfig created correctly from CLI args')
"
```

### 6. Test Validation Errors
```bash
# Test max_passes < 1 (should error)
python parallel_orchestrator.py --max-passes 0 --run 2>&1 | grep -i "at least 1"

# Test retry_delay < 0 (should error)
python parallel_orchestrator.py --retry-delay -1 --run 2>&1 | grep -i "negative"
```

### 7. Help Text Verification
```bash
# Verify help shows the Retry Configuration group
python parallel_orchestrator.py --help | grep -A 10 "Retry Configuration"

# Verify examples in epilog
python parallel_orchestrator.py --help | grep "max-passes 5"
```

### 8. Dry Run with Custom Retry Settings
```bash
# Run status to verify config is read (won't actually start workers)
python parallel_orchestrator.py --max-passes 5 --retry-delay 60 --status
# Should show configuration without errors
```

### 9. Full Integration Test (Manual)
```bash
# Run with custom retry settings on test accounts
python parallel_orchestrator.py --workers 1 --max-passes 2 --retry-delay 10 --run

# Monitor logs for:
# 1. "Retry Configuration:" block showing custom values
# 2. "Starting pass 1/2" message (not 1/3)
# 3. "Waiting 10s before next pass" (not 30s)
```

### 10. Backward Compatibility Test
```bash
# Run with NO retry args (should use defaults)
python parallel_orchestrator.py --workers 1 --run --seed-only
# Should work without errors, using default retry config
```
