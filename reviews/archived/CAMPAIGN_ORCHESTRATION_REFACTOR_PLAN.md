# Campaign Orchestration Refactor Plan

## Status: IMPLEMENTED ✅

All phases of this refactoring plan have been implemented as of 2025-12-15.

## Overview

This document describes a clean orchestration model where `CampaignConfig` serves as the **single source of truth** when `--campaign` is specified, while preserving backward compatibility for non-campaign (legacy) runs.

## Current Problems

1. **Scattered Path Resolution**: Campaign paths are derived in multiple places with ad-hoc overrides
2. **Implicit State**: `config.progress_file` is mutated after creation, making data flow unclear
3. **Inconsistent Parameters**: Functions take different combinations of paths vs objects
4. **No Central Validation**: Campaign validation happens at load time, not at operation time

## Proposed Architecture

### Core Concept: `PostingContext`

Create a unified context object that encapsulates all paths and settings needed for any operation:

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

---

## Refactored Function Signatures

### 1. `seed_progress_file()`

**Current:**
```python
def seed_progress_file(
    config: ParallelConfig,
    state_file: str = "scheduler_state.json",
    accounts_filter: List[str] = None
) -> int:
```

**Proposed:**
```python
def seed_progress_file(
    ctx: PostingContext,
    parallel_config: ParallelConfig,
    force_reseed: bool = False,
) -> int:
    """
    Seed progress file from campaign or legacy state.

    Args:
        ctx: PostingContext with all paths and settings
        parallel_config: Worker configuration
        force_reseed: If True, overwrite existing progress file

    Returns:
        Number of jobs seeded
    """
    tracker = ProgressTracker(ctx.progress_file)

    # Check existing file
    if tracker.exists() and not force_reseed:
        stats = tracker.get_stats()
        if stats['pending'] > 0 or stats['claimed'] > 0:
            logger.warning(f"Progress file has {stats['pending']} pending jobs")
            return 0

    if ctx.is_campaign_mode():
        # Campaign mode: seed from captions CSV
        return tracker.seed_from_campaign(
            ctx.campaign_config,
            max_posts_per_account_per_day=ctx.max_posts_per_account_per_day
        )
    else:
        # Legacy mode: seed from scheduler_state.json
        accounts = ctx.get_accounts()
        return tracker.seed_from_scheduler_state(
            ctx.state_file,
            accounts,
            max_posts_per_account_per_day=ctx.max_posts_per_account_per_day
        )
```

---

### 2. `run_parallel_posting()`

**Current:**
```python
def run_parallel_posting(
    num_workers: int = 3,
    state_file: str = "scheduler_state.json",
    force_reseed: bool = False,
    force_kill_ports: bool = False,
    accounts: List[str] = None,
    retry_all_failed: bool = True,
    retry_include_non_retryable: bool = False,
    retry_config: RetryConfig = None,
    campaign_config: 'CampaignConfig' = None
) -> Dict:
```

**Proposed:**
```python
def run_parallel_posting(
    ctx: PostingContext,
    num_workers: int = 3,
    force_reseed: bool = False,
    retry_all_failed: bool = True,
    retry_include_non_retryable: bool = False,
    retry_config: RetryConfig = None,
) -> Dict:
    """
    Main entry point for parallel posting.

    Args:
        ctx: PostingContext (campaign or legacy)
        num_workers: Number of parallel workers
        force_reseed: Force reseed progress file
        retry_all_failed: Retry failed jobs from previous runs
        retry_include_non_retryable: Include non-retryable in retry
        retry_config: Multi-pass retry configuration

    Returns:
        Dict with results
    """
    global _active_config, _shutdown_requested, _active_campaign_accounts

    # Setup
    setup_signal_handlers()
    parallel_config = get_config(num_workers=num_workers)
    parallel_config.progress_file = ctx.progress_file

    # Store for emergency cleanup
    campaign_accounts = ctx.get_accounts() if ctx.is_campaign_mode() else None
    _active_campaign_accounts = campaign_accounts

    logger.info(f"Starting posting for {ctx.describe()}")
    logger.info(f"  Progress file: {ctx.progress_file}")
    logger.info(f"  Accounts: {len(ctx.get_accounts())}")

    # Check conflicts (campaign-aware)
    has_conflicts, conflicts = check_for_running_orchestrators(ctx.campaign_name)
    if has_conflicts:
        return {'error': 'orchestrator_conflict', 'conflicts': conflicts}

    # Cleanup (campaign-aware)
    full_cleanup(parallel_config, campaign_accounts=campaign_accounts)

    # Seed if needed
    tracker = ProgressTracker(ctx.progress_file)
    if not tracker.exists() or force_reseed:
        count = seed_progress_file(ctx, parallel_config, force_reseed)
        if count == 0:
            return {'error': 'no_jobs'}

    # ... rest of run logic with ctx used throughout
```

---

### 3. `show_status()`

**Current:**
```python
def show_status(config: ParallelConfig) -> None:
```

**Proposed:**
```python
def show_status(ctx: PostingContext, parallel_config: ParallelConfig) -> None:
    """
    Show current status of progress and resources.

    Args:
        ctx: PostingContext for file paths
        parallel_config: Worker configuration
    """
    print("\n" + "="*60)
    print(f"PARALLEL POSTING STATUS - {ctx.describe()}")
    print("="*60)

    # Progress stats from ctx.progress_file
    tracker = ProgressTracker(ctx.progress_file)
    if tracker.exists():
        stats = tracker.get_stats()
        print(f"\nProgress ({ctx.progress_file}):")
        # ... rest of status output

    # If campaign mode, show campaign-specific info
    if ctx.is_campaign_mode():
        print(f"\nCampaign Info:")
        print(f"  Name: {ctx.campaign_name}")
        print(f"  Videos: {ctx.videos_dir}")
        print(f"  Accounts: {len(ctx.get_accounts())}")
```

---

### 4. `reset_day()`

**Current:**
```python
def reset_day(progress_file: str, archive_dir: str = None) -> Tuple[bool, str]:
```

**Proposed:**
```python
def reset_day(ctx: PostingContext, archive_dir: str = None) -> Tuple[bool, str]:
    """
    Archive progress file and start fresh for a new day.

    Args:
        ctx: PostingContext with progress_file path
        archive_dir: Optional archive directory (default: same as progress file)

    Returns:
        (success, message)
    """
    progress_file = ctx.progress_file

    # Check for conflicts (campaign-aware)
    has_conflicts, conflicts = check_for_running_orchestrators(ctx.campaign_name)
    if has_conflicts:
        return False, f"Cannot reset while orchestrator(s) running: {conflicts}"

    if not os.path.exists(progress_file):
        return False, f"Progress file not found: {progress_file}"

    # ... rest of reset logic

    return True, f"Reset complete for {ctx.describe()}"
```

---

### 5. `retry_all_failed()`

**Current:** (inline in main())

**Proposed:**
```python
def retry_all_failed(
    ctx: PostingContext,
    include_non_retryable: bool = False
) -> int:
    """
    Reset all failed jobs back to retrying status.

    Args:
        ctx: PostingContext with progress_file path
        include_non_retryable: Include non-retryable errors

    Returns:
        Number of jobs reset to retrying
    """
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

---

## Refactored `main()` Entry Point

```python
def main():
    """CLI entry point with clean context-based dispatch."""
    parser = argparse.ArgumentParser(...)
    # ... argument definitions ...
    args = parser.parse_args()

    parallel_config = get_config(num_workers=args.workers)

    # ============================================================
    # STEP 1: Handle --list-campaigns (no context needed)
    # ============================================================
    if args.list_campaigns:
        list_campaigns_command()
        sys.exit(0)

    # ============================================================
    # STEP 2: Build PostingContext (single point of truth)
    # ============================================================
    ctx: PostingContext

    if args.campaign:
        # Campaign mode
        campaign_config = load_campaign_or_exit(args.campaign)

        # Check if campaign is enabled
        if not campaign_config.enabled:
            logger.error(f"Campaign '{campaign_config.name}' is disabled")
            sys.exit(1)

        ctx = PostingContext.from_campaign(campaign_config)
        logger.info(f"Loaded {ctx.describe()}")
        logger.info(f"  Progress: {ctx.progress_file}")
        logger.info(f"  Accounts: {len(ctx.get_accounts())}")
    else:
        # Legacy mode
        accounts_file = Config.ACCOUNTS_FILE
        if args.accounts:
            # Override accounts if provided via CLI
            accounts_list = [a.strip() for a in args.accounts.split(',')]
            # Write temp accounts file or handle differently

        ctx = PostingContext.legacy(
            progress_file=Config.PROGRESS_FILE,
            accounts_file=accounts_file,
            state_file=args.state_file,
        )
        logger.info(f"Running in {ctx.describe()}")

    # ============================================================
    # STEP 3: Dispatch to operation (all use ctx)
    # ============================================================

    if args.reset_day:
        success, message = reset_day(ctx)
        if not success:
            logger.error(message)
            sys.exit(1)
        logger.info(message)

    elif args.retry_all_failed:
        count = retry_all_failed(ctx, args.retry_include_non_retryable)
        if count == 0:
            logger.info("No failed jobs to retry")

    elif args.status:
        show_status(ctx, parallel_config)

    elif args.stop_all:
        stop_all_command(ctx, parallel_config)

    elif args.seed_only:
        count = seed_progress_file(ctx, parallel_config, args.force_reseed)
        if count == 0:
            logger.error("No jobs seeded")
            sys.exit(1)
        logger.info(f"Seeded {count} jobs")

    elif args.run:
        # Safety check
        if args.force_reseed and os.path.exists(ctx.progress_file):
            logger.error("--force-reseed not allowed with existing progress file")
            sys.exit(1)

        retry_cfg = RetryConfig(
            max_passes=args.max_passes,
            retry_delay_seconds=args.retry_delay,
        )

        results = run_parallel_posting(
            ctx=ctx,
            num_workers=args.workers,
            force_reseed=args.force_reseed,
            retry_all_failed=True,
            retry_include_non_retryable=args.retry_include_non_retryable,
            retry_config=retry_cfg,
        )

        if results.get('error'):
            sys.exit(1)

    else:
        parser.print_help()


def load_campaign_or_exit(campaign_arg: str) -> CampaignConfig:
    """Load campaign config or exit with error."""
    # Try as name in campaigns/ directory
    campaign_path = os.path.join(Config.PROJECT_ROOT, Config.CAMPAIGNS_DIR, campaign_arg)

    if not os.path.isdir(campaign_path):
        # Try as direct path
        campaign_path = campaign_arg

    try:
        return CampaignConfig.from_folder(campaign_path)
    except FileNotFoundError as e:
        logger.error(f"Campaign folder not found: {campaign_path}")
        logger.error("Available campaigns:")
        for c in CampaignConfig.list_campaigns():
            logger.error(f"  - {c.name}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Invalid campaign '{campaign_arg}': {e}")
        sys.exit(1)


def list_campaigns_command():
    """Handle --list-campaigns command."""
    campaigns = CampaignConfig.list_campaigns()

    if not campaigns:
        print("\nNo campaigns found in campaigns/ directory")
        print("Create a campaign folder with:")
        print("  - accounts.txt (one account per line)")
        print("  - captions.csv (filename,post_caption columns)")
        print("  - videos/ subfolder with .mp4 files")
        return

    print("\n" + "="*60)
    print("AVAILABLE CAMPAIGNS")
    print("="*60)

    for c in campaigns:
        status = "ENABLED" if c.enabled else "DISABLED"
        accounts = c.get_accounts()
        print(f"\n  {c.name} [{status}]")
        print(f"    Accounts:     {len(accounts)}")
        print(f"    Videos:       {c.videos_dir}")
        print(f"    Captions:     {c.captions_file}")
        print(f"    Progress:     {c.progress_file}")
        print(f"    Daily limit:  {c.max_posts_per_account_per_day} posts/account")

    print("\n" + "="*60)
    print("Usage: python parallel_orchestrator.py --campaign <name> --run")
    print("="*60 + "\n")
```

---

## Edge Cases and Error Handling

### 1. Missing Campaign Files

| Missing File | Detection | Behavior |
|-------------|-----------|----------|
| `accounts.txt` | `CampaignConfig.from_folder()` | Raise `ValueError`, exit with message |
| `captions.csv` | `CampaignConfig.from_folder()` | Raise `ValueError`, exit with message |
| Videos folder | `CampaignConfig.from_folder()` | Raise `ValueError`, exit with message |
| `progress.csv` | `ProgressTracker.exists()` | Auto-create on seed |
| `campaign.json` | `CampaignConfig.from_folder()` | Optional, use defaults |

```python
# In CampaignConfig.from_folder(), add detailed error messages:
if not os.path.exists(accounts_file):
    raise ValueError(
        f"Campaign '{name}' missing accounts.txt\n"
        f"  Expected: {accounts_file}\n"
        f"  Create this file with one account name per line"
    )
```

### 2. Empty Files

```python
# In PostingContext.get_accounts():
def get_accounts(self) -> List[str]:
    accounts = self._load_accounts()
    if not accounts:
        raise ValueError(f"No accounts found in {self.accounts_file}")
    return accounts
```

### 3. Disabled Campaigns

```python
# In load_campaign_or_exit():
if not campaign_config.enabled:
    logger.error(f"Campaign '{campaign_config.name}' is disabled")
    logger.error("Enable it by setting 'enabled: true' in campaign.json")
    sys.exit(1)
```

### 4. Campaign/Legacy Confusion

```python
# Prevent mixing campaign and legacy flags:
if args.campaign and args.state_file != 'scheduler_state.json':
    logger.warning("--state-file ignored when --campaign is specified")

if args.campaign and args.accounts:
    logger.warning("--accounts ignored when --campaign is specified (using campaign accounts)")
```

### 5. Progress File from Wrong Campaign

```python
# In ProgressTracker, add campaign tracking:
def seed_from_campaign(self, campaign_config, ...):
    # Store campaign name in progress file header or metadata
    # Validate on load that progress file matches expected campaign
```

---

## Migration Path

### Phase 1: Add PostingContext (Non-Breaking)

1. Add `PostingContext` dataclass to `config.py`
2. Add `from_campaign()` and `legacy()` factory methods
3. Keep existing function signatures, add new context-based variants

### Phase 2: Refactor Functions (Internal)

1. Create `_seed_progress_file_ctx()` that takes PostingContext
2. Have existing `seed_progress_file()` build context and delegate
3. Same pattern for other functions

### Phase 3: Update main() (Visible Change)

1. Build PostingContext once at the top of main()
2. Pass ctx to all operations
3. Remove ad-hoc path overrides

### Phase 4: Cleanup (Breaking)

1. Remove legacy function signatures
2. Require PostingContext for all operations
3. Update any external callers

---

## Implementation Checklist

- [x] Add `PostingContext` dataclass to `config.py`
- [x] Add factory methods `from_campaign()` and `legacy()`
- [x] Add `get_accounts()` and `is_campaign_mode()` methods
- [x] Refactor `seed_progress_file()` to use context → `seed_progress_file_ctx()`
- [x] Refactor `run_parallel_posting()` to use context → `run_parallel_posting_ctx()`
- [x] Refactor `show_status()` to use context → `show_status_ctx()`
- [x] Refactor `reset_day()` to use context → `reset_day_ctx()`
- [x] Extract `retry_all_failed()` as standalone function → `retry_all_failed_ctx()`
- [x] Update `main()` to build context once and dispatch
- [x] Add validation for edge cases
- [x] Update `load_campaign_or_exit()` helper
- [x] Update `list_campaigns_command()` helper
- [x] Add campaign name to log messages
- [x] Test with viral campaign
- [ ] Test with podcast campaign
- [x] Test legacy (no campaign) mode
- [ ] Test concurrent campaigns

---

## Benefits

1. **Single Source of Truth**: All paths come from one `PostingContext` object
2. **Clear Data Flow**: No mutation of config objects after creation
3. **Type Safety**: `PostingContext` enforces required fields
4. **Testability**: Easy to create test contexts
5. **Extensibility**: Add new context fields without changing signatures
6. **Self-Documenting**: `ctx.describe()` makes logs clear
7. **Campaign Isolation**: Each campaign is fully independent
