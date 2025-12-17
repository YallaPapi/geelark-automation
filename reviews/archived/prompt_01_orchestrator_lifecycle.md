# Prompt 1 – Trace orchestrator lifecycle and exit conditions

> You are analyzing a Python parallel orchestrator that manages multiple worker subprocesses for Appium-based posting.
>
> Goal: Find all code paths in `parallel_orchestrator.py` that can cause the main process to exit early or skip actually running workers, especially in campaign mode. Focus on the `PostingContext` refactor and the `run_parallel_posting` entrypoint.
>
> Tasks:
> - Enumerate all branches in `main()` after argument parsing that lead to `sys.exit()` or an immediate return when `--run` is passed (with or without `--campaign`).
> - Show how `PostingContext` is constructed in campaign vs legacy mode, and how that context is passed into `run_parallel_posting`.
> - Map out, step by step, what happens when executing:
>   - `python parallel_orchestrator.py --campaign podcast --workers 5 --retry-all-failed --run`
>   - `python parallel_orchestrator.py --campaign podcast --workers 1 --run`
> - Identify any conditions where `run_parallel_posting` is never reached, is called with the wrong parameters, or returns prematurely without propagating errors.
> - Check the new `retry_cfg` / `RetryConfig` usage and confirm `results.run_parallel_posting(...)` error propagation is consistent.
>
> Output:
> - A short control-flow diagram (text) from `main()` to `run_parallel_posting` for campaign mode.
> - A list of specific lines/blocks that can cause early exit while still leaving workers/Appium started, if any.
> - Concrete suggestions for logging and guardrails (e.g., mandatory "orchestrator STARTED/FINISHED" log lines, CLI argument validations) to make silent exits impossible.
