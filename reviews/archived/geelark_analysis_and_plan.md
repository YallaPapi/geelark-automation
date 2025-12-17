# Geelark Automation Codebase Analysis & Retry Loop Implementation Plan

## Executive Summary

This document provides a comprehensive analysis of the Geelark Instagram Automation codebase, identifying both exemplary and problematic coding practices. It then presents a detailed implementation plan for the requested **Retry Loop Logic** feature that distinguishes between non-retryable account issues and retryable infrastructure failures.

---

## Part 1: Codebase Best Practice Analysis

### 🟢 Good Practices

#### 1. **Strategy Pattern for Error Classification** (`progress_tracker.py`)

```python
# Error classification patterns (Strategy pattern)
# Maps error_type -> list of substrings to match in error message
ERROR_PATTERNS = {
    'suspended': ['suspended', 'account has been suspended'],
    'captcha': ['captcha', 'verify'],
    'loggedout': ['log in', 'logged out', 'sign up'],
    'actionblocked': ['action blocked', 'try again later'],
    'banned': ['banned', 'disabled'],
}

NON_RETRYABLE_ERRORS = {'suspended', 'captcha', 'loggedout', 'actionblocked', 'banned'}
```

**What's Good:**
- Clear separation of error types using a declarative data structure
- The pattern-matching approach is extensible—new error types can be added without changing classification logic
- Centralizes error knowledge in one location

**Underlying Principles:**
- Strategy Pattern: Encapsulates error classification behavior
- Open/Closed Principle: Open for extension (new patterns), closed for modification (classification logic)
- Single Source of Truth: All error patterns defined in one place

**Positive Consequences:**
- Easy to maintain and extend error handling
- Consistent error classification across the entire system
- Self-documenting code that clearly shows all handled error types

---

#### 2. **File-Based Locking for Multi-Process Coordination** (`progress_tracker.py`)

```python
def _locked_operation(self, operation):
    """Execute an operation with file locking."""
    os.makedirs(os.path.dirname(self.lock_file) or '.', exist_ok=True)

    with open(self.lock_file, 'w') as lock_handle:
        self._acquire_lock(lock_handle)
        try:
            jobs = self._read_all_jobs() if os.path.exists(self.progress_file) else []
            jobs, result = operation(jobs)
            if jobs is not None:
                self._write_all_jobs(jobs)
            return result
        finally:
            self._release_lock(lock_handle)
```

**What's Good:**
- Cross-platform file locking using `portalocker` with Windows fallback
- Atomic operations prevent race conditions in multi-worker scenarios
- Clean separation of locking mechanics from business logic via callback pattern

**Underlying Principles:**
- Template Method Pattern: The locking/unlocking is the template, operation is the variable
- RAII (Resource Acquisition Is Initialization): Lock acquired at entry, released in finally
- Defensive Programming: Handles both existence and creation of lock files

**Positive Consequences:**
- Prevents duplicate posts across parallel workers
- Safe for multi-process environments
- Graceful handling of edge cases (missing directories, missing files)

---

#### 3. **Single-Instance Lock Mechanism with Heartbeat** (`posting_scheduler.py`)

```python
def acquire_lock() -> bool:
    """Acquire single-instance lock with heartbeat monitoring."""
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, 'r') as f:
            lock_data = json.load(f)
        old_pid = lock_data.get('pid')
        last_heartbeat = lock_data.get('last_heartbeat')

        if old_pid and is_process_running(old_pid):
            if last_heartbeat:
                hb_time = datetime.fromisoformat(last_heartbeat)
                if datetime.now() - hb_time > timedelta(minutes=stale_threshold_minutes):
                    # Heartbeat stale - take over
                    pass
                else:
                    return False  # Another instance truly running
```

**What's Good:**
- Heartbeat-based stale detection prevents orphaned locks from blocking the system
- Cross-platform process existence checking
- Informative error messages when lock acquisition fails

**Underlying Principles:**
- Lease-based locking: Heartbeat acts as a lease renewal
- Fail-safe design: Stale locks can be reclaimed
- User-friendly errors: Clear instructions on manual resolution

**Positive Consequences:**
- System can recover from crashes without manual intervention
- Prevents accidental multiple scheduler instances
- Clear audit trail via lock file

---

#### 4. **Separation of Concerns with Dedicated Worker Processes** (`parallel_worker.py`)

```python
# Each worker is completely isolated:
# - Its own Appium server
# - Its own systemPort  
# - Its own log file
# Workers only communicate via the file-locked progress CSV.
```

**What's Good:**
- Complete process isolation prevents cascading failures
- Each worker manages its own lifecycle (Appium server start/stop)
- Inter-worker communication is stateless via shared CSV

**Underlying Principles:**
- Actor Model: Workers are independent actors
- Share Nothing Architecture: Only shared state is the progress file
- Failure Isolation: One worker crash doesn't affect others

**Positive Consequences:**
- Horizontal scalability—add more workers easily
- Resilient to individual worker failures
- Easy debugging via per-worker log files

---

#### 5. **Defensive Pre-Post Verification** (`progress_tracker.py`)

```python
def verify_job_before_post(self, job_id: str, worker_id: int) -> tuple:
    """
    Verify a job is still valid before actually posting.
    
    This is a safety check to prevent duplicate posts. Call this right before
    the actual Instagram posting to ensure:
    1. The job is still claimed by this worker (not stolen/completed)
    2. No duplicate success exists for this exact job
    """
```

**What's Good:**
- Double-checks job ownership immediately before expensive operations
- Prevents duplicates even in race condition scenarios
- Returns clear error messages for debugging

**Underlying Principles:**
- Optimistic Locking: Claim first, verify before commit
- Defense in Depth: Multiple validation layers
- Idempotency awareness: Posting is not idempotent, so extra care is warranted

**Positive Consequences:**
- Near-zero duplicate posts even under high concurrency
- Clear audit trail when verification fails
- Graceful handling of edge cases

---

#### 6. **Centralized Configuration Management** (`config.py`)

```python
from config import Config, setup_environment
setup_environment()

# All environment-specific paths in one place
ADB_PATH = Config.ADB_PATH
ANDROID_HOME = Config.ANDROID_HOME
```

**What's Good:**
- Single source of truth for all configuration
- Environment setup happens early and consistently
- Easy to switch between development/production configurations

**Underlying Principles:**
- Single Responsibility: Config class only handles configuration
- DRY (Don't Repeat Yourself): Paths defined once
- Dependency Injection: Config values injected from central location

**Positive Consequences:**
- Easy environment switching
- Consistent behavior across all modules
- Clear onboarding path for new developers

---

### 🔴 Bad Practices

#### 1. **Inconsistent Error Handling Patterns**

**Location:** Various files (`parallel_worker.py`, `post_reel_smart.py`)

```python
# In parallel_worker.py
except Exception as e:
    error_msg = f"{type(e).__name__}: {str(e)}"
    logger.error(f"Job {job_id} exception: {error_msg}")
    return False, error_msg

# In other places
except Exception as e:
    return {"action": "error", "message": f"JSON parse error: {e}"}
```

**What's Bad:**
- Generic `Exception` catching hides specific error types
- No distinction between recoverable and unrecoverable exceptions
- Error message formats vary across the codebase

**Underlying Problems:**
- Violates Liskov Substitution—different exceptions should have different handlers
- Debugging difficulty—root causes obscured
- Inconsistent user/operator experience

**Negative Consequences:**
- Retry logic may retry non-retryable errors
- Stack traces often lost
- Difficult to build comprehensive error dashboards

---

#### 2. **Magic Numbers and Hardcoded Values**

**Location:** Throughout codebase

```python
# In posting_scheduler.py
stale_threshold_minutes = 2

# In progress_tracker.py  
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_DELAY_MINUTES = 5

# In parallel_worker.py
released = tracker.release_stale_claims(max_age_seconds=600)
```

**What's Bad:**
- Values scattered across multiple files
- No central configuration for operational parameters
- Some values hardcoded while similar values are configurable

**Underlying Problems:**
- Violates DRY principle
- Difficult to tune system behavior
- Values disconnected from documentation

**Negative Consequences:**
- Operational tuning requires code changes
- Risk of inconsistent values across related features
- Testing different configurations is cumbersome

---

#### 3. **Import Statements Inside Functions**

**Location:** `posting_scheduler.py`, `parallel_worker.py`

```python
def check_appium_health(port: int = 4723) -> bool:
    """Check if Appium server is running and healthy."""
    import urllib.request
    import urllib.error
    # ...

def execute_posting_job(...):
    # Import here to avoid circular imports
    from post_reel_smart import SmartInstagramPoster
```

**What's Bad:**
- Imports inside functions add overhead on every call
- "Avoid circular imports" comment indicates architectural issue
- Makes dependencies harder to trace

**Underlying Problems:**
- Circular dependency suggests poor module boundaries
- Performance impact from repeated imports
- Hidden dependencies make testing harder

**Negative Consequences:**
- Slower execution (though Python caches imports)
- Architectural debt accumulates
- IDE tools struggle with dependency analysis

---

#### 4. **Incomplete Error Classification Coverage**

**Location:** `progress_tracker.py`

```python
ERROR_PATTERNS = {
    'suspended': ['suspended', 'account has been suspended'],
    'captcha': ['captcha', 'verify'],
    'loggedout': ['log in', 'logged out', 'sign up'],
    'actionblocked': ['action blocked', 'try again later'],
    'banned': ['banned', 'disabled'],
}
```

**What's Bad:**
- Missing critical infrastructure error patterns (ADB timeout, Appium crash)
- No category for "Claude stuck" or "Post returned False"
- Patterns are case-insensitive but not documented as such

**Underlying Problems:**
- Feature request's core need—distinguishing account vs infrastructure errors—is incomplete
- Unknown errors default to retryable, which may not be appropriate
- No mechanism for learning new error patterns

**Negative Consequences:**
- Infrastructure issues treated same as unknown account issues
- Unnecessary retries of clearly non-retryable errors
- Operators can't easily add new patterns

---

#### 5. **Lack of Structured Logging**

**Location:** Throughout codebase

```python
logger.info(f"Worker {worker_id} claimed job {job['job_id']} (account: {account})")
logger.error(f"Job {job_id} exception: {error_msg}")
```

**What's Bad:**
- String-formatted logs difficult to parse programmatically
- No structured fields for filtering/searching
- Inconsistent log message formats

**Underlying Problems:**
- Violates observability best practices
- Can't build effective dashboards
- Log aggregation tools underutilized

**Negative Consequences:**
- Manual log searching for debugging
- Can't create automated alerts based on log patterns
- Metrics extraction requires regex parsing

---

#### 6. **Missing Retry Category for Infrastructure Errors**

**Location:** Conceptual gap in current design

The current system only has:
- **Non-retryable account errors**: suspended, captcha, loggedout, actionblocked, banned
- **Everything else**: Treated as retryable up to MAX_ATTEMPTS

**What's Missing:**
- Explicit infrastructure error category
- Different retry strategies for different error types
- Maximum retry limits per error category

**Negative Consequences:**
- Infrastructure issues may exhaust account-level retry counts
- No exponential backoff for transient infrastructure issues
- Operators can't distinguish between error types in reports

---

## Part 2: Retry Loop Logic Implementation Plan

### Overview

The requested feature implements a **multi-pass retry system** that distinguishes between non-retryable account issues and retryable infrastructure failures. 

```
TRY ALL JOBS
    ↓
FILTER: account broken? → set aside forever
        infrastructure hiccup? → retry queue
    ↓
RETRY the hiccups
    ↓
REPEAT until done or max retries
```

### Detailed Implementation Plan

#### Phase 1: Error Classification Enhancement

**File:** `progress_tracker.py`

**Step 1.1: Add Infrastructure Error Patterns**

```python
# Enhanced error classification
ERROR_CATEGORIES = {
    'account': {  # Non-retryable - account issues
        'suspended': ['suspended', 'account has been suspended', 'your account is suspended'],
        'disabled': ['disabled', 'your account has been disabled'],
        'verification': ['verify your identity', 'verification required', 'security check'],
        'logged_out': ['log in', 'logged out', 'sign up', 'session expired'],
        'action_blocked': ['action blocked', 'try again later', 'temporarily blocked'],
        'banned': ['banned', 'permanently banned'],
        'not_in_geelark': ['phone not found', 'device not found', 'not in geelark'],
    },
    'infrastructure': {  # Retryable - transient issues
        'adb_timeout': ['adb timeout', 'adb connection', 'connection timed out', 'device offline'],
        'appium_crash': ['appium', 'session not created', 'uiautomator', 'instrumentation'],
        'connection_dropped': ['connection dropped', 'socket hang up', 'connection reset'],
        'claude_stuck': ['post returned false', 'max steps reached', 'navigation failed'],
        'glogin_expired': ['glogin', 'login first'],
        'network_error': ['network', 'timeout', 'connection refused'],
    }
}

NON_RETRYABLE_CATEGORIES = {'account'}
```

**Step 1.2: Update Error Classification Method**

```python
def _classify_error(self, error: str) -> tuple[str, str]:
    """
    Classify an error message into category and type.
    
    Returns:
        (category, error_type) - e.g., ('account', 'suspended') or ('infrastructure', 'adb_timeout')
        ('unknown', '') for unclassified errors
    """
    error_lower = error.lower() if error else ''
    
    for category, types in self.ERROR_CATEGORIES.items():
        for error_type, patterns in types.items():
            if any(pattern in error_lower for pattern in patterns):
                return category, error_type
    
    return 'unknown', ''
```

**Step 1.3: Add New CSV Columns**

```python
COLUMNS = [
    'job_id', 'account', 'video_path', 'caption', 'status',
    'worker_id', 'claimed_at', 'completed_at', 'error',
    'attempts', 'max_attempts', 'retry_at', 
    'error_type', 'error_category',  # NEW: category for retry decisions
    'pass_number',  # NEW: which retry pass this job is on
]
```

---

#### Phase 2: Retry Pass Manager

**File:** New file `retry_manager.py`

```python
"""
Retry Pass Manager - Orchestrates multi-pass retry logic.

Pass Flow:
1. First pass: Run all pending jobs
2. After pass: Categorize failures
   - Account issues → Mark as permanently failed
   - Infrastructure issues → Queue for retry
3. Second pass: Run only retryable failures
4. Repeat until: All succeed, only non-retryable remain, or max passes reached
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from datetime import datetime
from enum import Enum
import logging

from progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)


class PassResult(Enum):
    ALL_COMPLETE = "all_complete"
    ONLY_NON_RETRYABLE = "only_non_retryable"
    MAX_PASSES_REACHED = "max_passes_reached"
    RETRYABLE_REMAINING = "retryable_remaining"


@dataclass
class PassStats:
    """Statistics for a single pass."""
    pass_number: int
    total_jobs: int
    succeeded: int
    failed_account: int  # Non-retryable
    failed_infrastructure: int  # Retryable
    failed_unknown: int
    start_time: datetime
    end_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        if self.total_jobs == 0:
            return 0.0
        return self.succeeded / self.total_jobs * 100


@dataclass  
class RetryConfig:
    """Configuration for retry behavior."""
    max_passes: int = 3
    retry_delay_seconds: int = 30  # Delay between passes
    infrastructure_retry_limit: int = 3  # Max retries per job for infra errors
    unknown_error_is_retryable: bool = True  # Treat unknown errors as retryable


class RetryPassManager:
    """
    Manages multi-pass retry logic for job processing.
    
    Key responsibilities:
    1. Track which pass we're on
    2. Categorize failures after each pass
    3. Determine which jobs should be retried
    4. Decide when to stop retrying
    """
    
    def __init__(
        self,
        tracker: ProgressTracker,
        config: RetryConfig = None
    ):
        self.tracker = tracker
        self.config = config or RetryConfig()
        self.current_pass = 0
        self.pass_history: List[PassStats] = []
        
    def start_new_pass(self) -> int:
        """
        Start a new retry pass.
        
        Returns:
            Pass number (1-indexed)
        """
        self.current_pass += 1
        logger.info(f"{'='*60}")
        logger.info(f"STARTING PASS {self.current_pass}")
        logger.info(f"{'='*60}")
        
        # Get jobs for this pass
        if self.current_pass == 1:
            jobs = self._get_pending_jobs()
        else:
            jobs = self._get_retryable_failed_jobs()
            
        stats = PassStats(
            pass_number=self.current_pass,
            total_jobs=len(jobs),
            succeeded=0,
            failed_account=0,
            failed_infrastructure=0,
            failed_unknown=0,
            start_time=datetime.now()
        )
        self.pass_history.append(stats)
        
        logger.info(f"Pass {self.current_pass}: {len(jobs)} jobs to process")
        return self.current_pass
        
    def end_pass(self) -> PassResult:
        """
        End current pass, categorize failures, and determine next action.
        
        Returns:
            PassResult indicating what should happen next
        """
        if not self.pass_history:
            return PassResult.ALL_COMPLETE
            
        stats = self.pass_history[-1]
        stats.end_time = datetime.now()
        
        # Gather stats from tracker
        all_jobs = self.tracker._read_all_jobs()
        
        stats.succeeded = sum(1 for j in all_jobs if j.get('status') == 'success')
        
        for job in all_jobs:
            if job.get('status') == 'failed':
                category = job.get('error_category', 'unknown')
                if category == 'account':
                    stats.failed_account += 1
                elif category == 'infrastructure':
                    stats.failed_infrastructure += 1
                else:
                    stats.failed_unknown += 1
        
        # Log pass summary
        logger.info(f"{'='*60}")
        logger.info(f"PASS {self.current_pass} COMPLETE")
        logger.info(f"  Succeeded: {stats.succeeded}")
        logger.info(f"  Failed (account issues): {stats.failed_account}")
        logger.info(f"  Failed (infrastructure): {stats.failed_infrastructure}")
        logger.info(f"  Failed (unknown): {stats.failed_unknown}")
        logger.info(f"  Duration: {stats.end_time - stats.start_time}")
        logger.info(f"{'='*60}")
        
        # Determine what to do next
        retryable_count = stats.failed_infrastructure
        if self.config.unknown_error_is_retryable:
            retryable_count += stats.failed_unknown
            
        if retryable_count == 0:
            if stats.failed_account > 0:
                return PassResult.ONLY_NON_RETRYABLE
            else:
                return PassResult.ALL_COMPLETE
                
        if self.current_pass >= self.config.max_passes:
            return PassResult.MAX_PASSES_REACHED
            
        # Reset retryable jobs for next pass
        self._reset_retryable_jobs_for_retry()
        
        return PassResult.RETRYABLE_REMAINING
    
    def _get_pending_jobs(self) -> List[Dict]:
        """Get all pending jobs for first pass."""
        all_jobs = self.tracker._read_all_jobs()
        return [j for j in all_jobs if j.get('status') == 'pending']
    
    def _get_retryable_failed_jobs(self) -> List[Dict]:
        """Get jobs that failed with retryable errors."""
        all_jobs = self.tracker._read_all_jobs()
        retryable = []
        
        for job in all_jobs:
            if job.get('status') != 'failed':
                continue
                
            category = job.get('error_category', 'unknown')
            attempts = int(job.get('attempts', 0))
            
            # Check if this error category is retryable
            if category == 'account':
                continue  # Never retry account issues
                
            if category == 'infrastructure':
                if attempts < self.config.infrastructure_retry_limit:
                    retryable.append(job)
            elif self.config.unknown_error_is_retryable:
                # Unknown errors get limited retries
                if attempts < 2:
                    retryable.append(job)
                    
        return retryable
    
    def _reset_retryable_jobs_for_retry(self):
        """Reset retryable failed jobs to pending for next pass."""
        def _reset_operation(jobs):
            reset_count = 0
            for job in jobs:
                if job.get('status') != 'failed':
                    continue
                    
                category = job.get('error_category', 'unknown')
                attempts = int(job.get('attempts', 0))
                
                should_retry = False
                if category == 'infrastructure':
                    should_retry = attempts < self.config.infrastructure_retry_limit
                elif category == 'unknown' and self.config.unknown_error_is_retryable:
                    should_retry = attempts < 2
                    
                if should_retry:
                    job['status'] = 'pending'
                    job['pass_number'] = str(self.current_pass + 1)
                    job['worker_id'] = ''
                    job['claimed_at'] = ''
                    reset_count += 1
                    
            logger.info(f"Reset {reset_count} jobs for retry pass {self.current_pass + 1}")
            return jobs, reset_count
            
        return self.tracker._locked_operation(_reset_operation)
    
    def get_summary(self) -> Dict:
        """Get summary of all passes."""
        return {
            'total_passes': len(self.pass_history),
            'passes': [
                {
                    'pass_number': s.pass_number,
                    'total_jobs': s.total_jobs,
                    'succeeded': s.succeeded,
                    'failed_account': s.failed_account,
                    'failed_infrastructure': s.failed_infrastructure,
                    'failed_unknown': s.failed_unknown,
                    'success_rate': f"{s.success_rate:.1f}%",
                    'duration': str(s.end_time - s.start_time) if s.end_time else 'in_progress'
                }
                for s in self.pass_history
            ]
        }
```

---

#### Phase 3: Orchestrator Integration

**File:** `parallel_orchestrator.py` (modifications)

```python
from retry_manager import RetryPassManager, RetryConfig, PassResult

def run_parallel_posting_with_retry(
    num_workers: int = 5,
    state_file: str = "scheduler_state.json",
    accounts: List[str] = None,
    retry_config: RetryConfig = None
) -> Dict:
    """
    Main entry point with multi-pass retry logic.
    
    This implements the requested flow:
    1. First pass: Run all pending jobs across workers
    2. After pass: Categorize failures
    3. Retry passes: Only retry infrastructure failures
    4. Repeat until done or max passes
    """
    config = get_config(num_workers=num_workers)
    tracker = ProgressTracker(config.progress_file)
    retry_manager = RetryPassManager(tracker, retry_config or RetryConfig())
    
    # Setup (same as before)
    setup_signal_handlers()
    full_cleanup(config)
    
    # Seed jobs if needed
    if not tracker.exists():
        seed_progress_file(config, state_file, accounts)
    
    final_result = PassResult.RETRYABLE_REMAINING
    
    while final_result == PassResult.RETRYABLE_REMAINING:
        # Start new pass
        pass_num = retry_manager.start_new_pass()
        
        # Start workers for this pass
        processes = start_all_workers(config)
        
        # Monitor until this pass completes
        monitor_workers(processes, config)
        
        # End pass and determine next action
        final_result = retry_manager.end_pass()
        
        # Brief delay between passes
        if final_result == PassResult.RETRYABLE_REMAINING:
            logger.info(f"Waiting {retry_config.retry_delay_seconds}s before next pass...")
            time.sleep(retry_config.retry_delay_seconds)
    
    # Final cleanup
    full_cleanup(config)
    
    # Return comprehensive results
    summary = retry_manager.get_summary()
    final_stats = tracker.get_stats()
    
    logger.info("="*60)
    logger.info("MULTI-PASS RETRY COMPLETE")
    logger.info(f"  Result: {final_result.value}")
    logger.info(f"  Total passes: {summary['total_passes']}")
    logger.info(f"  Final - Success: {final_stats['success']}")
    logger.info(f"  Final - Failed: {final_stats['failed']}")
    logger.info("="*60)
    
    return {
        'result': final_result.value,
        'summary': summary,
        'final_stats': final_stats
    }
```

---

#### Phase 4: Worker-Level Error Categorization

**File:** `parallel_worker.py` (modifications)

```python
def execute_posting_job(job, worker_config, config, logger, tracker=None, worker_id=None):
    """Execute a single posting job with enhanced error categorization."""
    
    # ... existing setup code ...
    
    try:
        # ... existing posting logic ...
        
        if success:
            return True, "", None, None  # success, error, category, type
        else:
            error = poster.last_error_message or "Post returned False"
            category, error_type = tracker._classify_error(error) if tracker else ('unknown', '')
            return False, error, category, error_type
            
    except TimeoutError as e:
        return False, f"TimeoutError: {e}", "infrastructure", "adb_timeout"
        
    except ConnectionError as e:
        return False, f"ConnectionError: {e}", "infrastructure", "connection_dropped"
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        # Let tracker classify the error
        category, error_type = tracker._classify_error(error_msg) if tracker else ('unknown', '')
        return False, error_msg, category, error_type


# In run_worker main loop:
success, error, category, error_type = execute_posting_job(...)

if success:
    tracker.update_job_status(job_id, 'success', worker_id)
else:
    tracker.update_job_status(
        job_id, 'failed', worker_id, 
        error=error,
        error_category=category,
        error_type=error_type
    )
```

---

#### Phase 5: Progress Tracker Updates

**File:** `progress_tracker.py` (modifications to `update_job_status`)

```python
def update_job_status(
    self,
    job_id: str,
    status: str,
    worker_id: int,
    error: str = '',
    error_category: str = '',  # NEW
    error_type: str = '',      # NEW
    retry_delay_minutes: float = None
) -> bool:
    """
    Update job status with enhanced error categorization.
    
    NEW BEHAVIOR:
    - Account errors: Mark as failed immediately, never retry
    - Infrastructure errors: Allow retries up to infrastructure_retry_limit
    - Unknown errors: Allow limited retries
    """
    
    def _update_operation(jobs):
        for job in jobs:
            if job.get('job_id') == job_id:
                job['worker_id'] = str(worker_id)
                job['completed_at'] = datetime.now().isoformat()
                job['error'] = error[:500] if error else ''
                
                if status == self.STATUS_SUCCESS:
                    job['status'] = self.STATUS_SUCCESS
                    
                elif status == self.STATUS_FAILED:
                    attempts = int(job.get('attempts', 0)) + 1
                    job['attempts'] = str(attempts)
                    
                    # Classify error if not already done
                    if not error_category:
                        cat, etype = self._classify_error(error)
                    else:
                        cat, etype = error_category, error_type
                        
                    job['error_category'] = cat
                    job['error_type'] = etype
                    
                    # Determine if this is final failure or retryable
                    if cat == 'account':
                        # Account issues - never retry
                        job['status'] = self.STATUS_FAILED
                        logger.warning(
                            f"Job {job_id} FAILED - account issue ({etype}), not retrying"
                        )
                    else:
                        # Let retry manager handle retry decisions
                        job['status'] = self.STATUS_FAILED
                        logger.info(
                            f"Job {job_id} failed ({cat}/{etype}), "
                            f"attempt {attempts}, may be retried"
                        )
                        
                return jobs, True
        return jobs, False
        
    return self._locked_operation(_update_operation)
```

---

### Phase 6: CLI Integration

**File:** `parallel_orchestrator.py` (CLI additions)

```python
def main():
    parser = argparse.ArgumentParser(...)
    
    # Existing arguments...
    
    # NEW: Retry configuration
    parser.add_argument('--max-passes', type=int, default=3,
                        help='Maximum retry passes (default: 3)')
    parser.add_argument('--retry-delay', type=int, default=30,
                        help='Seconds between retry passes (default: 30)')
    parser.add_argument('--infra-retry-limit', type=int, default=3,
                        help='Max retries for infrastructure errors per job (default: 3)')
    parser.add_argument('--no-retry-unknown', action='store_true',
                        help='Do not retry unknown errors (default: retry them)')
    
    args = parser.parse_args()
    
    retry_config = RetryConfig(
        max_passes=args.max_passes,
        retry_delay_seconds=args.retry_delay,
        infrastructure_retry_limit=args.infra_retry_limit,
        unknown_error_is_retryable=not args.no_retry_unknown
    )
    
    if args.run:
        results = run_parallel_posting_with_retry(
            num_workers=args.workers,
            accounts=accounts_list,
            retry_config=retry_config
        )
```

---

### Testing Plan

#### Unit Tests

1. **Error Classification Tests**
   - Test all account error patterns are classified correctly
   - Test all infrastructure error patterns are classified correctly
   - Test unknown errors return ('unknown', '')
   - Test case insensitivity

2. **Retry Manager Tests**
   - Test first pass gets all pending jobs
   - Test subsequent passes only get retryable failures
   - Test pass statistics are accurate
   - Test max passes limit is respected
   - Test account errors never reset for retry

3. **Integration Tests**
   - Simulate mixed failure scenarios
   - Verify account failures stay failed across passes
   - Verify infrastructure failures get retried
   - Verify final statistics are correct

#### Manual Testing Scenarios

1. **Scenario A: All Success**
   - Run 5 jobs, all succeed
   - Expect: 1 pass, all success

2. **Scenario B: Account Failures Only**
   - Run 5 jobs, 2 fail with "account suspended"
   - Expect: 1 pass, 3 success, 2 failed (not retried)

3. **Scenario C: Infrastructure Failures**
   - Run 5 jobs, 2 fail with "ADB timeout"
   - Expect: Multiple passes, infrastructure failures retried

4. **Scenario D: Mixed Failures**
   - Run 10 jobs, 3 account failures, 3 infrastructure failures
   - Expect: Account failures stay failed, infrastructure retried

---

### Migration Notes

1. **Backward Compatibility**
   - Existing progress.csv files will work (new columns default to empty)
   - Old error classification still functions but with less granularity

2. **Configuration**
   - All new parameters have sensible defaults
   - No breaking changes to CLI

3. **Rollback**
   - If issues occur, can disable retry logic via `--max-passes 1`

---

### Summary

This implementation plan provides:

1. **Enhanced error classification** distinguishing account issues from infrastructure problems
2. **Multi-pass retry manager** that orchestrates the retry flow
3. **Clear separation of concerns** between classification, retry decisions, and execution
4. **Comprehensive logging** for debugging and monitoring
5. **Configurable behavior** via CLI flags
6. **Backward compatibility** with existing systems

The key insight is separating "what went wrong" (classification) from "what to do about it" (retry policy), allowing flexible and maintainable error handling.
