# Prompt 5 – Fix orchestrator conflict detection for campaigns

> The function `check_for_running_orchestrators` in `parallel_orchestrator.py` currently treats *any* `parallel_orchestrator.py --run` process as a conflict, blocking concurrent campaigns even if they use different progress files and accounts. The new design adds a `campaign_name` parameter.
>
> Tasks:
> - Locate `check_for_running_orchestrators` and confirm its current implementation and call sites, including how it's used with `PostingContext`.
> - Verify that the campaign-aware version:
>   - Treats orchestrators with the **same** campaign as conflicts.
>   - Allows multiple concurrent orchestrators when:
>     - They have different `campaign_name`, or
>     - They are in legacy mode and use different progress files/accounts.
> - Check if there are any callers still using the old (no-arg) version or still parsing `ps` output in a campaign-agnostic way.
>
> Output:
> - A before/after description of the conflict-detection logic.
> - A set of unit-level test cases (input: list of fake process command lines, current campaign context; output: conflict yes/no) to ensure you never regress this again.
> - A suggested log message format when a conflict is detected, including campaign name and PID/command of the existing orchestrator.
