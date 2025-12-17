# Task ID: 56

**Title:** Improve Retry Pass Visibility with Clear Markers and Configurable Limits

**Status:** pending

**Dependencies:** 52 ✓, 53 ✓, 54 ✓

**Priority:** medium

**Description:** Enhance the multi-pass retry system visibility by adding prominent PASS 1/2/3 markers in logs, increasing default max_passes from 3 to 5, adding --max-attempts-per-job CLI flag, showing pass summaries after each pass, and ensuring proper delays between retry passes.

**Details:**

## Overview

The multi-pass retry system exists in `retry_manager.py` and `parallel_orchestrator.py` but needs improved visibility and configurability. This task enhances the user experience by making retry progress clearer and more controllable.

## Implementation Details

### 1. Add Prominent PASS Markers in Logs

**File:** `retry_manager.py` (lines 136-156)

Update `start_new_pass()` to include more prominent markers:

```python
def start_new_pass(self) -> int:
    """Start a new retry pass with prominent logging."""
    self.current_pass += 1

    # More prominent pass markers - 80 chars wide with banner
    logger.info("")
    logger.info("=" * 80)
    logger.info("=" * 80)
    logger.info(f"    ██████╗  █████╗ ███████╗███████╗    {self.current_pass}")
    logger.info(f"    ██╔══██╗██╔══██╗██╔════╝██╔════╝")
    logger.info(f"    ██████╔╝███████║███████╗███████╗    PASS {self.current_pass} OF {self.config.max_passes}")
    logger.info(f"    ██╔═══╝ ██╔══██║╚════██║╚════██║")
    logger.info(f"    ██║     ██║  ██║███████║███████║")
    logger.info(f"    ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝")
    logger.info("=" * 80)
    logger.info("=" * 80)
    logger.info("")
    
    # ... rest of method
```

Alternatively, a simpler but still prominent marker:

```python
logger.info("")
logger.info("#" * 80)
logger.info(f"#{'':^78}#")
logger.info(f"#{'PASS ' + str(self.current_pass) + ' OF ' + str(self.config.max_passes):^78}#")
logger.info(f"#{'':^78}#")
logger.info("#" * 80)
logger.info("")
```

### 2. Update Default max_passes from 3 to 5

**File:** `retry_manager.py` (line 62)

```python
@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_passes: int = 5  # Changed from 3 to 5
    retry_delay_seconds: int = 30
    infrastructure_retry_limit: int = 3
    unknown_error_is_retryable: bool = True
```

**File:** `parallel_orchestrator.py` (line 1043)

```python
parser.add_argument('--max-passes', type=int, default=5,  # Changed from 3 to 5
                    help='Maximum number of retry passes (default: 5)')
```

**File:** `config.py` - Add new constant (around line 82):

```python
# ==================== RETRY SETTINGS ====================

# Maximum retry passes for the orchestrator
MAX_RETRY_PASSES: int = 5

# Maximum retry attempts for failed jobs (per job)
MAX_RETRY_ATTEMPTS: int = 5

# Delay between retries in minutes
RETRY_DELAY_MINUTES: int = 5
```

### 3. Add --max-attempts-per-job CLI Flag

**File:** `parallel_orchestrator.py` (around line 1047)

Add new argument to the retry configuration group:

```python
retry_group.add_argument('--max-attempts-per-job', type=int, default=5,
    help='Maximum retry attempts per individual job before marking as failed (default: 5)')
```

**File:** `retry_manager.py` - Update RetryConfig:

```python
@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_passes: int = 5
    retry_delay_seconds: int = 30
    infrastructure_retry_limit: int = 3  # Per-job limit for infrastructure errors
    max_attempts_per_job: int = 5  # NEW: Total attempts per job across all passes
    unknown_error_is_retryable: bool = True
```

**File:** `parallel_orchestrator.py` - Pass to RetryConfig (around line 1120):

```python
retry_cfg = RetryConfig(
    max_passes=args.max_passes,
    retry_delay_seconds=args.retry_delay,
    infrastructure_retry_limit=args.infra_retry_limit,
    max_attempts_per_job=args.max_attempts_per_job,  # NEW
    unknown_error_is_retryable=not args.no_retry_unknown
)
```

### 4. Show Retry Pass Summary at End of Each Pass

**File:** `retry_manager.py` - Enhance `end_pass()` method (around line 186-194):

```python
def end_pass(self) -> PassResult:
    """End current pass, categorize failures, and show comprehensive summary."""
    if not self.pass_history:
        return PassResult.ALL_COMPLETE

    stats = self.pass_history[-1]
    stats.end_time = datetime.now()

    # ... existing stats gathering ...

    # Enhanced pass summary with box drawing
    logger.info("")
    logger.info("╔" + "═" * 78 + "╗")
    logger.info(f"║{'PASS ' + str(self.current_pass) + ' SUMMARY':^78}║")
    logger.info("╠" + "═" * 78 + "╣")
    logger.info(f"║  {'Jobs Processed:':<30} {stats.total_jobs:>44} ║")
    logger.info(f"║  {'✓ Succeeded:':<30} {stats.succeeded:>44} ║")
    logger.info(f"║  {'✗ Failed (account issues):':<30} {stats.failed_account:>44} ║")
    logger.info(f"║  {'⟳ Failed (infrastructure):':<30} {stats.failed_infrastructure:>44} ║")
    logger.info(f"║  {'? Failed (unknown):':<30} {stats.failed_unknown:>44} ║")
    logger.info("╠" + "═" * 78 + "╣")
    logger.info(f"║  {'Success Rate:':<30} {stats.success_rate:.1f}%{' ':>41} ║")
    logger.info(f"║  {'Duration:':<30} {str(stats.duration) if stats.duration else 'N/A':>44} ║")
    logger.info("╠" + "═" * 78 + "╣")
    
    # Show what's next
    next_action = ""
    if retryable_count == 0:
        if stats.failed_account > 0:
            next_action = "STOPPING: Only non-retryable account failures remain"
        else:
            next_action = "COMPLETE: All jobs succeeded!"
    elif self.current_pass >= self.config.max_passes:
        next_action = f"STOPPING: Max passes ({self.config.max_passes}) reached"
    else:
        next_action = f"CONTINUING: {retryable_count} jobs will retry in pass {self.current_pass + 1}"
    
    logger.info(f"║  {'Next:':<30} {next_action[:44]:>44} ║")
    logger.info("╚" + "═" * 78 + "╝")
    logger.info("")

    # ... rest of method
```

### 5. Ensure Proper Delay Between Retry Passes

**File:** `parallel_orchestrator.py` (lines 954-959)

The delay already exists but needs better logging and interruptibility:

```python
if result == PassResult.RETRYABLE_REMAINING:
    delay = retry_config.retry_delay_seconds
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"WAITING {delay} SECONDS BEFORE PASS {retry_mgr.current_pass + 1}")
    logger.info("=" * 60)
    
    # Show countdown every 10 seconds
    for elapsed in range(delay):
        if _shutdown_requested:
            logger.info("Shutdown requested, cancelling wait")
            break
        if elapsed > 0 and elapsed % 10 == 0:
            remaining = delay - elapsed
            logger.info(f"  ... {remaining}s remaining until pass {retry_mgr.current_pass + 1}")
        time.sleep(1)
    
    if not _shutdown_requested:
        logger.info(f"Starting pass {retry_mgr.current_pass + 1}")
```

### 6. Update Help Text

**File:** `parallel_orchestrator.py` - Update the help epilog (around line 1001):

```python
epilog="""
Examples:
  # Run with 3 workers, default 5 retry passes
  python parallel_orchestrator.py --workers 3 --run

  # Run with custom retry settings
  python parallel_orchestrator.py --workers 5 --run --max-passes 10 --max-attempts-per-job 3

  # Run with longer delay between retry passes
  python parallel_orchestrator.py --workers 3 --run --retry-delay 60

  # Check current status
  python parallel_orchestrator.py --status

Retry Behavior:
  - Default: 5 retry passes, 5 attempts per job
  - Infrastructure failures (ADB timeout, Appium crash) are automatically retried
  - Account failures (suspended, banned) are NOT retried
  - Use --max-passes to control total retry passes
  - Use --max-attempts-per-job to limit retries per individual job
"""
```

### 7. Log Retry Config at Startup

**File:** `parallel_orchestrator.py` - Enhance startup logging (around line 1127):

```python
logger.info("")
logger.info("=" * 60)
logger.info("RETRY CONFIGURATION")
logger.info("=" * 60)
logger.info(f"  Max passes:              {retry_cfg.max_passes}")
logger.info(f"  Max attempts per job:    {retry_cfg.max_attempts_per_job}")
logger.info(f"  Delay between passes:    {retry_cfg.retry_delay_seconds}s")
logger.info(f"  Infra retry limit:       {retry_cfg.infrastructure_retry_limit}")
logger.info(f"  Retry unknown errors:    {retry_cfg.unknown_error_is_retryable}")
logger.info("=" * 60)
logger.info("")
```

## Files to Modify

1. **retry_manager.py** - Update RetryConfig defaults, add prominent pass markers, enhance pass summary
2. **parallel_orchestrator.py** - Add --max-attempts-per-job flag, update defaults, improve delay logging
3. **config.py** - Add MAX_RETRY_PASSES constant

## Backward Compatibility

- All changes are backward compatible
- New CLI flag has sensible default (5)
- Existing scripts without new flags will work with new defaults

**Test Strategy:**

## Test Strategy

### 1. Verify Default Value Changes

```bash
# Check retry_manager.py defaults
python -c "
from retry_manager import RetryConfig
config = RetryConfig()
assert config.max_passes == 5, f'Expected max_passes=5, got {config.max_passes}'
print(f'✓ RetryConfig.max_passes = {config.max_passes}')
"

# Check CLI default
python parallel_orchestrator.py --help | grep -A1 "max-passes"
# Expected: default: 5
```

### 2. Verify New CLI Flag Exists

```bash
# Verify --max-attempts-per-job flag exists
python parallel_orchestrator.py --help | grep "max-attempts-per-job"
# Expected: --max-attempts-per-job ... (default: 5)

# Verify it parses correctly
python -c "
import sys
sys.argv = ['test', '--max-attempts-per-job', '3', '--run']
# Would need to mock the rest, but this tests the argparse
"
```

### 3. Test Pass Marker Visibility

```bash
# Run a quick test to see pass markers
python -c "
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
from retry_manager import RetryPassManager, RetryConfig
from progress_tracker import ProgressTracker
import tempfile
import os

# Create temp file
with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    test_file = f.name

try:
    tracker = ProgressTracker(test_file)
    config = RetryConfig(max_passes=5)
    manager = RetryPassManager(tracker, config)
    
    # Seed test jobs
    test_jobs = [{'job_id': 'v1', 'account': 'acc1', 'video_path': '/v1.mp4', 'caption': 'Test'}]
    tracker.seed_from_jobs(test_jobs)
    
    # Start a pass - should show prominent marker
    print('\\n=== TESTING PASS MARKERS ===\\n')
    pass_num = manager.start_new_pass()
    print(f'Pass {pass_num} started')
    
finally:
    os.unlink(test_file)
    if os.path.exists(test_file + '.lock'):
        os.unlink(test_file + '.lock')
"
```

### 4. Test Pass Summary Output

```bash
# Run a test to see pass summary
python -c "
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
from retry_manager import RetryPassManager, RetryConfig, PassResult
from progress_tracker import ProgressTracker
import tempfile
import os

with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    test_file = f.name

try:
    tracker = ProgressTracker(test_file)
    config = RetryConfig(max_passes=5)
    manager = RetryPassManager(tracker, config)
    
    # Seed test jobs
    test_jobs = [
        {'job_id': 'v1', 'account': 'acc1', 'video_path': '/v1.mp4', 'caption': 'Test 1'},
        {'job_id': 'v2', 'account': 'acc2', 'video_path': '/v2.mp4', 'caption': 'Test 2'},
    ]
    tracker.seed_from_jobs(test_jobs)
    
    # Start and end a pass
    manager.start_new_pass()
    tracker.update_job_status('v1', 'success', worker_id=0)
    tracker.update_job_status('v2', 'failed', worker_id=0, error='ADB timeout')
    
    print('\\n=== TESTING PASS SUMMARY ===\\n')
    result = manager.end_pass()
    print(f'\\nResult: {result.value}')
    
finally:
    os.unlink(test_file)
    if os.path.exists(test_file + '.lock'):
        os.unlink(test_file + '.lock')
"
```

### 5. Integration Test with Mock Run

```bash
# Test the full flow with --status to verify configuration display
python parallel_orchestrator.py --status

# Test help text includes new options
python parallel_orchestrator.py --help | grep -E "retry|pass|attempts"
```

### 6. Verify Delay Between Passes

```bash
# Test delay countdown (short delay for testing)
python -c "
import logging
import time
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger()

delay = 5  # Short delay for testing
logger.info(f'WAITING {delay} SECONDS BEFORE NEXT PASS')
for elapsed in range(delay):
    if elapsed > 0 and elapsed % 2 == 0:
        remaining = delay - elapsed
        logger.info(f'  ... {remaining}s remaining')
    time.sleep(1)
logger.info('Starting next pass')
"
```

### 7. End-to-End Test

```bash
# Only run this if you have test accounts set up
# This verifies the actual retry loop works with the new defaults
python parallel_orchestrator.py --workers 1 --run --max-passes 2 --max-attempts-per-job 2 --retry-delay 5

# Observe:
# 1. Pass 1/2 marker appears prominently
# 2. After pass completes, summary shows success/failure breakdown
# 3. 5 second delay countdown appears
# 4. Pass 2/2 marker appears
# 5. Final results show total passes
```
