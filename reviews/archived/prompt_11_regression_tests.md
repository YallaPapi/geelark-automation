# Prompt 11 – Design regression tests for campaign orchestration

> The campaign system has multiple moving parts: `PostingContext`, campaign-specific progress files, TikTok integration, and new conflict detection. To prevent future regressions like "orchestrator exits silently; jobs stuck as claimed," you need automated checks.
>
> Tasks:
> - Using the existing Task IDs and test snippets in the XML (e.g., Task 60/61 test strategies), extract all current manual/CLI tests related to campaign mode.
> - Propose a minimal automated test suite (can be `pytest` or simple Python scripts) that validates:
>   - `--campaign X --status`, `--reset-day`, `--retry-all-failed`, `--seed-only`, and `--run` all operate on the campaign's progress file and accounts.
>   - Multiple worker processes can run in parallel without leaving jobs stuck in `claimed`.
>   - Stopping the orchestrator yields no orphaned Appium servers and leaves no jobs forever `claimed`.
>
> Output:
> - A list of 5–8 concrete test cases with: command to run, expected observable behavior, and files/processes to assert on.
> - Suggestions for a small "orchestrator harness" that can:
>   - Spawn the orchestrator with a test campaign.
>   - Wait for N seconds.
>   - Inspect progress CSV, worker PIDs, and Appium ports.
>   - Terminate everything and assert invariants.
