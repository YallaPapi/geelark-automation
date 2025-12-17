# Task ID: 54

**Title:** Create RetryPassManager class in retry_manager.py

**Status:** done

**Dependencies:** 2 ✓, 9 ✓, 25 ✓, 51 ✓

**Priority:** high

**Description:** Implement a new retry_manager.py module containing RetryConfig dataclass, PassResult enum, PassStats dataclass, and RetryPassManager class to orchestrate multi-pass retry logic for infrastructure failures in the parallel posting system.

**Details:**

## Implementation Overview

Create a new file `retry_manager.py` in the project root that provides pass-level retry orchestration for the parallel posting system. This module will coordinate with the existing `progress_tracker.py` to enable automatic multi-pass retrying of infrastructure failures.

## File: retry_manager.py

### 1. Imports and Module Docstring

```python
"""
Retry Pass Manager - Multi-Pass Retry Orchestration.

This module provides pass-level retry management for the parallel posting system.
It tracks retry passes, aggregates statistics, and decides whether to continue
retrying based on error categories.

Key Concepts:
- Pass: A complete run through all pending/retryable jobs
- RetryConfig: Configuration for retry behavior
- PassResult: Outcome of a pass (continue, stop, complete)
- PassStats: Statistics for a single pass

Usage:
    from retry_manager import RetryPassManager, RetryConfig, PassResult
    
    config = RetryConfig(max_passes=3, retry_delay_seconds=30)
    manager = RetryPassManager(config, progress_tracker)
    
    while True:
        manager.start_new_pass()
        # ... run workers ...
        result = manager.end_pass()
        if result != PassResult.RETRYABLE_REMAINING:
            break
"""

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime
from typing import Optional, Dict, List, Any

from progress_tracker import ProgressTracker

logger = logging.getLogger(__name__)
```

### 2. RetryConfig Dataclass

```python
@dataclass
class RetryConfig:
    """
    Configuration for retry pass behavior.
    
    Attributes:
        max_passes: Maximum number of retry passes (default: 3)
        retry_delay_seconds: Delay between passes in seconds (default: 30)
        infrastructure_retry_limit: Max retries for infrastructure errors per job (default: 3)
    """
    max_passes: int = 3
    retry_delay_seconds: int = 30
    infrastructure_retry_limit: int = 3
    
    def __post_init__(self):
        """Validate configuration values."""
        if self.max_passes < 1:
            raise ValueError(f"max_passes must be >= 1, got {self.max_passes}")
        if self.retry_delay_seconds < 0:
            raise ValueError(f"retry_delay_seconds must be >= 0, got {self.retry_delay_seconds}")
        if self.infrastructure_retry_limit < 1:
            raise ValueError(f"infrastructure_retry_limit must be >= 1, got {self.infrastructure_retry_limit}")
```

### 3. PassResult Enum

```python
class PassResult(Enum):
    """
    Outcome of a retry pass - determines whether to continue.
    
    Values:
        ALL_COMPLETE: All jobs finished successfully, no retries needed
        ONLY_NON_RETRYABLE: Only non-retryable failures remain (suspended, captcha, etc.)
        MAX_PASSES_REACHED: Hit max_passes limit, stopping regardless of remaining jobs
        RETRYABLE_REMAINING: Retryable failures remain, should start another pass
    """
    ALL_COMPLETE = auto()
    ONLY_NON_RETRYABLE = auto()
    MAX_PASSES_REACHED = auto()
    RETRYABLE_REMAINING = auto()
```

### 4. PassStats Dataclass

```python
@dataclass
class PassStats:
    """
    Statistics for a single retry pass.
    
    Attributes:
        pass_number: Which pass this is (1-indexed)
        started_at: When this pass started
        ended_at: When this pass ended (None if still running)
        jobs_attempted: Total jobs attempted this pass
        jobs_succeeded: Jobs that succeeded this pass
        jobs_failed_retryable: Jobs that failed with retryable errors
        jobs_failed_non_retryable: Jobs that failed with non-retryable errors
        jobs_pending_start: Jobs pending when pass started
        jobs_pending_end: Jobs pending when pass ended
    """
    pass_number: int
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None
    jobs_attempted: int = 0
    jobs_succeeded: int = 0
    jobs_failed_retryable: int = 0
    jobs_failed_non_retryable: int = 0
    jobs_pending_start: int = 0
    jobs_pending_end: int = 0
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Duration of this pass in seconds, or None if still running."""
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()
    
    @property
    def success_rate(self) -> float:
        """Success rate as a percentage (0-100)."""
        if self.jobs_attempted == 0:
            return 0.0
        return (self.jobs_succeeded / self.jobs_attempted) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            'pass_number': self.pass_number,
            'started_at': self.started_at.isoformat(),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'duration_seconds': self.duration_seconds,
            'jobs_attempted': self.jobs_attempted,
            'jobs_succeeded': self.jobs_succeeded,
            'jobs_failed_retryable': self.jobs_failed_retryable,
            'jobs_failed_non_retryable': self.jobs_failed_non_retryable,
            'success_rate': f"{self.success_rate:.1f}%"
        }
```

### 5. RetryPassManager Class

```python
class RetryPassManager:
    """
    Manages multi-pass retry orchestration for the parallel posting system.
    
    This class tracks the current pass, aggregates statistics across passes,
    and decides whether to continue retrying based on error categories.
    
    Integrates with ProgressTracker to:
    - Query pending/failed/retrying jobs
    - Reset retryable failed jobs for the next pass
    - Classify errors as retryable vs non-retryable
    
    Usage:
        manager = RetryPassManager(config, tracker)
        
        while True:
            manager.start_new_pass()
            # ... workers process jobs ...
            result = manager.end_pass()
            
            if result == PassResult.ALL_COMPLETE:
                print("All jobs succeeded!")
                break
            elif result == PassResult.ONLY_NON_RETRYABLE:
                print("Only non-retryable failures remain")
                break
            elif result == PassResult.MAX_PASSES_REACHED:
                print("Max passes reached, giving up")
                break
            # PassResult.RETRYABLE_REMAINING - continue to next pass
    """
    
    def __init__(self, config: RetryConfig, tracker: ProgressTracker):
        """
        Initialize the retry pass manager.
        
        Args:
            config: RetryConfig with retry behavior settings
            tracker: ProgressTracker instance for job status queries
        """
        self.config = config
        self.tracker = tracker
        self.current_pass: int = 0
        self.pass_history: List[PassStats] = []
        self._current_stats: Optional[PassStats] = None
        self._snapshot_before_pass: Optional[Dict[str, int]] = None
    
    def start_new_pass(self) -> PassStats:
        """
        Start a new retry pass.
        
        This method:
        1. Increments the pass counter
        2. Takes a snapshot of current job stats
        3. Resets retryable failed jobs to 'retrying' status
        4. Creates PassStats for this pass
        
        Returns:
            PassStats for the newly started pass
        """
        self.current_pass += 1
        
        # Snapshot current state
        stats = self.tracker.get_stats()
        self._snapshot_before_pass = dict(stats)
        
        logger.info("="*60)
        logger.info(f"RETRY PASS {self.current_pass} STARTING")
        logger.info(f"  Pending: {stats['pending']}, Retrying: {stats.get('retrying', 0)}")
        logger.info(f"  Success: {stats['success']}, Failed: {stats['failed']}")
        logger.info("="*60)
        
        # Reset retryable failed jobs for this pass
        pending_jobs = self._get_pending_jobs()
        retryable_jobs = self._get_retryable_failed_jobs()
        
        if retryable_jobs:
            reset_count = self._reset_retryable_jobs()
            logger.info(f"Reset {reset_count} retryable failed jobs for pass {self.current_pass}")
        
        # Create stats tracker for this pass
        self._current_stats = PassStats(
            pass_number=self.current_pass,
            jobs_pending_start=stats['pending'] + stats.get('retrying', 0)
        )
        
        return self._current_stats
    
    def end_pass(self) -> PassResult:
        """
        End the current retry pass and determine the result.
        
        This method:
        1. Computes final statistics for the pass
        2. Determines whether to continue retrying
        3. Logs pass summary
        
        Returns:
            PassResult indicating whether to continue
        """
        if self._current_stats is None:
            raise RuntimeError("end_pass() called without start_new_pass()")
        
        # Capture end state
        self._current_stats.ended_at = datetime.now()
        stats = self.tracker.get_stats()
        
        # Compute pass stats by comparing before/after
        before = self._snapshot_before_pass or {}
        
        # Jobs attempted = jobs that moved from pending/retrying to something else
        jobs_before = before.get('pending', 0) + before.get('retrying', 0)
        jobs_after = stats['pending'] + stats.get('retrying', 0)
        
        self._current_stats.jobs_pending_end = jobs_after
        self._current_stats.jobs_attempted = jobs_before - jobs_after + stats['success'] - before.get('success', 0)
        self._current_stats.jobs_succeeded = stats['success'] - before.get('success', 0)
        
        # Count retryable vs non-retryable failures
        failed_jobs = self._get_all_failed_jobs()
        retryable_count = 0
        non_retryable_count = 0
        
        for job in failed_jobs:
            error_type = job.get('error_type', '')
            if error_type in self.tracker.NON_RETRYABLE_ERRORS:
                non_retryable_count += 1
            else:
                retryable_count += 1
        
        self._current_stats.jobs_failed_retryable = retryable_count
        self._current_stats.jobs_failed_non_retryable = non_retryable_count
        
        # Store in history
        self.pass_history.append(self._current_stats)
        
        # Log summary
        logger.info("="*60)
        logger.info(f"RETRY PASS {self.current_pass} COMPLETE")
        logger.info(f"  Duration: {self._current_stats.duration_seconds:.1f}s")
        logger.info(f"  Attempted: {self._current_stats.jobs_attempted}")
        logger.info(f"  Succeeded: {self._current_stats.jobs_succeeded} ({self._current_stats.success_rate:.1f}%)")
        logger.info(f"  Failed (retryable): {self._current_stats.jobs_failed_retryable}")
        logger.info(f"  Failed (non-retryable): {self._current_stats.jobs_failed_non_retryable}")
        logger.info("="*60)
        
        # Determine result
        result = self._determine_pass_result(stats)
        
        logger.info(f"Pass result: {result.name}")
        
        # Reset for next pass
        self._current_stats = None
        self._snapshot_before_pass = None
        
        return result
    
    def _determine_pass_result(self, stats: Dict[str, int]) -> PassResult:
        """
        Determine the result of the current pass.
        
        Args:
            stats: Current job statistics from tracker
            
        Returns:
            PassResult enum value
        """
        # Check if all jobs are complete (success or non-retryable failure)
        pending = stats['pending'] + stats.get('retrying', 0)
        failed = stats['failed']
        
        if pending == 0 and failed == 0:
            return PassResult.ALL_COMPLETE
        
        # Check max passes
        if self.current_pass >= self.config.max_passes:
            return PassResult.MAX_PASSES_REACHED
        
        # Check if only non-retryable failures remain
        retryable_jobs = self._get_retryable_failed_jobs()
        if pending == 0 and len(retryable_jobs) == 0:
            return PassResult.ONLY_NON_RETRYABLE
        
        # Retryable jobs remain
        return PassResult.RETRYABLE_REMAINING
    
    def _get_pending_jobs(self) -> List[Dict[str, Any]]:
        """Get all pending jobs from the tracker."""
        jobs = self.tracker._read_all_jobs()
        return [j for j in jobs if j.get('status') in ('pending', 'retrying')]
    
    def _get_retryable_failed_jobs(self) -> List[Dict[str, Any]]:
        """Get all failed jobs that are eligible for retry."""
        jobs = self.tracker._read_all_jobs()
        retryable = []
        for job in jobs:
            if job.get('status') == 'failed':
                error_type = job.get('error_type', '')
                if error_type not in self.tracker.NON_RETRYABLE_ERRORS:
                    retryable.append(job)
        return retryable
    
    def _get_all_failed_jobs(self) -> List[Dict[str, Any]]:
        """Get all failed jobs regardless of retry eligibility."""
        jobs = self.tracker._read_all_jobs()
        return [j for j in jobs if j.get('status') == 'failed']
    
    def _reset_retryable_jobs(self) -> int:
        """
        Reset all retryable failed jobs back to 'retrying' status.
        
        Returns:
            Number of jobs reset
        """
        return self.tracker.retry_all_failed(include_non_retryable=False)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all passes.
        
        Returns:
            Dict with overall summary and per-pass details
        """
        total_attempted = sum(p.jobs_attempted for p in self.pass_history)
        total_succeeded = sum(p.jobs_succeeded for p in self.pass_history)
        total_failed_retryable = sum(p.jobs_failed_retryable for p in self.pass_history)
        total_failed_non_retryable = sum(p.jobs_failed_non_retryable for p in self.pass_history)
        
        overall_success_rate = (total_succeeded / total_attempted * 100) if total_attempted > 0 else 0
        
        return {
            'total_passes': len(self.pass_history),
            'total_jobs_attempted': total_attempted,
            'total_jobs_succeeded': total_succeeded,
            'total_failed_retryable': total_failed_retryable,
            'total_failed_non_retryable': total_failed_non_retryable,
            'overall_success_rate': f"{overall_success_rate:.1f}%",
            'passes': [p.to_dict() for p in self.pass_history]
        }
```

### 6. Module-level test/demo code

```python
if __name__ == "__main__":
    # Demo usage
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    print("RetryPassManager Demo")
    print("="*60)
    
    # Create config with defaults
    config = RetryConfig()
    print(f"Config: max_passes={config.max_passes}, delay={config.retry_delay_seconds}s")
    
    # Test PassResult enum
    print(f"\nPassResult values:")
    for result in PassResult:
        print(f"  {result.name} = {result.value}")
    
    # Test PassStats
    stats = PassStats(pass_number=1)
    stats.jobs_attempted = 10
    stats.jobs_succeeded = 8
    print(f"\nPassStats: {stats.to_dict()}")
    
    print("\nTo use with ProgressTracker:")
    print("  tracker = ProgressTracker('progress.csv')")
    print("  manager = RetryPassManager(config, tracker)")
    print("  manager.start_new_pass()")
    print("  # ... run workers ...")
    print("  result = manager.end_pass()")
```

## Integration Notes

This module is designed to integrate with:
- **progress_tracker.py**: Uses `ProgressTracker.get_stats()`, `retry_all_failed()`, and `_read_all_jobs()` methods
- **parallel_orchestrator.py**: Task 52 will wrap the worker loop with `RetryPassManager` for multi-pass retry support
- **config.py**: Retry settings like `MAX_RETRY_ATTEMPTS` and `NON_RETRYABLE_ERRORS` are already defined

## Dependencies on Existing Code

References these existing patterns:
- `ProgressTracker.NON_RETRYABLE_ERRORS` (progress_tracker.py:93) - set of non-retryable error types
- `ProgressTracker.get_stats()` (progress_tracker.py:896) - returns job status counts
- `ProgressTracker.retry_all_failed()` (progress_tracker.py:791) - resets failed jobs for retry
- `Config.MAX_RETRY_ATTEMPTS` (config.py:82) - default retry limit
- `Config.RETRY_DELAY_MINUTES` (config.py:85) - default retry delay

**Test Strategy:**

## Test Strategy

### 1. Unit Test - Module imports successfully
```bash
python -c "from retry_manager import RetryPassManager, RetryConfig, PassResult, PassStats; print('Import OK')"
```

### 2. Unit Test - RetryConfig validation
```bash
python -c "
from retry_manager import RetryConfig

# Test defaults
config = RetryConfig()
assert config.max_passes == 3
assert config.retry_delay_seconds == 30
assert config.infrastructure_retry_limit == 3
print('Default config OK')

# Test custom values
config = RetryConfig(max_passes=5, retry_delay_seconds=60, infrastructure_retry_limit=2)
assert config.max_passes == 5
print('Custom config OK')

# Test validation - should raise ValueError
try:
    bad_config = RetryConfig(max_passes=0)
    print('ERROR: Should have raised ValueError for max_passes=0')
except ValueError:
    print('Validation: max_passes < 1 rejected OK')

try:
    bad_config = RetryConfig(retry_delay_seconds=-1)
    print('ERROR: Should have raised ValueError for negative delay')
except ValueError:
    print('Validation: negative delay rejected OK')
"
```

### 3. Unit Test - PassResult enum values
```bash
python -c "
from retry_manager import PassResult

# Verify all enum values exist
assert PassResult.ALL_COMPLETE
assert PassResult.ONLY_NON_RETRYABLE
assert PassResult.MAX_PASSES_REACHED
assert PassResult.RETRYABLE_REMAINING
print('PassResult enum OK')

# Test enum comparison
result = PassResult.RETRYABLE_REMAINING
assert result == PassResult.RETRYABLE_REMAINING
assert result != PassResult.ALL_COMPLETE
print('Enum comparison OK')
"
```

### 4. Unit Test - PassStats properties
```bash
python -c "
from retry_manager import PassStats
from datetime import datetime, timedelta

# Test basic stats
stats = PassStats(pass_number=1)
stats.jobs_attempted = 10
stats.jobs_succeeded = 7
stats.jobs_failed_retryable = 2
stats.jobs_failed_non_retryable = 1

# Test success_rate property
assert stats.success_rate == 70.0, f'Expected 70%, got {stats.success_rate}'
print(f'Success rate: {stats.success_rate}% OK')

# Test duration_seconds property (None when not ended)
assert stats.duration_seconds is None
print('Duration None before end OK')

# Set ended_at and test duration
stats.ended_at = stats.started_at + timedelta(seconds=120)
assert stats.duration_seconds == 120.0
print(f'Duration: {stats.duration_seconds}s OK')

# Test to_dict()
d = stats.to_dict()
assert d['pass_number'] == 1
assert d['jobs_attempted'] == 10
assert '70.0%' in d['success_rate']
print('to_dict() OK')
"
```

### 5. Integration Test - RetryPassManager with ProgressTracker
```bash
python -c "
import os
import tempfile
from retry_manager import RetryPassManager, RetryConfig, PassResult
from progress_tracker import ProgressTracker

# Create temp progress file
with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    temp_file = f.name

try:
    # Initialize tracker and seed with test jobs
    tracker = ProgressTracker(temp_file)
    test_jobs = [
        {'job_id': 'test1', 'account': 'acc1', 'video_path': '/v1.mp4', 'caption': 'Test 1'},
        {'job_id': 'test2', 'account': 'acc2', 'video_path': '/v2.mp4', 'caption': 'Test 2'},
        {'job_id': 'test3', 'account': 'acc3', 'video_path': '/v3.mp4', 'caption': 'Test 3'},
    ]
    tracker.seed_from_jobs(test_jobs)
    
    # Create manager
    config = RetryConfig(max_passes=3)
    manager = RetryPassManager(config, tracker)
    
    # Test start_new_pass
    stats = manager.start_new_pass()
    assert stats.pass_number == 1
    assert manager.current_pass == 1
    print('start_new_pass() OK')
    
    # Simulate some jobs completing
    tracker.claim_next_job(worker_id=0)
    tracker.update_job_status('test1', 'success', worker_id=0)
    tracker.claim_next_job(worker_id=0)
    tracker.update_job_status('test2', 'failed', worker_id=0, error='Timeout error')
    tracker.claim_next_job(worker_id=0)
    tracker.update_job_status('test3', 'success', worker_id=0)
    
    # Test end_pass
    result = manager.end_pass()
    print(f'Pass 1 result: {result.name}')
    
    # Test get_summary
    summary = manager.get_summary()
    assert summary['total_passes'] == 1
    print(f'Summary: {summary}')
    print('Integration test OK')
    
finally:
    # Cleanup
    if os.path.exists(temp_file):
        os.remove(temp_file)
    if os.path.exists(temp_file + '.lock'):
        os.remove(temp_file + '.lock')
"
```

### 6. Unit Test - Pass result determination
```bash
python -c "
import os
import tempfile
from retry_manager import RetryPassManager, RetryConfig, PassResult
from progress_tracker import ProgressTracker

with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    temp_file = f.name

try:
    tracker = ProgressTracker(temp_file)
    
    # Test ALL_COMPLETE - all jobs succeed
    tracker.seed_from_jobs([
        {'job_id': 't1', 'account': 'a1', 'video_path': '/v.mp4', 'caption': 'Test'}
    ])
    
    config = RetryConfig(max_passes=3)
    manager = RetryPassManager(config, tracker)
    manager.start_new_pass()
    
    tracker.claim_next_job(worker_id=0)
    tracker.update_job_status('t1', 'success', worker_id=0)
    
    result = manager.end_pass()
    assert result == PassResult.ALL_COMPLETE, f'Expected ALL_COMPLETE, got {result}'
    print('ALL_COMPLETE detection OK')

finally:
    if os.path.exists(temp_file):
        os.remove(temp_file)
    if os.path.exists(temp_file + '.lock'):
        os.remove(temp_file + '.lock')
"
```

### 7. Integration Test - MAX_PASSES_REACHED detection
```bash
python -c "
import os
import tempfile
from retry_manager import RetryPassManager, RetryConfig, PassResult
from progress_tracker import ProgressTracker

with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
    temp_file = f.name

try:
    tracker = ProgressTracker(temp_file)
    tracker.seed_from_jobs([
        {'job_id': 't1', 'account': 'a1', 'video_path': '/v.mp4', 'caption': 'Test'}
    ])
    
    # Set max_passes=1 to test limit
    config = RetryConfig(max_passes=1)
    manager = RetryPassManager(config, tracker)
    
    # Pass 1 - job fails with retryable error
    manager.start_new_pass()
    tracker.claim_next_job(worker_id=0)
    tracker.update_job_status('t1', 'failed', worker_id=0, error='Timeout')
    
    result = manager.end_pass()
    assert result == PassResult.MAX_PASSES_REACHED, f'Expected MAX_PASSES_REACHED, got {result}'
    print('MAX_PASSES_REACHED detection OK')

finally:
    if os.path.exists(temp_file):
        os.remove(temp_file)
    if os.path.exists(temp_file + '.lock'):
        os.remove(temp_file + '.lock')
"
```

### 8. Run module as script (demo)
```bash
python retry_manager.py
# Should print demo output showing config, enum values, and usage instructions
```
