# Prompt 9 – Add campaign-aware, worker-aware logging

> Logging currently lacks clear campaign context and worker identity, making debugging hard. There is also a missing `--campaign-name` argument when spawning workers.
>
> Tasks:
> - Enumerate all logger initializations and `logging.basicConfig` calls in `parallel_orchestrator.py` and `parallel_worker.py`.
> - Confirm whether the worker command line includes campaign or context (it should add `--campaign-name` for logging and metrics).
> - Design a logging format that always includes:
>   - Campaign name or "legacy".
>   - Worker ID.
>   - PID.
> - Propose minimal changes to:
>   - Add a `--campaign-name` CLI arg to `parallel_worker.py`.
>   - Pass `ctx.campaign_name` from the orchestrator when spawning workers.
>   - Reconfigure loggers so that errors clearly identify which campaign/worker they belong to.
>
> Output:
> - A code snippet showing the updated worker spawn command with `--campaign-name`.
> - A recommended logging format string.
> - A short list of high-value log statements to add (e.g., when a worker claims a job, starts Appium, posts successfully, marks job failed, or exits).
