# Task ID: 58

**Title:** Fix Multi-Campaign File Routing and Flag Wiring in Parallel Orchestrator

**Status:** done

**Dependencies:** 20 ✓, 25 ✓, 54 ✓, 57 ✓

**Priority:** medium

**Description:** Audit and correct all logic paths in the multi-campaign posting system so that the --campaign flag and CampaignConfig are consistently used, ensuring all modes (seed-only, run, status, reset-day, retry-all-failed) operate on campaign-specific files instead of root-level files.

**Details:**

## Objectives
- Ensure **all code paths** that accept `--campaign` use **campaign-specific** files for accounts, scheduler state, and progress, instead of root-level defaults.
- Ensure `CampaignConfig` from `config.py` is **the single source of truth** for campaign-specific paths and is **used everywhere it is constructed**.
- Make `parallel_orchestrator.py` and `progress_tracker.py` fully **campaign-aware** for all relevant CLI modes: `--seed-only`, `--run`, `--status`, `--reset-day`, `--retry-all-failed`.

## Design & Best Practices
- Follow centralized configuration best practices by using a **typed config class** (like `CampaignConfig`) rather than scattered string paths, mirroring patterns from `Config` in `config.py`.[4][8]
- Prefer explicit dependency injection of configuration objects (e.g., passing `CampaignConfig` into helpers) over hidden globals to avoid future wiring gaps.[4]
- Keep default (no `--campaign`) behavior intact by falling back to root-level paths only when **no campaign is specified or resolved**.

## Implementation Plan

### 1. Analyze Current Multi-Campaign Wiring
1. Inspect `config.py`:
   - Locate `CampaignConfig` class and its fields (e.g., campaign name, campaign root folder, paths for `accounts.txt`, `scheduler_state.json`, `parallel_progress.csv`, and any other campaign-specific resources).
   - Document a short internal reference of each field and which module is expected to use it.

2. Inspect `parallel_orchestrator.py`:
   - Identify CLI parsing for `--campaign`, `--seed-only`, `--run`, `--status`, `--reset-day`, `--retry-all-failed`.
   - Map every logic path that:
     - Constructs or can construct a `CampaignConfig`.
     - Reads/writes any of the following **root-level** files:
       - `accounts.txt`
       - `scheduler_state.json`
       - `parallel_progress.csv`
     - Calls into helpers or classes (e.g., `ProgressTracker`, Retry manager, scheduler utilities) that may themselves open these files.

3. Inspect `progress_tracker.py`:
   - Identify all file path usages: main progress CSV(s), daily reset markers, any other state files.
   - Determine if it already accepts a configurable path (e.g., via constructor arg) or if it hardcodes `parallel_progress.csv`.
   - Note all call sites in `parallel_orchestrator.py` and any other orchestrators.

4. Identify “missing wiring” locations:
   - Places where `CampaignConfig` is created but **not passed** down to the lower-level functions/classes.
   - Places where `--campaign` is parsed but logic still uses `Config` or hardcoded file names instead of campaign-specific paths.

### 2. Normalize Campaign Path Access via CampaignConfig
1. Extend/confirm `CampaignConfig` API in `config.py`:
   - Ensure it exposes clear, typed properties for at least:
     - `accounts_file: Path`
     - `scheduler_state_file: Path`
     - `progress_file: Path` (or more granular if multiple CSVs are used per campaign)
   - If not present, add helper constructors such as:
     - `CampaignConfig.from_name(campaign_name: str)` → resolves `campaigns/<name>/...` layout defined in Task 57.
   - Ensure defaults align with Task 57’s folder structure and are **relative to project root** from `Config.PROJECT_ROOT`.

2. Centralize campaign resolution logic:
   - In `parallel_orchestrator.py`, introduce a small helper, e.g.:
     ```python
     def resolve_campaign_config(args) -> Optional[CampaignConfig]:
         if not getattr(args, "campaign", None):
             return None
         return CampaignConfig.from_name(args.campaign)
     ```
   - This function becomes the single way to map `--campaign` to a `CampaignConfig` instance.

### 3. Make Parallel Orchestrator Fully Campaign-Aware
For each CLI mode, ensure it uses campaign paths and passes `CampaignConfig` into collaborators.

1. Shared initialization:
   - At the top of `main()` / orchestrator entrypoint:
     ```python
     campaign_config = resolve_campaign_config(args)
     ```
   - For all downstream operations, **pass `campaign_config` explicitly** (or derived paths) instead of using root-level filenames.

2. `--seed-only` mode:
   - If `--campaign` is provided:
     - Use `campaign_config.accounts_file` instead of `accounts.txt`.
     - If seeding involves initializing progress/state files, use campaign-specific files from `campaign_config`.
   - Ensure any progress tracker or scheduler initialization receives campaign-specific paths.

3. `--run` mode:
   - When creating `ProgressTracker`, `RetryPassManager`, or similar, ensure they are constructed with campaign-specific file paths (e.g., `campaign_config.progress_file`).
   - Where accounts are loaded, use `campaign_config.accounts_file`.
   - Where scheduler state is read/written, use `campaign_config.scheduler_state_file`.

4. `--status` mode:
   - Ensure status reporting uses the campaign-specific progress and state files; if no `--campaign` is passed, continue to report global/root status.
   - If multiple campaigns exist, status for a given campaign **must not read** from the root-level `parallel_progress.csv`.

5. `--reset-day` mode:
   - Ensure the daily reset logic operates on the progress and any related state for the **selected campaign only**.
   - Root-level reset remains available when no `--campaign` is provided.

6. `--retry-all-failed` mode:
   - When building the failed queue, source failures from the campaign-specific progress file.
   - Ensure that any updated state (e.g., new rows or pass markers) is written back to the same campaign-specific progress file.

### 4. Refactor ProgressTracker to Support Campaign Paths
1. Update `progress_tracker.py` API:
   - If it currently hardcodes `parallel_progress.csv`, change the main class to accept a `progress_path: Path` (or similar) argument in its constructor.
   - Keep a backwards-compatible default (e.g., when `progress_path` is `None`, use root-level file) to avoid breaking legacy callers.

2. Inject paths from orchestrator:
   - In `parallel_orchestrator.py`, always pass an explicit `progress_path` based on:
     ```python
     progress_path = campaign_config.progress_file if campaign_config else DEFAULT_PROGRESS_FILE
     ```
   - Similarly, if `ProgressTracker` handles auxiliary files (e.g., per-pass CSVs or lock files), ensure these are derived relative to `progress_path` or the campaign folder.

3. Verify RetryPassManager and other helpers:
   - If `RetryPassManager` or other classes currently accept a path or `ProgressTracker`, ensure the campaign-specific `ProgressTracker` instance is passed through.
   - Do not re-open root-level progress files inside these helpers; rely on the `ProgressTracker` or explicit paths provided.

### 5. Eliminate Remaining Root-Level File Usage in Campaign Contexts
1. Static grep / code search:
   - Search the codebase for `accounts.txt`, `scheduler_state.json`, `parallel_progress.csv` and review each hit.
   - For each usage:
     - If it is part of **campaign-aware** code or reachable from `--campaign` flows, replace it with `CampaignConfig`-derived paths.
     - If it is part of purely root-level / default operation, ensure it is clearly documented as such.

2. Guard against accidental root fallback:
   - In campaign flows, avoid implicit fallback to root paths. For example, if `CampaignConfig` resolution fails, **fail fast** with a clear error indicating an invalid campaign name, rather than silently using root files.

### 6. Error Handling and Logging Improvements
1. Add clear log messages:
   - When `--campaign` is used, log which campaign and which file paths are active:
     - Campaign name
     - Accounts file path
     - Scheduler state path
     - Progress path
   - This greatly simplifies diagnosing mis-wiring.

2. Validation:
   - When constructing `CampaignConfig`, validate that the required files and folders exist, or provide a clear error suggesting how to initialize the campaign (e.g., run a campaign init script).

## Example Code Sketches (Non-Authoritative)

```python
# config.py
@dataclass
class CampaignConfig:
    name: str
    root: Path
    accounts_file: Path
    scheduler_state_file: Path
    progress_file: Path

    @classmethod
    def from_name(cls, name: str) -> "CampaignConfig":
        root = Config.PROJECT_ROOT / "campaigns" / name
        return cls(
            name=name,
            root=root,
            accounts_file=root / "accounts.txt",
            scheduler_state_file=root / "scheduler_state.json",
            progress_file=root / "parallel_progress.csv",
        )
```

```python
# parallel_orchestrator.py

def main(argv=None):
    args = parse_args(argv)
    campaign_config = resolve_campaign_config(args)

    progress_path = (
        campaign_config.progress_file if campaign_config else DEFAULT_PROGRESS_FILE
    )

    tracker = ProgressTracker(progress_path=progress_path)

    if args.seed_only:
        run_seed_only(args, campaign_config, tracker)
    elif args.run:
        run_campaign(args, campaign_config, tracker)
    elif args.status:
        show_status(args, campaign_config, tracker)
    elif args.reset_day:
        reset_day(args, campaign_config, tracker)
    elif args.retry_all_failed:
        retry_all_failed(args, campaign_config, tracker)
```

```python
# progress_tracker.py
class ProgressTracker:
    def __init__(self, progress_path: Path | str | None = None):
        self.progress_path = Path(progress_path or DEFAULT_PROGRESS_FILE)
        # all internal reads/writes use self.progress_path
```

## Documentation
- Update internal developer docs (e.g., `CLAUDE.md` or campaign README) to describe:
  - The canonical `CampaignConfig` API and how to add new per-campaign files.
  - How `--campaign` affects all orchestrator modes.
  - Example commands for running, checking status, resetting, and retrying for a specific campaign.

**Test Strategy:**

1. **Unit Tests – CampaignConfig and Path Resolution**
- Add tests for `CampaignConfig.from_name()`:
  - Create a temporary `campaigns/test_campaign` folder with dummy `accounts.txt`, `scheduler_state.json`, and `parallel_progress.csv`.
  - Assert that `CampaignConfig.from_name("test_campaign")` resolves all paths correctly.
  - Test behavior when the campaign folder does not exist (expect clear exception or error return).

2. **Unit Tests – ProgressTracker Path Injection**
- Create a temporary directory and pass a custom `progress_path` into `ProgressTracker`.
- Verify that all read/write operations create and use that file instead of the default root-level CSV.
- Ensure legacy behavior still uses the default when `progress_path` is omitted.

3. **Unit Tests – Orchestrator Argument Handling**
- Use `argparse` (or equivalent) test harness to simulate CLI invocations of `parallel_orchestrator.py`:
  - For each mode: `--seed-only`, `--run`, `--status`, `--reset-day`, `--retry-all-failed` with `--campaign test_campaign`.
  - Patch file I/O (e.g., with `tmp_path` in pytest or `unittest.mock`) to capture which file paths are opened.
  - Assert that only **campaign-specific** paths are used and no root-level files are touched.

4. **Integration Tests – End-to-End Campaign Run (Dry-Run / Small Data)**
- Set up two campaigns in a temporary project structure: `campaigns/podcast` and `campaigns/viral`, each with its own accounts and progress files.
- Run orchestrator in a controlled environment (possibly with a dry-run flag or mocked phone/appium layer) for each CLI mode:
  - `--campaign podcast --seed-only`
  - `--campaign podcast --run`
  - `--campaign podcast --status`
  - `--campaign podcast --reset-day`
  - `--campaign podcast --retry-all-failed`
- After each run, assert:
  - Only the podcast campaign files changed for podcast commands.
  - Only the viral campaign files changed for viral commands.
  - Root-level files remain unchanged when `--campaign` is present.

5. **Regression Tests – No-Campaign Behavior**
- Run the same orchestrator modes **without** `--campaign`.
- Assert that behavior remains compatible with previous expectations: root-level files are used and the system functions as before.

6. **Static Analysis and Code Review Checks**
- Add a CI step or checklist item to:
  - Grep for `accounts.txt`, `scheduler_state.json`, and `parallel_progress.csv` and confirm each usage is either:
    - Behind a root-level (no campaign) path, or
    - Derived from `CampaignConfig`.
- Run type checking (e.g., mypy) to ensure `CampaignConfig` fields are properly typed and passed through functions correctly.

7. **Logging Verification**
- In a test or manual run with `--campaign` and verbose logging enabled, confirm log messages clearly indicate:
  - Selected campaign name.
  - Effective paths for accounts, scheduler state, and progress files.
- Use these logs to quickly confirm that no root-level file is used during campaign-specific operations.
