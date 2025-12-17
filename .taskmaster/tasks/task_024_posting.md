# Task ID: 24

**Title:** Enforce strict worker-phone-Appium bindings with explicit phone assignment

**Status:** deferred

**Dependencies:** 19 ✓

**Priority:** high

**Description:** Add phone_id field to WorkerConfig, implement --phones CLI argument for the orchestrator to map each worker to a specific phone, update get_config() to assign phones to workers, pass --phone-id to parallel_worker.py, and validate phone assignments are unique and exist in Geelark before starting.

**Details:**

## Overview

This task addresses Section 3.1-3.2 from reviews/review1.txt, implementing strict worker-phone-Appium bindings to prevent phone-level collisions. Currently, workers can implicitly "grab phones" rather than being bound to a pre-assigned phone identity, making phone-level collisions possible when multiple workers run concurrently.

## Current State Analysis

- `parallel_config.py` (lines 26-53): `WorkerConfig` dataclass has no `phone_id` field
- `parallel_config.py` (lines 172-174): `get_config()` only accepts `num_workers` parameter, no phone assignment
- `parallel_orchestrator.py` (lines 626-657): `start_worker_process()` passes `--worker-id`, `--num-workers`, `--progress-file`, `--delay` but no `--phone-id`
- `parallel_worker.py` (lines 368-399): `main()` parser accepts `--worker-id`, `--num-workers`, `--progress-file`, `--delay` but no `--phone-id`
- `parallel_worker.py` (lines 131-216): `execute_posting_job()` uses `account` from job dict as phone_name, not a worker-bound phone_id
- Workers currently select phones dynamically based on the account name from jobs, not from a pre-assigned binding

## Implementation Details

### 3.1 Add phone_id field to WorkerConfig and orchestrator CLI

**File:** `parallel_config.py`

1. Extend `WorkerConfig` dataclass (around line 26):
```python
@dataclass
class WorkerConfig:
    """Configuration for a single worker process."""
    worker_id: int
    appium_port: int
    system_port_start: int
    system_port_end: int
    log_file: str
    appium_log_file: str
    phone_id: Optional[str] = None  # NEW: Geelark phone ID or serialName
```

2. Modify `get_config()` function (around line 172) to accept phones parameter:
```python
def get_config(num_workers: int = 3, phones: Optional[List[str]] = None) -> ParallelConfig:
    """
    Get a parallel configuration with the specified number of workers.
    
    Args:
        num_workers: Number of parallel workers
        phones: Optional list of phone IDs/names to assign to workers (must match num_workers)
    
    Returns:
        ParallelConfig with phone assignments if provided
    """
    config = ParallelConfig(num_workers=num_workers)
    if phones:
        if len(phones) != num_workers:
            raise ValueError(f"Number of phones ({len(phones)}) must match number of workers ({num_workers})")
        for worker, phone in zip(config.workers, phones):
            worker.phone_id = phone
    return config
```

**File:** `parallel_orchestrator.py`

3. Add `--phones` CLI argument (around line 959):
```python
parser.add_argument('--phones', '-p',
                    help='Comma-separated list of phone IDs/names (must match --workers count)')
```

4. Parse phones list in `main()` (around line 967):
```python
# Parse phones list if provided
phones_list = None
if args.phones:
    phones_list = [p.strip() for p in args.phones.split(',') if p.strip()]
```

5. Update `get_config()` calls throughout orchestrator to pass phones:
```python
config = get_config(num_workers=args.workers, phones=phones_list)
```

6. Add phone validation function before starting workers:
```python
def validate_phone_assignments(config: ParallelConfig) -> Tuple[bool, List[str]]:
    """
    Validate that all phone_id values are unique and exist in Geelark.
    
    Returns:
        (valid: bool, list of error messages)
    """
    errors = []
    
    # Check for phone assignments
    phone_ids = [w.phone_id for w in config.workers if w.phone_id]
    if not phone_ids:
        errors.append("No phones assigned to workers. Use --phones phone1,phone2,...")
        return False, errors
    
    if len(phone_ids) != config.num_workers:
        errors.append(f"Only {len(phone_ids)} phones assigned but {config.num_workers} workers configured")
        return False, errors
    
    # Check for duplicates
    if len(phone_ids) != len(set(phone_ids)):
        duplicates = [p for p in phone_ids if phone_ids.count(p) > 1]
        errors.append(f"Duplicate phone assignments: {set(duplicates)}")
        return False, errors
    
    # Validate phones exist in Geelark
    try:
        client = GeelarkClient()
        all_phones = {}
        for page in range(1, 20):
            result = client.list_phones(page=page, page_size=100)
            for phone in result.get('items', []):
                all_phones[phone['id']] = phone['serialName']
                all_phones[phone['serialName']] = phone['id']
            if len(result.get('items', [])) < 100:
                break
        
        for phone_id in phone_ids:
            if phone_id not in all_phones:
                errors.append(f"Phone '{phone_id}' not found in Geelark")
    except Exception as e:
        errors.append(f"Failed to validate phones with Geelark: {e}")
    
    return len(errors) == 0, errors
```

7. Call validation before `start_all_workers()` in `run_parallel_posting()`:
```python
# Validate phone assignments
logger.info("Validating phone assignments...")
valid, errors = validate_phone_assignments(config)
if not valid:
    for err in errors:
        logger.error(f"  - {err}")
    return {'error': 'invalid_phone_assignments', 'details': errors}
logger.info("Phone assignments validated successfully")
```

### 3.2 Pass --phone-id to parallel_worker.py and enforce exclusive use

**File:** `parallel_orchestrator.py`

8. Update `start_worker_process()` (around line 626) to pass phone_id:
```python
def start_worker_process(worker_id: int, config: ParallelConfig) -> subprocess.Popen:
    """Start a single worker subprocess."""
    worker_config = config.get_worker(worker_id)
    
    cmd = [
        sys.executable,
        'parallel_worker.py',
        '--worker-id', str(worker_id),
        '--num-workers', str(config.num_workers),
        '--progress-file', config.progress_file,
        '--delay', str(config.delay_between_jobs),
        '--phone-id', worker_config.phone_id,  # NEW: Pass assigned phone
    ]
    # ... rest of function
```

**File:** `parallel_worker.py`

9. Add `--phone-id` argument to parser (around line 371):
```python
parser.add_argument('--phone-id', required=True,
                    help='Geelark phone ID or serialName assigned to this worker')
```

10. Store phone_id in worker state and pass to job execution (around line 385):
```python
# Run worker with assigned phone
stats = run_worker(
    worker_id=args.worker_id,
    config=config,
    progress_file=args.progress_file,
    delay_between_jobs=args.delay,
    phone_id=args.phone_id  # NEW
)
```

11. Update `run_worker()` signature and enforce phone binding (around line 218):
```python
def run_worker(
    worker_id: int,
    config: ParallelConfig,
    progress_file: str = None,
    delay_between_jobs: int = None,
    phone_id: str = None  # NEW: Required phone assignment
) -> dict:
    """
    Main worker loop.
    
    Args:
        worker_id: This worker's ID
        config: Parallel configuration
        progress_file: Override progress file path
        delay_between_jobs: Override delay between jobs
        phone_id: Assigned Geelark phone (required - worker uses ONLY this phone)
    """
    if not phone_id:
        raise ValueError("phone_id is required - worker must have an assigned phone")
```

12. Update `execute_posting_job()` to use worker's assigned phone instead of job account (around line 131):
```python
def execute_posting_job(
    job: dict,
    worker_config: WorkerConfig,
    config: ParallelConfig,
    logger: logging.Logger,
    tracker=None,
    worker_id: int = None,
    phone_id: str = None  # NEW: Worker's assigned phone
) -> tuple:
    """
    Execute a single posting job using the worker's assigned phone.
    
    IMPORTANT: The worker uses its assigned phone_id, NOT the account from the job.
    The 'account' in the job refers to the Instagram account to post to,
    while phone_id is the Geelark cloud phone this worker exclusively controls.
    """
```

13. Pass phone_id when calling execute_posting_job in run_worker():
```python
success, error = execute_posting_job(
    job, worker_config, config, logger,
    tracker=tracker, worker_id=worker_id,
    phone_id=phone_id  # Pass worker's assigned phone
)
```

## File-level Change Summary

| File | Changes |
|------|---------|
| `parallel_config.py` | Add `phone_id: Optional[str] = None` to WorkerConfig, update `get_config()` to accept phones list |
| `parallel_orchestrator.py` | Add `--phones` CLI arg, add `validate_phone_assignments()`, update `start_worker_process()` to pass `--phone-id`, call validation before starting |
| `parallel_worker.py` | Add `--phone-id` arg (required), update `run_worker()` and `execute_posting_job()` to use assigned phone exclusively |

## Key Invariants Enforced

1. **One worker ↔ one phone**: Each worker is bound to exactly one Geelark phone at startup
2. **No dynamic phone selection**: Workers do not scan for "any available phone"
3. **Uniqueness**: No two workers can be assigned the same phone
4. **Existence validation**: All assigned phones must exist in Geelark before orchestrator starts
5. **Explicit binding**: Phone assignment is explicit via CLI, not implicit

**Test Strategy:**

## Test Strategy

### 1. Unit Tests for WorkerConfig phone_id Field

**Test phone_id field exists and is optional:**
```python
def test_worker_config_phone_id_optional():
    config = WorkerConfig(
        worker_id=0, appium_port=4723,
        system_port_start=8200, system_port_end=8209,
        log_file="test.log", appium_log_file="appium.log"
    )
    assert config.phone_id is None

def test_worker_config_phone_id_set():
    config = WorkerConfig(
        worker_id=0, appium_port=4723,
        system_port_start=8200, system_port_end=8209,
        log_file="test.log", appium_log_file="appium.log",
        phone_id="test_phone_123"
    )
    assert config.phone_id == "test_phone_123"
```

### 2. Unit Tests for get_config() with phones

**Test get_config with matching phones:**
```bash
python -c "
from parallel_config import get_config
config = get_config(num_workers=3, phones=['phone1', 'phone2', 'phone3'])
assert len(config.workers) == 3
assert config.workers[0].phone_id == 'phone1'
assert config.workers[1].phone_id == 'phone2'
assert config.workers[2].phone_id == 'phone3'
print('PASS: get_config with phones')
"
```

**Test get_config with mismatched phones count (should raise):**
```bash
python -c "
from parallel_config import get_config
try:
    config = get_config(num_workers=3, phones=['phone1', 'phone2'])
    print('FAIL: Should have raised ValueError')
except ValueError as e:
    print(f'PASS: Raised ValueError: {e}')
"
```

### 3. Integration Tests for Phone Validation

**Test validate_phone_assignments with duplicates:**
```bash
python -c "
from parallel_orchestrator import validate_phone_assignments
from parallel_config import get_config

# Create config with duplicate phones
config = get_config(num_workers=2)
config.workers[0].phone_id = 'same_phone'
config.workers[1].phone_id = 'same_phone'

valid, errors = validate_phone_assignments(config)
assert not valid, 'Should be invalid'
assert any('Duplicate' in e for e in errors)
print(f'PASS: Duplicate detection - {errors}')
"
```

**Test validate_phone_assignments with non-existent phone:**
```bash
python -c "
from parallel_orchestrator import validate_phone_assignments
from parallel_config import get_config

config = get_config(num_workers=1, phones=['nonexistent_phone_xyz123'])
valid, errors = validate_phone_assignments(config)
assert not valid, 'Should be invalid'
assert any('not found' in e for e in errors)
print(f'PASS: Non-existent phone detection - {errors}')
"
```

### 4. CLI Argument Tests

**Test --phones argument parsing:**
```bash
# Test with matching phones
python parallel_orchestrator.py --workers 2 --phones phone1,phone2 --status

# Test with mismatched count (should error)
python parallel_orchestrator.py --workers 3 --phones phone1,phone2 --run 2>&1 | grep -i "must match"
```

### 5. Worker phone_id Enforcement Tests

**Test worker refuses to start without phone_id:**
```bash
python -c "
from parallel_worker import run_worker
from parallel_config import get_config

config = get_config(num_workers=1)
try:
    run_worker(worker_id=0, config=config, phone_id=None)
    print('FAIL: Should have raised ValueError')
except ValueError as e:
    print(f'PASS: Worker requires phone_id - {e}')
"
```

### 6. End-to-End Test with Real Phones

**Prerequisites:** Have at least 2 Geelark phones available (e.g., from accounts.txt)

```bash
# Step 1: Get two available phone names
python -c "
from geelark_client import GeelarkClient
client = GeelarkClient()
result = client.list_phones(page_size=5)
phones = [p['serialName'] for p in result['items'][:2]]
print(f'Available phones: {phones}')
print(f'Use: --phones {phones[0]},{phones[1]}')
"

# Step 2: Test orchestrator with phone binding (dry run)
python parallel_orchestrator.py --workers 2 --phones <phone1>,<phone2> --status

# Step 3: Full test with 2 workers on 2 phones
python parallel_orchestrator.py --workers 2 --phones <phone1>,<phone2> --seed-only --accounts acc1,acc2

# Verify logs show phone binding
grep "phone_id" logs/worker_0.log
grep "phone_id" logs/worker_1.log
```

### 7. Collision Prevention Test

**Test that workers use only assigned phones:**
```bash
# Start orchestrator with explicit phone bindings
# Monitor that worker 0 only uses phone1, worker 1 only uses phone2
# Check logs for any attempts to use non-assigned phones
python parallel_orchestrator.py --workers 2 --phones phone1,phone2 --run &

# In another terminal, monitor:
tail -f logs/worker_0.log | grep -i phone
tail -f logs/worker_1.log | grep -i phone

# Verify no cross-phone operations
```

### 8. Regression Tests

**Ensure backwards compatibility when --phones not provided:**
```bash
# Without --phones should show error or warning, not crash
python parallel_orchestrator.py --workers 2 --status  # Should work (no phone validation for status)
python parallel_orchestrator.py --workers 2 --run  # Should error gracefully asking for --phones
```
