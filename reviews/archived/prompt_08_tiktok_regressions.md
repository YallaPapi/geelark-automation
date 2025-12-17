# Prompt 8 – Isolate TikTok-specific regressions

> The system worked before TikTok support was added (around commit `aebf876`). The regression likely came from shared infrastructure changes made to support TikTok.
>
> Tasks:
> - Identify TikTok-related modules (e.g., TikTok poster class, new device control paths) and where they are wired into the worker pipeline (e.g., platform selection logic, `SmartInstagramPoster` vs TikTok poster).
> - Find any new imports or branches in `parallel_worker.py`, `parallel_orchestrator.py`, or `device_connection` that are TikTok-specific and could fail on environments that only expect Instagram.
> - Look for changes since the "pre-TikTok" state where shared components were modified rather than added in parallel (e.g., unified UI controller, shared ADB helpers, posting state machine).
>
> Output:
> - A list of TikTok-related changes that affect:
>   - Process startup (imports, environment requirements).
>   - Device/Appium initialization.
>   - Job posting loop and error handling.
> - Concrete recommendations to:
>   - Fail gracefully when TikTok-specific preconditions are not met (e.g., missing package, capabilities).
>   - Keep platform-specific failures from killing the whole worker/orchestrator.
>   - Optionally add a `platform` field to campaigns and use it to decide which poster to instantiate.
