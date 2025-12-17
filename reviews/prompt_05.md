# Prompt 5 – Isolate and, if needed, partially revert only the IG navigation while keeping TikTok

> You are designing a **minimal** code change that restores Instagram posting to the known-good state of `c260362`, while preserving TikTok support added later.
>
> Inputs:
> - Results of Prompts 1–4 (list of IG-breaking changes and their locations).
>
> Goal: Propose the smallest possible set of code edits that:
> - Makes Instagram posting behave as at `c260362`.
> - Leaves TikTok code present and compilable.
> - Keeps shared utilities platform-agnostic, but does not force Instagram to adopt TikTok-style assumptions.
>
> Tasks:
> 1. Identify the **core IG navigation cluster** (functions/methods) that should be reverted to `c260362` behavior:
>    - In the analyzer prompt and action interpretation.
>    - In the IG poster class.
>    - In device/UI dump helpers, if needed.
> 2. For each such function, decide whether to:
>    - Fully restore the `c260362` version.
>    - Introduce a versioned/conditional path (e.g., `if platform == 'instagram': use_old_ig_path()`).
> 3. Ensure TikTok code continues to compile and run by:
>    - Keeping TikTok-specific prompts and posters in their own modules.
>    - Using explicit platform checks to select IG vs TikTok behavior.
>
> Output:
> - A high-level patch plan:
>   - "In file X, function Y: restore `c260362` implementation."
>   - "In file Z: wrap new generic logic in `if platform == 'tiktok'`."
> - If possible, a concrete diff or pseudocode showing how to:
>   - Restore IG-specific logic.
>   - Keep TikTok paths separate and intact.
