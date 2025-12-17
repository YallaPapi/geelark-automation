# Task ID: 9

**Title:** Implement main loop, error handling, and structured logging

**Status:** done

**Dependencies:** 2 ✓, 5 ✓, 7 ✓

**Priority:** high

**Description:** Create the main entrypoint that iterates over CSV rows, invokes the posting orchestrator per job, and writes structured logs with status, timestamp, and errors.

**Details:**

Implementation details:
- In `main.py`, implement:
  - `load_config()`.
  - Initialize `GeelarkDeviceController`, `ClaudeNavigator`, and optionally `CaptchaSolver`.
  - Load jobs via `read_jobs(config.input_csv_path, config.video_root_dir)`.
  - For each job:
    - Call `run_post_job` inside a `try/except` block.
    - On success, call `append_log_row(..., status="success")`.
    - On failure, log `status="fail"` with the exception message.
- Use Python `logging` module with JSON-ish log format (e.g. `%(asctime)s %(levelname)s %(message)s`) and include job identifiers.
- Allow CLI flags/env for:
  - `--mvp` (single job from CSV).
  - `--max-jobs` to limit for testing.
- Pseudo-code:
```python
def main():
    config = load_config()
    controller = AdbGeelarkDeviceController(mapping=load_account_device_mapping())
    navigator = ClaudeNavigator(api_key=config.anthropic_api_key)
    jobs = read_jobs(config.input_csv_path, config.video_root_dir)

    for i, job in enumerate(jobs):
        try:
            run_post_job(job, config, controller, navigator)
            append_log_row(config.output_log_csv_path, job.account_name, job.video_path, "success")
        except Exception as e:
            append_log_row(config.output_log_csv_path, job.account_name, job.video_path, "fail", str(e))
```
- Ensure that an exception in one job does not terminate the loop; always continue to next row.
- Optionally, add a small random delay between jobs to reduce pattern-like behavior and mitigate rate limits.

**Test Strategy:**

- Use a mock controller and navigator to simulate successful and failing jobs; verify that the main loop continues after failures and that the log CSV contains correct rows.
- Run end-to-end in a test environment with 2–3 dummy jobs, visually inspect logs and confirm that timestamps and statuses are correct.
- Intentionally raise an exception inside `run_post_job` for one job and confirm that others are still processed.
