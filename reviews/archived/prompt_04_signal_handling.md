# Prompt 4 – Audit signal handling and shutdown semantics

> The system has `shutdown_requested` flags and signal handlers in `parallel_worker.py`. `parallel_orchestrator.py` performs cleanup including stopping phones and Appium. The symptoms: the orchestrator exits while Appium servers keep running and jobs stay "claimed".
>
> Tasks:
> - List all signal handlers and shutdown paths in:
>   - `parallel_worker.py` (e.g., `setup_signal_handlers`, `shutdown_requested` checks).
>   - `parallel_orchestrator.py` (any signal handling or try/finally around the main run loop).
> - Identify where cleanup of Appium servers and Geelark phones is triggered (`full_cleanup`, `stop_all_phones`, `AppiumServerManager.stop_all` etc.).
> - Determine whether workers receive shutdown signals before the orchestrator tears down shared infrastructure, and whether they can be left mid-job.
> - Check if there are code paths where:
>   - The orchestrator exits due to an error and skips `full_cleanup`, or
>   - `full_cleanup` runs, but does not kill Appium processes started by workers.
>
> Output:
> - A table of "signal → handler → side effects" for orchestrator and workers.
> - Concrete recommendations to ensure:
>   - Orchestrator will not exit until all worker processes have either finished, been signaled, and confirmed terminated.
>   - Appium servers and Geelark phones are stopped **only** after workers are down, and only for this orchestrator session.
>   - Shutdown always logs a clear summary (e.g., "Stopped N workers, M Appium servers, K phones").
