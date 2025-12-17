# Prompt 6 – Add a quick "IG navigation debug mode"

> You are adding a debug mode that helps inspect the Instagram navigation loop without actually posting.
>
> Goal: Introduce a mode (e.g., CLI flag or environment variable) where the IG poster runs its navigation loop but only logs the actions it *would* take, instead of tapping/swiping for real. This will help validate that the AI sees and chooses the `+` button.
>
> Tasks:
> 1. In the IG poster class:
>    - Add a `debug_actions_only: bool` flag (default False).
>    - When `True`, still run the full loop (UI dump → analyze → action selection) but:
>      - Log each chosen action and target element text/bounds.
>      - Skip the actual tap/swipe/type calls.
> 2. In the worker or a small CLI wrapper:
>    - Add a way to turn on this flag for a single job or test run.
>
> Output:
> - A patch or pseudocode for adding `debug_actions_only` and its logging.
> - Example log lines that show: step number, chosen action, element text/description, and why this lets you verify that the bot can find the `+` button again.
