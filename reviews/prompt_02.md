# Prompt 2 – Restore Instagram prompt and navigation while keeping TikTok

> You are refactoring the navigation logic to restore the **previously working** Instagram behavior from commit `c260362`, without discarding TikTok support added later.
>
> Inputs:
> - The diff of `claude_analyzer.py` and `post_reel_smart.py` between `c260362` and `HEAD`.
>
> Goal: Make Instagram navigation and posting behave exactly as at `c260362`, while leaving TikTok functionality intact and clearly separated.
>
> Tasks:
> 1. In `claude_analyzer.py`:
>    - Extract the Instagram-specific prompt / instructions that existed at `c260362` (for recognizing the `+` button, home feed, reels UI, etc.).
>    - Compare with the current prompt.
>    - Propose a refactor that:
>      - Restores the **IG prompt text and action schema** from `c260362` for Instagram runs.
>      - Introduces a separate TikTok prompt if needed, instead of a single merged one that weakens Instagram behavior.
> 2. In `post_reel_smart.py` (or equivalent IG poster):
>    - Ensure the IG poster still:
>      - Dumps UI elements in the same structure as at `c260362`.
>      - Calls the analyzer with the same schema.
>      - Interprets returned actions in the same way (tap indices, swipe directions, completion detection).
>    - If TikTok-related abstractions changed the IG loop or stop conditions, propose code that restores the `c260362` IG flow while keeping TikTok logic in a **separate code path or subclass**.
>
> Output:
> - A concrete patch (or pseudocode diff) to:
>   - Reintroduce an `IG_UI_PROMPT` that matches `c260362`.
>   - Add a `TIKTOK_UI_PROMPT` if needed.
>   - Dispatch between them based on platform/campaign, without altering the IG path that used to work.
> - Explicit notes on what must be identical to `c260362` for Instagram (prompt text, element schema, action names).
