# Task ID: 62

**Title:** Implement Complete Multi-Campaign Posting System with CLI Integration

**Status:** done

**Dependencies:** 57 ✓, 61 ✓, 19 ✓, 20 ✓, 9 ✓, 27 ✓

**Priority:** medium

**Description:** Integrate full multi-campaign support into the main CLI entrypoint, wiring CampaignConfig and PostingContext throughout the orchestrator for campaign-specific files while preserving legacy mode, and add --list-campaigns functionality.

**Details:**

**Implementation Overview**

Extend the main CLI in `main.py` (or equivalent entrypoint from Task 9) to support `--campaign NAME` flag with full integration across seed, run, status, reset-day, and retry-all-failed operations. Build directly on Task 61's PostingContext and Task 57's CampaignConfig.

**Core CLI Changes (main.py)**

1. **Parse `--campaign` flag early**:
```python
from argparse import ArgumentParser
from config import PostingContext, CampaignConfig
from pathlib import Path

parser = ArgumentParser()
parser.add_argument('--campaign', type=str, help='Campaign name (e.g. "viral", "podcast")')
# ... other flags: --seed-only, --run, --status, --reset-day N, --retry-all-failed
args = parser.parse_args()

ctx = PostingContext.legacy()  # default
if args.campaign:
    campaign_dir = Path('campaigns') / args.campaign
    if not campaign_dir.exists():
        raise ValueError(f"Campaign '{args.campaign}' not found. Run --list-campaigns to see available campaigns.")
    campaign_config = CampaignConfig.from_folder(campaign_dir)
    ctx = PostingContext.from_campaign(campaign_config)  # from Task 61
```

2. **Wire ctx everywhere**:
- Pass `ctx` to ALL functions: `seed_jobs(ctx)`, `run_orchestrator(ctx)`, `print_status(ctx)`, `reset_day(ctx, day)`, `retry_all_failed(ctx)`
- **Every function MUST use ctx.accounts_file, ctx.state_file, ctx.progress_file** instead of hardcoded Config paths
- Update `parallel_orchestrator.py` (Task 19/61) to accept `PostingContext` as first param

3. **Implement subcommands**:

**`--list-campaigns`**:
```python
import glob
from pathlib import Path

campaigns_dir = Path('campaigns')
campaigns = [d.name for d in campaigns_dir.iterdir() if d.is_dir() and (d/'campaign.json').exists()]
print('Available campaigns:', campaigns or 'None')
```

**`--seed-only --campaign NAME`**:
```python
jobs = read_jobs(ctx.accounts_file, ctx.input_csv_path, ctx.video_root_dir)  # Task 2 updated for ctx
ProgressTracker(ctx.progress_file).seed_from_jobs(jobs)
```

**`--run --campaign NAME`** (or no campaign):
```python
if args.retry_all_failed:
    ProgressTracker(ctx.progress_file).retry_all_failed()  # Task 27

ParallelOrchestrator(ctx).run()  # Task 19/61 updated for ctx
```

**`--status --campaign NAME`**:
```python
ProgressTracker(ctx.progress_file).print_status()
```

**`--reset-day N --campaign NAME`**:
```python
ProgressTracker(ctx.progress_file).reset_day(int(args.reset_day))
```

4. **Early failure with clear errors**:
- Check campaign dir + `campaign.json` exists before any operation
- Validate `ctx.accounts_file`, `ctx.progress_file` exist before ProgressTracker ops
- Print: `f"Missing {missing_file} for campaign '{args.campaign}'"`

5. **Preserve legacy mode**:
- No `--campaign` → `PostingContext.legacy()` → uses `Config.ACCOUNTS_FILE`, etc. (Task 61)
- All existing flags work unchanged without `--campaign`

**Update Dependent Modules**:
- `progress_tracker.py`: Accept `progress_file` path as constructor param (already partially done in Task 61)
- `parallel_orchestrator.py`: Use `ctx` for ALL file paths and config

**Best Practices Applied** (from multi-channel research):
- **Unified context object** prevents scattered config (like unified campaign briefs)[1][2]
- **Early validation** mirrors pre-flight checklists[3]
- **Clear CLI feedback** follows consistent messaging across channels[6]

**File Structure Expected** (from Task 57):
```
campaigns/
├── viral/
│   ├── campaign.json
│   ├── accounts.csv
│   ├── progress.csv
│   └── videos/
└── podcast/
    ├── campaign.json
    ├── accounts.csv
    └── ...
```

**Test Strategy:**

**Comprehensive Test Strategy**

### 1. Unit Tests - CLI Parsing & Context Creation**
```bash
python -c '
from main import parse_args_and_get_ctx  # new helper

# Test legacy
ctx = parse_args_and_get_ctx([])
assert ctx.is_legacy

# Test valid campaign
ctx = parse_args_and_get_ctx(["--campaign", "viral"])
assert not ctx.is_legacy
assert ctx.progress_file == "campaigns/viral/progress.csv"

# Test missing campaign - expect ValueError
try: parse_args_and_get_ctx(["--campaign", "missing"]); assert False
except ValueError as e: assert "not found" in str(e)
'
```

### 2. Integration Tests - Full Workflow per Campaign**
**Setup**: Create test campaigns:
```bash
mkdir -p campaigns/{viral,podcast}/videos
# viral/campaign.json, accounts.csv (2 accounts), progress.csv
# podcast/campaign.json, accounts.csv (3 accounts), progress.csv
```

**Test `--list-campaigns`**:
```bash
./main.py --list-campaigns  # expect: ["viral", "podcast"]
```

**Test `--campaign viral --seed-only`**:
```bash
# Create viral/accounts.csv + input csv
./main.py --campaign viral --seed-only
# Verify campaigns/viral/progress.csv seeded correctly (check job count, pending status)
```

**Test `--campaign viral --status`**:
```bash
# Shows viral progress only
```

**Test `--campaign viral --run`**:
```bash
# Uses viral/accounts.csv, viral/progress.csv
# Verify parallel_orchestrator uses correct paths (log inspection)
```

**Test `--campaign podcast --reset-day 1`**:
```bash
# Only affects podcast/progress.csv
```

**Test `--campaign viral --retry-all-failed`**:
```bash
# Resets only viral failed jobs (Task 27 verification)
```

### 3. Cross-Mode Tests**
```bash
# Legacy mode (no --campaign)
./main.py --seed-only  # uses Config.PROGRESS_FILE
./main.py --status     # shows legacy progress

# Verify campaign mode doesn't touch legacy files
ls -la campaigns/*/progress.csv Config.PROGRESS_FILE  # all unchanged
```

### 4. Error Case Tests**
```bash
# Missing campaign files
rm campaigns/viral/accounts.csv
./main.py --campaign viral --run 2>&1 | grep "Missing accounts.csv"

# Non-existent campaign
./main.py --campaign fake --status 2>&1 | grep "not found"
```

### 5. End-to-End Smoke Test**
Run full cycle for both campaigns:
1. `--list-campaigns`
2. `--campaign viral --seed-only`
3. `--campaign viral --run` (mock success)
4. `--campaign viral --status` (shows complete)
5. Repeat for podcast

**Verify**: Each campaign uses isolated files, legacy untouched, all flags work.
