# Task ID: 61

**Title:** Implement PostingContext Refactor for Unified Path Management

**Status:** done

**Dependencies:** 19 ✓, 20 ✓, 57 ✓

**Priority:** high

**Description:** Refactor parallel_orchestrator.py to use a new PostingContext dataclass that serves as the single source of truth for all paths and settings, replacing scattered path resolution with unified context-based dispatch for both campaign and legacy modes.

**Details:**

## Implementation Overview

Implement the PostingContext refactor as specified in `reviews/CAMPAIGN_ORCHESTRATION_REFACTOR_PLAN.md` to address scattered path resolution, implicit state mutation, and inconsistent parameters. This is a four-phase refactor that maintains backward compatibility.

## Phase 1: Add PostingContext Dataclass to config.py

Add the PostingContext dataclass below the CampaignConfig class in `config.py`:

```python
@dataclass
class PostingContext:
    """
    Unified context for all posting operations.
    
    This is the single source of truth for file paths and settings,
    whether running a campaign or in legacy mode.
    """
    # Required paths
    progress_file: str
    accounts_file: str
    
    # Optional paths (campaign mode)
    state_file: Optional[str] = None
    videos_dir: Optional[str] = None
    captions_file: Optional[str] = None
    
    # Settings
    max_posts_per_account_per_day: int = 1
    
    # Source info
    campaign_name: Optional[str] = None  # None = legacy mode
    campaign_config: Optional['CampaignConfig'] = None
    
    @classmethod
    def from_campaign(cls, campaign: 'CampaignConfig') -> 'PostingContext':
        """Create context from a CampaignConfig."""
        return cls(
            progress_file=campaign.progress_file,
            accounts_file=campaign.accounts_file,
            state_file=campaign.state_file,
            videos_dir=campaign.videos_dir,
            captions_file=campaign.captions_file,
            max_posts_per_account_per_day=campaign.max_posts_per_account_per_day,
            campaign_name=campaign.name,
            campaign_config=campaign,
        )
    
    @classmethod
    def legacy(
        cls,
        progress_file: str = Config.PROGRESS_FILE,
        accounts_file: str = Config.ACCOUNTS_FILE,
        state_file: str = Config.STATE_FILE,
        max_posts_per_account_per_day: int = Config.MAX_POSTS_PER_ACCOUNT_PER_DAY,
    ) -> 'PostingContext':
        """Create context for legacy (non-campaign) mode."""
        return cls(
            progress_file=progress_file,
            accounts_file=accounts_file,
            state_file=state_file,
            max_posts_per_account_per_day=max_posts_per_account_per_day,
            campaign_name=None,
            campaign_config=None,
        )
    
    def get_accounts(self) -> List[str]:
        """Load accounts from the appropriate source."""
        if self.campaign_config:
            return self.campaign_config.get_accounts()
        else:
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
    
    def is_campaign_mode(self) -> bool:
        """Check if running in campaign mode."""
        return self.campaign_name is not None
    
    def describe(self) -> str:
        """Human-readable description of this context."""
        if self.campaign_name:
            return f"campaign '{self.campaign_name}'"
        return "legacy mode (root files)"
```

## Phase 2: Refactor Core Functions

### 2.1 Refactor seed_progress_file() (lines 684-730)

Update signature from:
```python
def seed_progress_file(config: ParallelConfig, state_file: str = "scheduler_state.json", accounts_filter: List[str] = None) -> int:
```

To context-based version:
```python
def seed_progress_file(ctx: PostingContext, parallel_config: ParallelConfig, force_reseed: bool = False) -> int:
```

The function should:
- Use `ctx.progress_file` instead of `config.progress_file`
- Check `ctx.is_campaign_mode()` to determine seeding method
- For campaign mode: call `tracker.seed_from_campaign(ctx.campaign_config, ...)`
- For legacy mode: call `tracker.seed_from_scheduler_state(ctx.state_file, ctx.get_accounts(), ...)`
- Use `ctx.max_posts_per_account_per_day` for daily limits

### 2.2 Refactor run_parallel_posting() (lines 931-1125)

Update signature from:
```python
def run_parallel_posting(num_workers, state_file, force_reseed, force_kill_ports, accounts, retry_all_failed, retry_include_non_retryable, retry_config, campaign_config) -> Dict:
```

To context-based version:
```python
def run_parallel_posting(ctx: PostingContext, num_workers: int = 3, force_reseed: bool = False, retry_all_failed: bool = True, retry_include_non_retryable: bool = False, retry_config: RetryConfig = None) -> Dict:
```

Key changes:
- Remove `state_file`, `accounts`, `campaign_config` parameters (all come from ctx)
- Get `campaign_accounts` via `ctx.get_accounts() if ctx.is_campaign_mode() else None`
- Set `parallel_config.progress_file = ctx.progress_file`
- Use `ctx.campaign_name` for conflict checking
- Use `ctx.describe()` in log messages
- Call new `seed_progress_file(ctx, parallel_config, force_reseed)` signature

### 2.3 Refactor show_status() (lines 875-928)

Update signature from:
```python
def show_status(config: ParallelConfig) -> None:
```

To context-based version:
```python
def show_status(ctx: PostingContext, parallel_config: ParallelConfig) -> None:
```

Key changes:
- Use `ctx.progress_file` instead of `config.progress_file`
- Print `ctx.describe()` in header
- Show campaign-specific info when `ctx.is_campaign_mode()`

### 2.4 Refactor reset_day() (lines 506-575)

Update signature from:
```python
def reset_day(progress_file: str, archive_dir: str = None) -> Tuple[bool, str]:
```

To context-based version:
```python
def reset_day(ctx: PostingContext, archive_dir: str = None) -> Tuple[bool, str]:
```

Key changes:
- Get `progress_file = ctx.progress_file`
- Use `ctx.campaign_name` for campaign-aware conflict checking
- Return `ctx.describe()` in success message

### 2.5 Extract retry_all_failed() as Standalone Function

Create new function (currently inline in main()):
```python
def retry_all_failed_jobs(ctx: PostingContext, include_non_retryable: bool = False) -> int:
    """Reset all failed jobs back to retrying status."""
    if not os.path.exists(ctx.progress_file):
        logger.error(f"Progress file not found: {ctx.progress_file}")
        return 0
    
    tracker = ProgressTracker(ctx.progress_file)
    stats_before = tracker.get_stats()
    
    logger.info(f"Retrying failed jobs for {ctx.describe()}")
    logger.info(f"Current: {stats_before['failed']} failed, {stats_before.get('retrying', 0)} retrying")
    
    count = tracker.retry_all_failed(include_non_retryable=include_non_retryable)
    
    if count > 0:
        stats_after = tracker.get_stats()
        logger.info(f"Reset {count} jobs to retrying")
        logger.info(f"New: {stats_after['failed']} failed, {stats_after.get('retrying', 0)} retrying")
    
    return count
```

## Phase 3: Update main() Entry Point

Restructure main() (lines 1128-1344) to:

1. **Handle --list-campaigns first** (no context needed)

2. **Build PostingContext ONCE** after parsing args:
```python
ctx: PostingContext

if args.campaign:
    campaign_config = load_campaign_or_exit(args.campaign)
    if not campaign_config.enabled:
        logger.error(f"Campaign '{campaign_config.name}' is disabled")
        sys.exit(1)
    ctx = PostingContext.from_campaign(campaign_config)
else:
    ctx = PostingContext.legacy(
        progress_file=Config.PROGRESS_FILE,
        accounts_file=Config.ACCOUNTS_FILE,
        state_file=args.state_file,
    )

logger.info(f"Running in {ctx.describe()}")
```

3. **Update all command dispatches** to use ctx:
- `args.reset_day`: `reset_day(ctx)`
- `args.retry_all_failed`: `retry_all_failed_jobs(ctx, args.retry_include_non_retryable)`
- `args.status`: `show_status(ctx, parallel_config)`
- `args.stop_all`: `full_cleanup(config, campaign_accounts=ctx.get_accounts() if ctx.is_campaign_mode() else None)`
- `args.seed_only`: `seed_progress_file(ctx, parallel_config)`
- `args.run`: `run_parallel_posting(ctx=ctx, num_workers=args.workers, ...)`

4. **Add helper function**:
```python
def load_campaign_or_exit(campaign_arg: str) -> CampaignConfig:
    """Load campaign config or exit with error."""
    campaign_path = os.path.join(Config.PROJECT_ROOT, Config.CAMPAIGNS_DIR, campaign_arg)
    if not os.path.isdir(campaign_path):
        campaign_path = campaign_arg  # Try as direct path
    try:
        return CampaignConfig.from_folder(campaign_path)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Failed to load campaign: {e}")
        sys.exit(1)
```

## Phase 4: Cleanup Legacy Signatures

After testing all phases:

1. Remove old function parameters that are now derived from PostingContext
2. Update any remaining ad-hoc path overrides in run_parallel_posting()
3. Remove `config.progress_file = campaign_config.progress_file` mutations
4. Update docstrings to reference PostingContext
5. Update imports in parallel_orchestrator.py: `from config import Config, CampaignConfig, PostingContext, setup_environment`

## Edge Case Handling

Add validation in PostingContext:
- `get_accounts()` raises ValueError if accounts file is empty
- Log warnings for conflicting CLI flags (e.g., `--state-file` with `--campaign`)
- Ensure progress file campaign mismatch detection in ProgressTracker

## Files Modified

1. `config.py` - Add PostingContext dataclass
2. `parallel_orchestrator.py` - Refactor all functions to use PostingContext

**Test Strategy:**

## Test Strategy

### 1. Unit Test - PostingContext Factory Methods
```bash
python -c "
from config import Config, CampaignConfig, PostingContext

# Test legacy context
ctx = PostingContext.legacy()
assert ctx.progress_file == Config.PROGRESS_FILE
assert ctx.accounts_file == Config.ACCOUNTS_FILE
assert ctx.is_campaign_mode() == False
assert 'legacy' in ctx.describe()
print('Legacy context: OK')

# Test campaign context (if campaign exists)
import os
campaign_path = os.path.join(Config.PROJECT_ROOT, Config.CAMPAIGNS_DIR, 'viral')
if os.path.isdir(campaign_path):
    campaign = CampaignConfig.from_folder(campaign_path)
    ctx = PostingContext.from_campaign(campaign)
    assert ctx.progress_file == campaign.progress_file
    assert ctx.is_campaign_mode() == True
    assert 'viral' in ctx.describe()
    print('Campaign context: OK')
"
```

### 2. Integration Test - seed_progress_file with PostingContext
```bash
python -c "
import tempfile
import os
from config import PostingContext, Config

# Create a test context pointing to temp files
temp_dir = tempfile.mkdtemp()
test_progress = os.path.join(temp_dir, 'test_progress.csv')
test_accounts = os.path.join(temp_dir, 'test_accounts.txt')

# Write test accounts
with open(test_accounts, 'w') as f:
    f.write('test_account_1\ntest_account_2\n')

ctx = PostingContext.legacy(
    progress_file=test_progress,
    accounts_file=test_accounts,
)

# Verify context properties
assert ctx.get_accounts() == ['test_account_1', 'test_account_2']
assert not ctx.is_campaign_mode()
print('PostingContext.get_accounts(): OK')

# Cleanup
import shutil
shutil.rmtree(temp_dir)
"
```

### 3. Functional Test - show_status with PostingContext
```bash
# Test status command with legacy context
python parallel_orchestrator.py --status

# Test status command with campaign context (if campaign exists)
python parallel_orchestrator.py --campaign viral --status
```

### 4. Functional Test - reset_day with PostingContext
```bash
# Create test progress file first
python parallel_orchestrator.py --campaign viral --seed-only

# Test reset (should archive the file)
python parallel_orchestrator.py --campaign viral --reset-day

# Verify archive was created
ls campaigns/viral/progress_*.csv
```

### 5. Functional Test - Full Run with PostingContext
```bash
# Test legacy mode (should work as before)
python parallel_orchestrator.py --workers 1 --status

# Test campaign mode (uses PostingContext.from_campaign)
python parallel_orchestrator.py --campaign viral --workers 1 --run

# Verify context was used correctly in logs (should show "campaign 'viral'" not path)
grep "campaign 'viral'" logs/orchestrator.log
```

### 6. Regression Test - Verify No Breaking Changes
```bash
# Existing CLI commands must continue to work:

# Status check (legacy)
python parallel_orchestrator.py --status

# List campaigns
python parallel_orchestrator.py --list-campaigns

# Seed only (legacy)
python parallel_orchestrator.py --seed-only --force-reseed

# Campaign run (should use PostingContext internally)
python parallel_orchestrator.py --campaign viral --status
```

### 7. Edge Case Tests
```bash
# Test empty accounts file handling
python -c "
import tempfile
import os
from config import PostingContext

temp_dir = tempfile.mkdtemp()
empty_accounts = os.path.join(temp_dir, 'empty.txt')
open(empty_accounts, 'w').close()

ctx = PostingContext.legacy(accounts_file=empty_accounts)
try:
    accounts = ctx.get_accounts()
    # Should return empty list or raise ValueError
    if not accounts:
        print('Empty accounts handled: OK')
except ValueError as e:
    print(f'Empty accounts raised error: OK - {e}')

import shutil
shutil.rmtree(temp_dir)
"

# Test conflicting flags warning
python parallel_orchestrator.py --campaign viral --state-file other.json --status 2>&1 | grep -i "ignored\|warning"
```

### 8. Final Verification Checklist
- [ ] PostingContext.from_campaign() creates correct context
- [ ] PostingContext.legacy() creates correct context  
- [ ] ctx.get_accounts() returns correct accounts for both modes
- [ ] ctx.is_campaign_mode() returns correct boolean
- [ ] ctx.describe() returns human-readable string
- [ ] seed_progress_file(ctx, ...) works for both modes
- [ ] run_parallel_posting(ctx, ...) works for both modes
- [ ] show_status(ctx, ...) shows correct paths
- [ ] reset_day(ctx) archives correct file
- [ ] main() builds context once and passes to all commands
- [ ] No regression in existing CLI behavior
