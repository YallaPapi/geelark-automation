# Task ID: 60

**Title:** Design Clean Campaign Orchestration Model with CampaignOrchestrator Class

**Status:** done

**Dependencies:** 25 ✓, 54 ✓, 57 ✓, 59 ✓

**Priority:** high

**Description:** Create a CampaignOrchestrator class or refactor existing orchestration functions to make CampaignConfig the single source of truth when --campaign is specified, with well-defined function signatures and backward compatibility for non-campaign runs.

**Details:**

## Implementation Overview

The current parallel_orchestrator.py has campaign logic scattered throughout various functions with ad-hoc CampaignConfig handling. This task designs a clean orchestration model that makes CampaignConfig the central authority when running campaigns.

## Option 1: CampaignOrchestrator Class (Recommended)

Create a new class `CampaignOrchestrator` in `parallel_orchestrator.py` (or separate `campaign_orchestrator.py`) that encapsulates all campaign-aware operations:

```python
@dataclass
class CampaignOrchestrator:
    """
    Orchestrates parallel posting with campaign as the single source of truth.
    
    When campaign_config is provided, ALL paths and settings come from it.
    When campaign_config is None, falls back to legacy behavior.
    """
    campaign_config: Optional[CampaignConfig] = None
    parallel_config: ParallelConfig = field(default_factory=get_config)
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    
    def __post_init__(self):
        """Override parallel_config paths from campaign if specified."""
        if self.campaign_config:
            self.parallel_config.progress_file = self.campaign_config.progress_file
            self._accounts = self.campaign_config.get_accounts()
            self._campaign_name = self.campaign_config.name
        else:
            self._accounts = None
            self._campaign_name = None
```

## Exact Function Signatures

### 1. seed_progress_file()
```python
def seed_progress_file(
    self,
    force_reseed: bool = False,
    state_file: str = "scheduler_state.json"
) -> int:
    """
    Seed the progress file from campaign or legacy state.
    
    When campaign_config is set:
        - Uses campaign.captions_file, campaign.videos_dir, campaign.get_accounts()
        - Calls ProgressTracker.seed_from_campaign(self.campaign_config)
    When campaign_config is None:
        - Uses legacy scheduler_state.json
        - Calls ProgressTracker.seed_from_scheduler_state(state_file)
    
    Args:
        force_reseed: If True, delete existing progress file first
        state_file: Path to scheduler_state.json (only used if no campaign)
    
    Returns:
        Number of jobs seeded
    
    Raises:
        FileNotFoundError: If required source files don't exist
        ValueError: If campaign is disabled (campaign_config.enabled == False)
    """
```

### 2. run_parallel_posting()
```python
def run_parallel_posting(
    self,
    num_workers: int = 3,
    force_kill_ports: bool = False,
    retry_all_failed: bool = True,
    retry_include_non_retryable: bool = False
) -> Dict[str, Any]:
    """
    Main entry point for parallel posting with campaign awareness.
    
    Behavior:
        1. Check for running orchestrators (campaign-scoped conflict detection)
        2. Cleanup resources (campaign-scoped phone stopping)
        3. Seed progress file (from campaign or legacy)
        4. Start workers with multi-pass retry loop
        5. Return final stats
    
    Args:
        num_workers: Number of parallel worker processes
        force_kill_ports: Kill processes blocking Appium ports
        retry_all_failed: Retry infrastructure failures from previous runs
        retry_include_non_retryable: Also retry account-level failures
    
    Returns:
        Dict with keys: success, failed, pending, retrying, error (if any),
                       retry_summary, failure_breakdown
    """
```

### 3. show_status()
```python
def show_status(self) -> None:
    """
    Display current status of the orchestrator.
    
    Shows:
        - Campaign info (name, accounts, videos_dir) if campaign mode
        - Progress file stats (pending/claimed/success/failed/retrying)
        - Per-worker stats
        - Appium server status on allocated ports
        - Running Geelark phones (filtered to campaign accounts if applicable)
    """
```

### 4. reset_day()
```python
def reset_day(self) -> Tuple[bool, str]:
    """
    Archive current progress file and start fresh for a new day.
    
    When campaign_config is set:
        - Archives campaign.progress_file to campaign_dir/progress_YYYYMMDD.csv
        - Creates fresh progress_file with headers only
    When campaign_config is None:
        - Archives Config.PROGRESS_FILE to parallel_progress_YYYYMMDD.csv
    
    Returns:
        (success: bool, message: str describing result or error)
    
    Raises:
        RuntimeError: If orchestrators are running for this campaign
    """
```

### 5. retry_all_failed()
```python
def retry_all_failed(
    self,
    include_non_retryable: bool = False
) -> int:
    """
    Reset all failed jobs to retrying status.
    
    Args:
        include_non_retryable: If True, also retry account-level failures
    
    Returns:
        Number of jobs reset to retrying
    """
```

## Option 2: Refactor Existing Functions (Alternative)

If a class is too invasive, refactor existing module-level functions to accept `campaign_config: CampaignConfig = None` as first parameter:

```python
def seed_progress_file(
    campaign_config: CampaignConfig = None,
    config: ParallelConfig = None,
    state_file: str = "scheduler_state.json",
    accounts_filter: List[str] = None
) -> int:
    """Seed progress file from campaign (if provided) or legacy state."""
    if campaign_config:
        # Campaign is single source of truth
        tracker = ProgressTracker(campaign_config.progress_file)
        return tracker.seed_from_campaign(campaign_config, ...)
    else:
        # Legacy behavior
        config = config or get_config()
        tracker = ProgressTracker(config.progress_file)
        return tracker.seed_from_scheduler_state(state_file, accounts_filter, ...)
```

## Edge Cases to Handle

### 1. Missing Campaign Files
```python
def _validate_campaign(self) -> None:
    """Validate campaign configuration before operations."""
    if not self.campaign_config:
        return  # Non-campaign mode, skip validation
    
    c = self.campaign_config
    
    # Required files
    if not os.path.exists(c.accounts_file):
        raise FileNotFoundError(f"Campaign accounts file not found: {c.accounts_file}")
    if not os.path.exists(c.captions_file):
        raise FileNotFoundError(f"Campaign captions file not found: {c.captions_file}")
    if not os.path.isdir(c.videos_dir):
        raise FileNotFoundError(f"Campaign videos directory not found: {c.videos_dir}")
    
    # Accounts check
    accounts = c.get_accounts()
    if not accounts:
        raise ValueError(f"Campaign has no accounts in {c.accounts_file}")
```

### 2. Disabled Campaigns
```python
if self.campaign_config and not self.campaign_config.enabled:
    raise ValueError(f"Campaign '{self.campaign_config.name}' is disabled. "
                    "Set enabled=true in campaign.json to run.")
```

### 3. Non-Campaign Backward Compatibility
```python
# In main() CLI handling
if args.campaign:
    orchestrator = CampaignOrchestrator(
        campaign_config=CampaignConfig.from_folder(campaign_path)
    )
else:
    # Legacy non-campaign mode
    orchestrator = CampaignOrchestrator(campaign_config=None)
    # Uses Config.PROGRESS_FILE, scheduler_state.json, accounts.txt
```

### 4. Progress File Doesn't Exist
```python
def seed_progress_file(self, ...):
    tracker = ProgressTracker(self._get_progress_file())
    
    # Allow seeding even if file doesn't exist - tracker handles creation
    if not tracker.exists():
        logger.info("Creating new progress file")
    elif not force_reseed:
        stats = tracker.get_stats()
        if stats['pending'] > 0:
            logger.warning(f"Progress file has {stats['pending']} pending jobs")
            return 0  # Don't overwrite existing work
```

## Files to Modify

1. **parallel_orchestrator.py** - Add CampaignOrchestrator class or refactor existing functions
2. **config.py** - Add `is_valid()` method to CampaignConfig for validation
3. **progress_tracker.py** - No changes needed (already has seed_from_campaign)

## Integration with Existing Code

The main() function should create CampaignOrchestrator and delegate to it:

```python
def main():
    args = parse_args()
    
    # Create orchestrator (campaign or legacy mode)
    campaign_config = None
    if args.campaign:
        campaign_config = CampaignConfig.from_folder(args.campaign)
    
    orchestrator = CampaignOrchestrator(
        campaign_config=campaign_config,
        parallel_config=get_config(num_workers=args.workers),
        retry_config=RetryConfig(
            max_passes=args.max_passes,
            retry_delay_seconds=args.retry_delay
        )
    )
    
    if args.run:
        orchestrator.run_parallel_posting(...)
    elif args.status:
        orchestrator.show_status()
    elif args.reset_day:
        orchestrator.reset_day()
    # ... etc
```

**Test Strategy:**

## Test Strategy

### 1. Unit Test - CampaignOrchestrator Initialization

```bash
python -c "
from parallel_orchestrator import CampaignOrchestrator
from config import CampaignConfig, Config
from parallel_config import get_config

# Test 1: Non-campaign mode
orch = CampaignOrchestrator(campaign_config=None)
assert orch.campaign_config is None
assert orch.parallel_config.progress_file == Config.PROGRESS_FILE
print('Test 1 PASSED: Non-campaign mode initializes correctly')

# Test 2: Campaign mode
import tempfile, os
temp_dir = tempfile.mkdtemp()
os.makedirs(os.path.join(temp_dir, 'videos'))
with open(os.path.join(temp_dir, 'accounts.txt'), 'w') as f:
    f.write('test_account\n')
with open(os.path.join(temp_dir, 'captions.csv'), 'w') as f:
    f.write('filename,post_caption\ntest.mp4,Test caption\n')
with open(os.path.join(temp_dir, 'videos', 'test.mp4'), 'w') as f:
    f.write('fake')

campaign = CampaignConfig.from_folder(temp_dir)
orch = CampaignOrchestrator(campaign_config=campaign)
assert orch.campaign_config == campaign
assert orch.parallel_config.progress_file == campaign.progress_file
print('Test 2 PASSED: Campaign mode initializes correctly')

import shutil
shutil.rmtree(temp_dir)
"
```

### 2. Function Signature Verification

```bash
python -c "
from parallel_orchestrator import CampaignOrchestrator
import inspect

# Verify seed_progress_file signature
sig = inspect.signature(CampaignOrchestrator.seed_progress_file)
params = list(sig.parameters.keys())
assert 'self' in params
assert 'force_reseed' in params or len(params) >= 1
print('seed_progress_file signature: OK')

# Verify run_parallel_posting signature  
sig = inspect.signature(CampaignOrchestrator.run_parallel_posting)
params = list(sig.parameters.keys())
assert 'num_workers' in params
print('run_parallel_posting signature: OK')

# Verify show_status exists and is callable
assert callable(CampaignOrchestrator.show_status)
print('show_status: OK')

# Verify reset_day exists
assert callable(CampaignOrchestrator.reset_day)
print('reset_day: OK')

# Verify retry_all_failed exists
assert callable(CampaignOrchestrator.retry_all_failed)
print('retry_all_failed: OK')
"
```

### 3. Edge Case Tests

```bash
# Test missing campaign files handling
python -c "
from parallel_orchestrator import CampaignOrchestrator
from config import CampaignConfig
import tempfile, os

# Create incomplete campaign folder
temp_dir = tempfile.mkdtemp()
os.makedirs(os.path.join(temp_dir, 'videos'))
# Missing accounts.txt

try:
    campaign = CampaignConfig.from_folder(temp_dir)
    print('FAILED: Should have raised error for missing accounts.txt')
except ValueError as e:
    print(f'PASSED: Correctly raised ValueError: {e}')

import shutil
shutil.rmtree(temp_dir)
"

# Test disabled campaign handling
python -c "
from parallel_orchestrator import CampaignOrchestrator
from config import CampaignConfig
import tempfile, os, json

temp_dir = tempfile.mkdtemp()
os.makedirs(os.path.join(temp_dir, 'videos'))
with open(os.path.join(temp_dir, 'accounts.txt'), 'w') as f:
    f.write('test_account\n')
with open(os.path.join(temp_dir, 'captions.csv'), 'w') as f:
    f.write('filename,post_caption\ntest.mp4,Test\n')
with open(os.path.join(temp_dir, 'videos', 'test.mp4'), 'w') as f:
    f.write('fake')
with open(os.path.join(temp_dir, 'campaign.json'), 'w') as f:
    json.dump({'enabled': False}, f)

campaign = CampaignConfig.from_folder(temp_dir)
assert campaign.enabled == False
print('PASSED: Disabled campaign detected correctly')

import shutil
shutil.rmtree(temp_dir)
"
```

### 4. Backward Compatibility Test

```bash
# Verify non-campaign mode still works with existing CLI
python parallel_orchestrator.py --status

# Verify legacy seed still works
python -c "
from parallel_orchestrator import seed_progress_file
from parallel_config import get_config
config = get_config(num_workers=1)
# Should not crash when called without campaign
print('Legacy seed_progress_file function exists and is callable')
"
```

### 5. Integration Test - Campaign Mode

```bash
# Create test campaign and verify orchestrator behavior
python -c "
import tempfile, os, shutil
from config import CampaignConfig

# Setup test campaign
temp_dir = tempfile.mkdtemp(prefix='test_campaign_')
videos_dir = os.path.join(temp_dir, 'videos')
os.makedirs(videos_dir)

# Create test files
with open(os.path.join(temp_dir, 'accounts.txt'), 'w') as f:
    f.write('test_acc_1\ntest_acc_2\n')
with open(os.path.join(temp_dir, 'captions.csv'), 'w') as f:
    f.write('filename,post_caption\nvid1.mp4,Caption 1\nvid2.mp4,Caption 2\n')
with open(os.path.join(videos_dir, 'vid1.mp4'), 'w') as f:
    f.write('fake video 1')
with open(os.path.join(videos_dir, 'vid2.mp4'), 'w') as f:
    f.write('fake video 2')

# Load campaign
campaign = CampaignConfig.from_folder(temp_dir)
print(f'Campaign loaded: {campaign.name}')
print(f'Accounts: {campaign.get_accounts()}')
print(f'Progress file: {campaign.progress_file}')

# Verify progress file is inside campaign folder
assert temp_dir in campaign.progress_file
print('PASSED: Progress file correctly scoped to campaign')

shutil.rmtree(temp_dir)
"
```

### 6. CLI Integration Test

```bash
# Test --campaign flag with --status
python parallel_orchestrator.py --campaign viral --status 2>/dev/null || echo "Campaign 'viral' may not exist - expected"

# Test --list-campaigns
python parallel_orchestrator.py --list-campaigns

# Test backward compatibility - no campaign
python parallel_orchestrator.py --status
```
