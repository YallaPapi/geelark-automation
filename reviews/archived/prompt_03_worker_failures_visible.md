# Prompt 3 – Make worker subprocess failures visible

> You are reviewing how `parallel_orchestrator.py` spawns and supervises `parallel_worker.py` subprocesses. The current bug: workers appear to start, progress CSV shows jobs "claimed", but no real work happens, and the orchestrator exits silently while Appium servers remain.
>
> Tasks:
> - Locate the function responsible for starting worker processes (e.g., `start_worker_process` in `parallel_orchestrator.py`).
> - Show:
>   - How the `cmd` array for `subprocess.Popen` is built (arguments, environment, working directory).
>   - Whether `stdout`/`stderr` from workers are captured, logged, or fully discarded.
>   - Whether the orchestrator periodically polls worker process `returncode` or only waits on high-level results.
> - Identify any missing error checks where worker processes can crash immediately (bad CLI args, import failure, TikTok-only code) without the orchestrator noticing.
>
> Output:
> - A description of the existing worker supervision model.
> - Specific code locations where you would:
>   - Add logging of worker command line and PID.
>   - Capture/redirect worker stderr into a per-worker log file.
>   - Detect and log when a worker exits with non-zero status while jobs remain "claimed".
> - One concrete design for a minimal "worker heartbeat" or "last-seen timestamp" mechanism using the existing CSV (or an auxiliary file) to distinguish "claimed but alive" vs "claimed by dead worker".
