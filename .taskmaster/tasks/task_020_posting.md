# Task ID: 20

**Title:** Implement unified per-account daily posting limits and orchestrator safety controls

**Status:** done

**Dependencies:** 1 ✓, 2 ✓, 9 ✓, 19 ✓

**Priority:** medium

**Description:** Implement a unified posting control system that enforces per-account daily limits, adds orchestrator process safety checks, and introduces a controlled daily reset flow with documentation updates.

**Details:**

Implementation should focus on two modules (`progress_tracker.py`, `parallel_orchestrator.py`) plus `CLAUDE.md`, building on the existing CSV-based progress tracking and multi-process orchestration from Task 19.

1) Introduce unified per-account daily post limit configuration
- Add a configuration entry (e.g. in existing `config.py` or equivalent used by Task 19) for **`max_posts_per_account_per_day`**.
  - Default to **1**.
  - Allow integer values 1–4 (validate and raise on invalid values; keep the API open for future extension).
- Ensure this value is accessible to both `progress_tracker.py` and `parallel_orchestrator.py` without circular imports (pass via function parameters or a small config object where appropriate, instead of importing global state).
- Follow current best practices for configuration: avoid hard-coded constants, and keep default in a single source of truth so tests can override it easily.

2) Enhance `seed_from_scheduler_state()` for per-account limits
- In `progress_tracker.py`, extend `seed_from_scheduler_state()` to:
  - Read the existing progress CSV (the one introduced in Task 19) and compute a **`success_count_by_account: dict[str, int]`**.
    - Count rows where the job is in a terminal **success** state (re-use existing status field semantics from Task 19 to avoid double-defining what “success” means).
    - Use a streaming/iterator-based CSV read to avoid excessive memory use on large files.
  - Filter candidate accounts when seeding from the scheduler/state so that only accounts where `success_count < max_posts_per_account_per_day` are considered for new assignments.
  - Maintain an **in-memory** `success_count_by_account` during seeding and increment counts as new jobs are seeded, so that multiple jobs added in one seeding pass do not exceed the limit even before they are written back.
- Refactor as needed:
  - Extract small helpers such as `_load_success_counts(progress_path) -> dict[str, int]` for testability.
  - Keep all file I/O atomic (e.g. write temp file and rename) if seeding mutates the CSV, to avoid corruption under concurrent reads.
- Document function behavior clearly in docstrings so that both orchestrator and future tools can rely on the same semantics.

3) Add orchestrator startup safety check for duplicate Python orchestrators
- In `parallel_orchestrator.py`, before spawning worker processes, add a **startup guard** that checks for other running Python orchestrator processes.
  - Use a cross-platform-friendly approach such as `psutil.process_iter()` if already available in the project; otherwise, add a minimal, well-scoped dependency or implement a simple `subprocess`-based check, keeping in mind:
    - Only treat **other processes** as conflicts (ignore the current PID).
    - Match by a robust criterion, e.g. command line including the orchestrator entrypoint/module name or a specific `--orchestrator` flag.
  - If another orchestrator is detected, log a clear error and exit non-zero instead of starting new workers.
- Ensure the check is **read-only** (no OS-level locks, per requirements) and fails fast before creating any worker processes or touching progress files.
- Make the behavior configurable for tests (e.g. allow an environment variable or explicit flag to bypass the check in unit tests), but keep the default behavior strict in production.

4) Implement controlled daily reset command with archival behavior
- In `parallel_orchestrator.py` (or a small CLI wrapper if that’s where CLI parsing lives), add a **`--reset-day`** command/flag.
  - On invocation, the command should:
    - Locate the current progress CSV (respecting existing config from Task 19).
    - Compute an archive filename: `parallel_progress_YYYYMMDD.csv` based on **current local date** or a configurable timezone; document the choice and keep it consistent.
      - If a file with that name already exists, either:
        - Append a suffix such as `_1`, `_2`, etc., or
        - Fail with a clear error; pick one strategy and document it.
    - Move/rename the current progress file to the archive filename (not copy+delete; use atomic rename where possible).
    - Create a **fresh progress CSV** initialized with the correct header and any required initial state for a new day (e.g. pending jobs seeded from the scheduler, if that is part of reset semantics).
  - Never delete the progress file outright; the reset command must only archive and recreate.
- Implement reset logic in a dedicated function (e.g. `reset_day(progress_path, archive_dir=None)`), which can be called from CLI parsing and unit tests.
- Consider concurrency: ensure the reset operation is performed when no orchestrator workers are running; if needed, add a defensive check that refuses to reset when an orchestrator process is currently detected (re-use the process detection logic).

5) Update progress handling and `claim_next_job()` for defense in depth
- In `progress_tracker.py`, update `claim_next_job()` (introduced in Task 19) to enforce the same **per-account daily limit** in addition to seeding-time checks.
  - Before returning a job for a given account, compute or reuse `success_count_by_account` so that jobs are skipped when `success_count >= max_posts_per_account_per_day`.
  - Decide on behavior when a job is skipped because of the limit (e.g. treat as permanently skipped with a specific status like `daily_limit_reached`, or simply not claim it and move on to the next row). Document this behavior and ensure it is consistent with reporting.
  - Avoid O(N²) scans over the CSV for large inputs: if feasible, maintain a cached `success_count_by_account` that can be refreshed when needed, or compute counts once per orchestrator run rather than per-claim.
- Ensure that both `seed_from_scheduler_state()` and `claim_next_job()` share the same limit logic and do not diverge over time (e.g. via a `_within_daily_limit(account, counts, max_per_day)` helper).

6) Documentation updates in CLAUDE.md
- Edit `CLAUDE.md` to include **strict operational rules** around progress tracking and resets:
  - Explicitly state: **NEVER delete the progress file manually.**
  - For starting a new operational day, always run the **`--reset-day`** command instead of deleting or editing progress CSVs by hand.
  - Include a short explanation of the per-account daily limit behavior so human operators understand why some jobs may remain unposted once the limit is hit.
  - Add example CLI invocations for:
    - Starting the orchestrator normally.
    - Running `--reset-day`.
- Keep language concise and imperative so it can be used as a system prompt or operator runbook.

7) General code quality and patterns
- Maintain consistency with patterns established in Task 19: structured logging, error handling, and CLI parsing.
- Add type hints and docstrings for new/changed functions, and keep them in sync with behavior.
- Ensure any new dependencies (e.g. `psutil`) are declared in the project’s dependency management (requirements file, Poetry, etc.) and are optional where appropriate.
- Where feasible, design new logic to be testable without real orchestrator processes or actual CSV files by abstracting filesystem and process listing behind small helpers that can be mocked.

**Test Strategy:**

1) Unit tests for per-account daily limits
- Create a temporary progress CSV with multiple accounts and a mix of `success`, `fail`, and `pending` rows.
- Test `_load_success_counts` (or equivalent) to ensure only successful posts are counted per account, and counts match expectations.
- Configure `max_posts_per_account_per_day = 1` and verify that `seed_from_scheduler_state()` only seeds accounts with `success_count < 1`.
- With `max_posts_per_account_per_day = 2`, simulate seeding multiple jobs for the same account in a single call and assert that in-memory counts prevent creating more than 2 total for that account.

2) Unit tests for `claim_next_job()` enforcement
- Seed a test progress CSV with:
  - An account already at the daily limit (based on existing `success` rows).
  - Another account below the limit.
- Call `claim_next_job()` repeatedly and assert that:
  - Jobs for the over-limit account are not claimed (either skipped or marked with `daily_limit_reached`, according to the chosen design).
  - Jobs for accounts under the limit are claimed and marked as such, and that repeated calls never exceed the per-account limit.
- Verify that performance is acceptable by running `claim_next_job()` over a CSV with hundreds or thousands of rows in tests (avoid quadratic behavior).

3) Tests for orchestrator startup safety check
- Implement the process-detection logic in a function that accepts a list of mock process descriptors to enable pure unit testing.
- Provide fake process lists including:
  - Only the current process (should not block startup).
  - Another process whose command line clearly indicates it is an orchestrator (should block startup).
  - Unrelated Python processes (should not block startup, assuming matching criteria are specific enough).
- Assert that when a conflicting orchestrator is detected, the orchestrator entrypoint logs an appropriate error and exits with a non-zero code.

4) Tests for `--reset-day` archival behavior
- Use a temporary directory to host a fake progress CSV file with a known name and simple contents.
- Invoke the reset function directly (e.g. `reset_day(path)`):
  - Assert that the original file is no longer present and an archive file `parallel_progress_YYYYMMDD.csv` exists with identical contents.
  - Assert that a new progress CSV is created with the correct header and no historical rows.
- Test the behavior when an archive for the current date already exists:
  - If the design appends a numeric suffix, verify the new name (e.g. `parallel_progress_YYYYMMDD_1.csv`).
  - If the design is to fail, assert that an appropriate exception or error code is produced.
- Add a test ensuring reset refuses to run (or logs a strong warning) if the process-detection logic indicates an orchestrator is currently running.

5) Integration tests for end-to-end posting control
- With a small test CSV of jobs for multiple accounts, run the orchestrator in a test mode that uses a mock/posting stub instead of real devices.
- Set `max_posts_per_account_per_day = 1` and verify after a full run that:
  - No account has more than one `success` row in the progress CSV.
  - Jobs beyond the limit remain unposted or are marked according to the chosen policy.
- Repeat with `max_posts_per_account_per_day = 2` to ensure the system respects higher limits as well.

6) Documentation verification
- Add a test (or CI check) that ensures `CLAUDE.md` contains the key phrases: `NEVER delete progress file` and `--reset-day` (e.g. a simple text search in a docs-checking script).
- Optionally include a human-reviewed checklist item during code review to confirm that examples and instructions in `CLAUDE.md` match actual CLI flags and behavior.

## Subtasks

### 20.1. Add configurable per-account daily posting limit to parallel_config.py

**Status:** pending  
**Dependencies:** None  

Introduce a unified max_posts_per_account_per_day configuration entry in parallel_config.py that can be used by both progress_tracker.py and parallel_orchestrator.py without circular imports.

**Details:**

Add max_posts_per_account_per_day field to ParallelConfig dataclass in parallel_config.py with default value of 1. Implement validation to allow only integer values 1-4 with clear error on invalid values. Update get_config() to accept this parameter. The config should be passable via function parameters to seed_from_scheduler_state() and claim_next_job() to avoid global state imports. Add a _validate_daily_limit() helper that raises ValueError for out-of-range values. Update print_config() to display the limit setting. Ensure the default is a single source of truth that tests can override.

### 20.2. Enhance seed_from_scheduler_state() with configurable per-account limits and success counting

**Status:** pending  
**Dependencies:** 20.1  

Extend progress_tracker.py's seed_from_scheduler_state() to count successful posts per account from the progress CSV and filter accounts that have reached their daily limit, using the configurable max_posts_per_account_per_day parameter.

**Details:**

In progress_tracker.py: 1) Add _load_success_counts(progress_path) -> Dict[str,int] helper that iterates through CSV rows and counts STATUS_SUCCESS entries per account using a streaming reader to avoid memory issues. 2) Modify seed_from_scheduler_state() signature to accept max_posts_per_day: int = 1 parameter. 3) Replace the current hardcoded '1 post per account' logic with dynamic limit checking: compute success_count_by_account, filter available_accounts where count < max_posts_per_day, and maintain in-memory counts during seeding to prevent exceeding limit within a single seeding pass. 4) Add _within_daily_limit(account, counts, max_per_day) -> bool helper to share limit logic between seeding and claiming. 5) Ensure atomic file I/O is preserved - the existing temp file + rename pattern already handles this. Add clear docstrings documenting the behavior.

### 20.3. Add orchestrator startup guard to detect duplicate running orchestrators

**Status:** pending  
**Dependencies:** None  

Add a process detection check at startup in parallel_orchestrator.py that prevents running multiple orchestrator instances simultaneously, using subprocess-based approach to avoid adding psutil dependency.

**Details:**

In parallel_orchestrator.py: 1) Add _check_duplicate_orchestrator() -> Tuple[bool, str] function that uses subprocess to check for other Python processes running parallel_orchestrator.py. On Windows: use 'wmic process where "name='python.exe'" get processid,commandline' or 'tasklist /v'. On Unix: use 'ps aux | grep parallel_orchestrator'. 2) Filter out current process by comparing PIDs (os.getpid()). 3) Match by command line containing 'parallel_orchestrator' to identify orchestrator processes. 4) Call this check at the very start of run_parallel_posting() before any cleanup or worker spawning. 5) If another orchestrator is detected, log a clear error message with the detected PID and exit with sys.exit(1). 6) Add BYPASS_ORCHESTRATOR_CHECK environment variable that tests can set to skip the check. 7) Keep the check read-only (no OS-level locks as specified in requirements). Add to main() CLI as well.

### 20.4. Implement --reset-day command with progress file archival

**Status:** pending  
**Dependencies:** 20.3  

Add a --reset-day CLI flag to parallel_orchestrator.py that archives the current progress CSV to a dated filename and creates a fresh progress file, with safety checks to prevent reset while workers are running.

**Details:**

In parallel_orchestrator.py: 1) Add reset_day(progress_path: str, archive_dir: str = None) -> str function that: a) Computes archive filename as parallel_progress_YYYYMMDD.csv using local date; b) If archive file exists, append _1, _2, etc. suffix; c) Uses shutil.move() for atomic rename to archive; d) Creates fresh progress CSV with correct headers only. 2) Before reset, call _check_duplicate_orchestrator() to refuse reset if any orchestrator is running - reuse the detection logic from subtask 3. 3) Add --reset-day flag to argparse in main(). 4) When invoked, check no orchestrator running, perform reset, log archive path. 5) Document timezone assumption (local time) in docstring. 6) Return the archive filename for logging/testing. Handle case where progress file doesn't exist - just create empty one.

### 20.5. Update claim_next_job() for defense-in-depth limit enforcement and update CLAUDE.md documentation

**Status:** pending  
**Dependencies:** 20.1, 20.2  

Add per-account daily limit enforcement to claim_next_job() as defense-in-depth against seeding-time limit bypass, and update CLAUDE.md with operational rules for the new features.

**Details:**

In progress_tracker.py: 1) Modify claim_next_job() signature to accept max_posts_per_day: int = 1 parameter. 2) Within _claim_operation, compute success_count_by_account once at the start using the same counting logic as _load_success_counts. 3) When iterating pending jobs, add check: if success count for job's account >= max_posts_per_day, skip the job (log at debug level 'Skipping job X - account Y at daily limit'). 4) Reuse _within_daily_limit() helper from subtask 2 to ensure consistent logic. 5) Avoid O(N^2) by computing counts once before the loop. In CLAUDE.md: Add new section '## Parallel Posting Daily Limits' documenting: a) NEVER delete progress file manually - always use --reset-day; b) Per-account daily limit behavior and how to change the limit; c) Example CLI invocations for starting orchestrator and running --reset-day; d) Explain jobs may remain unposted when account limits are hit.
