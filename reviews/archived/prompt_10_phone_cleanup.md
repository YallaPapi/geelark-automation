# Prompt 10 – Make phone cleanup campaign-scoped and session-scoped

> `stop_all_phones` currently iterates over **all** Geelark phones and stops any with status 1, which is unsafe when multiple campaigns or VAs are running. The new design should only stop phones started by this orchestrator, and optionally support a `--stop-campaign-phones` flag.
>
> Tasks:
> - Examine `stop_all_phones`, `full_cleanup`, and any Geelark client usage (`GeelarkClient`) in `parallel_orchestrator.py`.
> - Identify where phones are started for a campaign and how they are associated (if at all) with worker IDs or campaigns.
> - Design a mechanism to track "phones started by this orchestrator session" (e.g., an in-memory `set` plus a persisted session file).
>
> Output:
> - A proposal for:
>   - `start_session_phone(phone_name)` that records phone ownership.
>   - `stop_session_phones()` that only stops phones in the recorded set.
>   - A new `--stop-campaign-phones` CLI mode that uses `ctx.campaign_name` in logs and only touches campaign phones.
> - A set of invariants ensuring that `--stop-all` is clearly documented as dangerous and logs all phones it stops.
