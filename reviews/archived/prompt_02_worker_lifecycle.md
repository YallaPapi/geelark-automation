# Prompt 2 – Analyze worker lifecycle and job-claiming race conditions

> You are analyzing a multi-worker posting system that uses a CSV-based `ProgressTracker` with file locking, plus a `parallel_worker.py` worker process. The problem: jobs are marked as "claimed" but no real work happens, and no phones run.
>
> Focus files:
> - `parallel_worker.py`
> - `progress_tracker.py`
> - Any shared helper used by both (e.g., `ParallelConfig`, `WorkerConfig`).
>
> Tasks:
> - Trace the complete worker lifecycle in `parallel_worker.py`: from process start, through ADB/Appium setup, to claiming a job from `ProgressTracker` and marking it `claimed`, then to marking it `completed` or `failed`.
> - Identify exactly where in the code the status transitions `pending -> claimed -> completed/failed` are performed.
> - Determine if there is any path where:
>   - The job gets marked as `claimed` before the phone/Appium session is actually ready, and
>   - A failure in ADB/Appium setup or in `SmartInstagramPoster`/TikTok poster causes the worker to crash or bail out **without** resetting the job status from `claimed` back to a retryable state.
> - Check if there is any sleep/retry logic between claim and actual post; call out any race conditions or "claim too early" patterns.
>
> Output:
> - A bullet list of all places where `ProgressTracker` status is changed.
> - Any paths where jobs can be stuck indefinitely in `claimed`.
> - Proposed changes to defer claiming until after Appium is ready, or to add a "claim with lease timeout" / "auto-unclaim on worker crash" strategy.
