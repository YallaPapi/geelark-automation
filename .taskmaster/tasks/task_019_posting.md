# Task ID: 19

**Title:** Implement multi-process Appium worker orchestration with isolated servers and CSV-based progress tracking

**Status:** done

**Dependencies:** 1 ✓, 2 ✓, 3 ✓, 4 ✓, 5 ✓, 7 ✓, 9 ✓, 10 ✓

**Priority:** medium

**Description:** Design and implement a multi-worker posting system where each Python process manages its own Appium server, device, and job subset, coordinated by a simple orchestrator and CSV-based progress tracking to avoid duplicate posts.

**Details:**

Implementation outline:

1) Overall architecture and process model
- Introduce a new module (e.g. `parallel_orchestrator.py`) that is responsible for:
  - Spawning N worker processes using `multiprocessing.Process` or `subprocess` (not threads) for true isolation.
  - Assigning each worker a unique Appium configuration (Appium port, systemPort range, device mapping, and log paths).
  - Managing lifecycle: start all workers, monitor, and perform clean shutdown on SIGINT/SIGTERM.
- Each worker process will:
  - Start its own Appium server instance (local `appium` binary or programmatic Node call) on a unique port (4723, 4725, 4727, etc.), following best practice that each device has a dedicated Appium server and unique port.[1][3]
  - Use a unique `systemPort` (or narrow range) per worker for UiAutomator2 to avoid conflicts between parallel Android sessions.[3][6]
  - Initialize its own `GeelarkDeviceController` and posting flow stack (`ClaudeNavigator`, etc.) to reuse existing single-device logic from Task 7.

2) Port and systemPort allocation strategy
- Define a configuration structure (in `config.py` or a new `parallel_config.py`) mapping worker IDs to Appium ports and systemPort ranges, e.g.:
  - worker 0: appium_port=4723, system_port_start=8200, system_port_end=8209
  - worker 1: appium_port=4725, system_port_start=8210, system_port_end=8219
- When constructing desired capabilities for a worker’s Appium session, set:
  - `"udid"` or equivalent device ID for that worker’s Geelark device.
  - `"systemPort"` to a value in the allocated range for that worker.
- Enforce uniqueness at runtime (assert no two workers share the same appium_port or overlapping systemPort ranges) to follow Appium parallel execution best practices.[1][3]

3) Appium server lifecycle per worker
- Implement a helper in a dedicated module, e.g. `appium_server_manager.py`:
  - `start_appium_server(port: int, log_path: str, extra_args: list[str]) -> subprocess.Popen` that:
    - Spawns `appium` with `--port`, and for Android also passes any required UiAutomator2/Chromedriver arguments.
    - Redirects stdout/stderr to a per-worker log file for easier debugging, as recommended for parallel runs.[1]
    - Waits for health-check (HTTP call to `/status`) with timeout and retry before proceeding.
  - `stop_appium_server(proc: subprocess.Popen, timeout: float = 10.0)` that sends SIGTERM, then SIGKILL if necessary.
- In the worker entrypoint:
  - Start Appium.
  - Run the worker job-processing loop.
  - In a `try/finally`, always stop the Appium server and perform device cleanup.

4) Worker process design and job acquisition
- Implement a `worker_main(worker_id: int, config: Config, shared_state_paths: ...)` entry function that:
  - Sets up logging with worker-specific identifiers.
  - Starts Appium with that worker’s dedicated ports.
  - Enters a loop where it repeatedly:
    - Claims the next unprocessed job from a shared CSV-based tracker (see section 5).
    - Runs `run_post_job(job, config, controller, navigator)` from Task 7, reusing the existing single-job flow.
    - On success/failure, writes to both the existing output log CSV (Task 2, 9) and the progress tracker.
  - Terminates cleanly when there are no remaining unclaimed jobs.
- Ensure workers do not share Python objects in memory; they should communicate only via the filesystem (CSV files) or simple IPC if needed.

5) CSV-based shared progress tracking (no duplicate posts)
- Design a dedicated progress CSV (e.g. `progress.csv`) separate from the result log:
  - Columns: `job_id`, `account_name`, `video_path`, `status` (pending/claimed/success/fail/skip), `worker_id`, `timestamp`, `error`.
- Implement a small `progress_tracker.py` module with concurrency-safe operations based on file locking:
  - Use `fcntl.flock` (Unix) or `msvcrt.locking`/`portalocker` (cross-platform) to protect updates so that parallel workers cannot claim the same job simultaneously (a best-practice for shared resources in parallel execution).[1]
  - `claim_next_job(worker_id) -> Optional[PostJob]`:
    - Acquire an exclusive lock on `progress.csv`.
    - Load rows (in-memory or via streaming), find the first `status == "pending"` row.
    - Mark it as `claimed` with `worker_id` and timestamp, rewrite the file atomically (e.g. write to temp file then rename).
    - Release the lock and return the corresponding `PostJob`, or `None` if no pending jobs remain.
  - `update_job_status(job_id, status, worker_id, error=None)`:
    - Lock file, update the row, rewrite atomically, unlock.
- Provide a bootstrap utility that, at orchestrator startup, seeds `progress.csv` from the main input CSV if it does not exist, assigning `job_id` indices that remain stable across runs.

6) Orchestrator script to start/stop all workers
- Implement a CLI script (e.g. `python -m geelark_ig_bot.parallel_orchestrator`) that:
  - Loads `Config` using existing config mechanisms from Task 1 and compatible with Task 9.
  - Reads desired `num_workers` and per-worker device/Appium port mapping from configuration.
  - Initializes/validates the `progress.csv` file, ensuring all jobs are marked `pending` or appropriately resumed from a previous run.
  - Starts worker processes with `multiprocessing.Process(target=worker_main, args=(...))` or by calling the module’s CLI via `subprocess.Popen`.
  - Monitors children: optionally capture exit codes and restart on transient failure, or log and shut down gracefully.
  - Handles signals:
    - On SIGINT/SIGTERM, set a shared shutdown flag (e.g. `multiprocessing.Event` or a `shutdown` file), wait for workers to finish their current job, then terminate any stuck processes.

7) Integration with existing posting logic
- Reuse existing modules:
  - Use Task 2’s `read_jobs` only in the orchestrator seeding step; workers should rely on `progress_tracker` for job acquisition.
  - Use Task 7’s `run_post_job` as the per-job worker function, passing the worker-specific `GeelarkDeviceController` and `ClaudeNavigator` instances.
  - Ensure proxy rotation (Task 5) and error-handling/logging (Task 9) continue to function as-is within each worker.
- Avoid global singletons where possible; instantiate controller/navigator inside each worker process to keep state isolated.

8) Clean shutdown, device cleanup, and fault tolerance
- Within each worker:
  - Track the current device session (driver) and ensure that on normal loop exit or exceptions, you:
    - Attempt to close the app session and release the device (following typical parallel execution guidance to avoid dangling sessions).[1][3]
    - Stop the Appium server via `stop_appium_server`.
  - Make all teardown operations idempotent so that repeated shutdown attempts (from orchestrator and OS) do not crash.
- Implement defensive behavior:
  - If Appium fails to start or health-check fails, mark the worker as failed, log the error, and exit with a non-zero code.
  - If a job fails due to Appium/device issues, mark job status as `fail` with error details in both progress and result logs.

9) Logging and observability
- Configure per-worker log files for:
  - Worker Python logs (info, warning, error) including job IDs and account names.
  - Appium server stdout/stderr.
- Include job IDs and worker IDs in all structured logs (Task 9) to simplify debugging parallel issues, as recommended for parallel test execution environments.[1]

10) Documentation and configuration
- Add documentation to `README` or internal docs:
  - How to configure the number of workers and mapping to devices.
  - Port and systemPort allocation strategy.
  - How progress tracking works and how to resume a partially completed run.
  - Operational notes: typical CPU/memory impact when running multiple Appium servers concurrently.[1][3]
- Expose the most important knobs via config: `num_workers`, `appium_start_cmd`, base Appium port, systemPort ranges, and log directory.

**Test Strategy:**

1) Unit tests for progress tracking
- Test `claim_next_job` and `update_job_status` sequentially:
  - Seed a temporary `progress.csv` with multiple pending jobs.
  - Verify that `claim_next_job` returns jobs in order and marks them as `claimed` with the correct `worker_id`.
  - Verify that `update_job_status` transitions rows to `success`, `fail`, or `skip` and persists changes.
- Simulate contention by spawning 2–3 lightweight Python processes in tests that concurrently call `claim_next_job` against the same file and assert that no `job_id` is returned more than once.

2) Unit tests for Appium server manager (where feasible with mocks)
- Mock `subprocess.Popen` and the HTTP health-check:
  - Ensure `start_appium_server` is called with the expected port and arguments.
  - Verify that failed health-checks raise a clear exception.
- Test `stop_appium_server` behavior when the process exits normally vs. hangs (ensure SIGKILL path is exercised).

3) Unit/integration tests for worker logic (with fakes/mocks)
- Use a fake `GeelarkDeviceController` and `ClaudeNavigator` that simulate successful postings without real devices.
- Run `worker_main` against a small `progress.csv` and confirm that:
  - All jobs transition from `pending` to `success`.
  - The existing result log CSV contains one row per job with the correct status.
  - The worker exits cleanly when no pending jobs remain.

4) Multi-process integration test (local)
- Start the orchestrator with 2–3 workers using the fake controller/navigator and a small input CSV (e.g. 10 jobs).
- Assert that:
  - All jobs are processed exactly once (no duplicates, no missing jobs) by inspecting `progress.csv`.
  - Work is distributed across workers (different `worker_id` values present).
  - Orchestrator exits with zero status and all worker processes have exited.

5) Signal handling and clean shutdown tests
- In an integration-style test, start the orchestrator with long-running fake jobs (each job sleeps a few seconds).
- Send SIGINT (or simulated shutdown signal) to the orchestrator process and assert that:
  - Workers finish or abort their current job, update job status appropriately (e.g. leave unstarted jobs as `pending`).
  - Appium server processes (mocked) receive `stop_appium_server` calls.

6) Real-device/Appium smoke test (manual or CI environment)
- Connect at least two Android devices (or Geelark cloud devices mapped via the controller) and configure two workers with distinct Appium ports and systemPorts.
- Start the orchestrator with a small CSV (e.g. 2–4 jobs) and visually confirm:
  - Two Appium servers run on the expected ports.
  - Each device is driven only by its assigned worker.
  - Posts are successfully created and logged once per job.
- Inspect logs to verify that no UiAutomator2/systemPort conflicts or session collisions occur, aligning with recommended Appium parallel execution patterns.[1][3][6]

7) Regression tests with existing single-worker flow
- Run a single-worker configuration and verify that behavior matches the existing Task 9/10 MVP: same success rate, logging format, and proxy rotation behavior.
- Confirm that enabling parallel mode does not require changes to the per-job posting logic (i.e. `run_post_job` remains unchanged aside from Appium config injection).

## Subtasks

### 19.1. Design parallel orchestration architecture and configuration for multi-process workers

**Status:** done  
**Dependencies:** None  

Define the overall architecture for multi-process Appium workers, including process model, per-worker isolation strategy, and configuration structures for devices, ports, and logging.

**Details:**

- Specify how the orchestrator module (e.g. `parallel_orchestrator.py`) will spawn and manage N worker processes using `multiprocessing.Process` or `subprocess`.
- Design a `ParallelConfig`/similar structure (in `config.py` or `parallel_config.py`) that maps worker IDs to: device identifier/UDID, Appium port, systemPort range, log directory paths, and any extra Appium args.
- Define how configuration is loaded from existing config (Task 1/9) and extended with parallel-specific fields like `num_workers`, `base_appium_port`, `system_port_block_size`.
- Document invariants (e.g. unique Appium ports, non-overlapping systemPort ranges, one device per worker) and how they will be validated at startup.
- Decide on basic IPC/shared-state mechanisms (CSV files, optional shutdown flag via file or `multiprocessing.Event`) and how workers discover shared paths (e.g. `progress_csv_path`, `results_csv_path`, `logs_dir`).

### 19.2. Implement Appium server manager and per-worker process entrypoint

**Status:** done  
**Dependencies:** 19.1  

Create the Appium server lifecycle utilities and the worker main function that owns a dedicated Appium server, device controller, and posting loop.

**Details:**

- Implement `appium_server_manager.py` with:
  - `start_appium_server(port: int, log_path: str, extra_args: list[str]) -> subprocess.Popen` that launches the `appium` binary with `--port` and other required arguments, redirects stdout/stderr to a per-worker log file, and performs `/status` health checks with retry and timeout.
  - `stop_appium_server(proc: subprocess.Popen, timeout: float = 10.0)` that sends SIGTERM and escalates to SIGKILL if the server does not exit in time.
- Implement `worker_main(worker_id: int, config: ParallelConfig, shared_paths: WorkerSharedPaths)` in a new worker module:
  - Initialize worker-specific logging (file and console) including worker ID in log records.
  - Resolve worker-specific device/Appium configuration (UDID, Appium port, systemPort range, log paths) from `ParallelConfig`.
  - Start the Appium server using `start_appium_server` and construct desired capabilities with unique `udid` and `systemPort` values within the worker’s allocated range.
  - Instantiate `GeelarkDeviceController`, `ClaudeNavigator`, and other dependencies, ensuring all state is local to the process.
  - Implement a guarded `try/finally` to guarantee teardown: close active driver session, perform device cleanup, and call `stop_appium_server` even on errors or external shutdown.
- Ensure no global singletons are shared across workers; all per-worker objects are created inside `worker_main`.

### 19.3. Build CSV-based progress tracker with file locking and seeding from input jobs

**Status:** done  
**Dependencies:** 19.1  

Implement a concurrency-safe CSV progress tracking module that coordinates job claiming and status updates across workers, and a bootstrap step to seed it from the main input CSV.

**Details:**

- Design the schema for `progress.csv` with at least columns: `job_id`, `account_name`, `video_path`, `caption` (if needed for reconstruction), `status`, `worker_id`, `timestamp`, `error`.
- Implement `progress_tracker.py` providing:
  - Cross-platform file-locking utilities (e.g. using `fcntl.flock` on Unix and `msvcrt`/`portalocker` on Windows) to guard read-modify-write cycles.
  - `claim_next_job(worker_id: int) -> Optional[PostJob]` that:
    - Acquires an exclusive lock on `progress.csv`.
    - Reads rows, finds the first `status == "pending"`, sets it to `"claimed"` with `worker_id` and timestamp.
    - Rewrites the CSV atomically via a temp file and rename, then releases the lock.
    - Returns a constructed `PostJob` (compatible with Task 2/7) or `None` if no pending jobs remain.
  - `update_job_status(job_id: int, status: str, worker_id: int, error: str | None = None)` that locks, updates the row, rewrites atomically, and unlocks.
- Implement a seeding/bootstrap utility (callable from the orchestrator) that:
  - Uses existing `read_jobs` (Task 2) to load jobs from the main input CSV when `progress.csv` does not exist.
  - Assigns stable `job_id`s, writes initial rows with `status="pending"`, and preserves any existing progress when resuming.
- Ensure functions are robust to partial files and can recover or fail clearly on CSV corruption.

### 19.4. Implement worker job-processing loop integrating posting logic and progress tracking

**Status:** done  
**Dependencies:** 19.2, 19.3  

Wire the worker loop to claim jobs from the progress tracker, run the existing posting flow, log outputs, and update job status with robust error handling and shutdown awareness.

**Details:**

- Inside `worker_main`, implement the main loop that:
  - Periodically checks a shutdown flag (e.g. `multiprocessing.Event` passed from orchestrator or a special "shutdown" file) to determine whether to stop after the current job.
  - Calls `claim_next_job(worker_id)` from `progress_tracker` and exits the loop when it returns `None` (no more pending jobs).
  - For each claimed job:
    - Ensures proxy rotation (Task 5) is invoked before posting, using existing network utilities.
    - Calls `run_post_job(job, controller, navigator, config)` from Task 7 within a `try/except` block.
    - On success, writes a row to the existing result log CSV via `append_log_row` (Task 2) and calls `update_job_status(job_id, "success", worker_id, error=None)`.
    - On exception, logs structured error information, writes a `status="fail"` row to the result log CSV, and calls `update_job_status(job_id, "fail", worker_id, error=str(exc))`.
  - Ensures that any Appium/device-specific failures are surfaced clearly and that repeated failures do not corrupt `progress.csv`.
- Include worker ID, job ID, and account name in all worker logs for observability consistent with Task 9.
- Make the loop resilient to transient tracker I/O errors (e.g. small retry on file-lock failures) while avoiding duplicate job processing.

### 19.5. Create orchestrator CLI to configure, launch, monitor, and gracefully shut down all workers

**Status:** done  
**Dependencies:** 19.1, 19.2, 19.3, 19.4  

Implement the top-level orchestrator script that initializes configuration and progress tracking, spawns worker processes, monitors their lifecycle, and handles clean shutdown and restarts.

**Details:**

- Implement a CLI entrypoint (e.g. `python -m geelark_ig_bot.parallel_orchestrator`) that:
  - Loads the base `Config` and parallel extensions (num workers, device/port mappings, log directories).
  - Validates the configuration invariants: unique Appium ports, non-overlapping systemPort ranges, valid device IDs, and accessible log directories.
  - Initializes or resumes `progress.csv` via the seeding utility, ensuring consistent `job_id`s and correct `pending`/`claimed`/`success`/`fail` states.
- Use `multiprocessing.Process` (or `subprocess.Popen` on the same module) to spawn one worker per configured device/worker ID, passing in the resolved `ParallelConfig` subset and shared paths.
- Implement monitoring logic that:
  - Tracks process handles, logs start/stop events with exit codes, and optionally restarts workers on transient failures according to a simple policy (e.g. limited restart count).
  - Periodically checks for overall completion (all jobs non-pending and all workers idle/exited).
- Implement signal handling for SIGINT/SIGTERM:
  - Set a shared shutdown flag or create a `shutdown` file that workers poll, allowing them to finish the current job and exit their loops.
  - After a grace period, terminate or kill any stuck worker processes and ensure Appium servers are torn down.
- Add basic documentation/comments describing how to run the orchestrator, configure workers and ports, and resume from partial runs; update README or internal docs accordingly.
