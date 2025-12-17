# Prompt 4 – Ensure device / UI dump behavior matches old Instagram assumptions

> You are comparing `device_connection.py` (and any UI-dump/screenshot helpers) between `c260362` and `HEAD`.
>
> Goal: Make sure that the Instagram navigation code still receives UI dumps and screenshots in a format that matches what the old, working logic expects.
>
> Tasks:
> 1. Identify changes between `c260362` and `HEAD` in:
>    - How UI elements are retrieved (methods, filters, attributes kept or dropped).
>    - How screenshots are captured (resolution, rotation, timing).
>    - Any new helper functions introduced to support TikTok that are now also used by Instagram.
> 2. For each change, analyze whether it could:
>    - Hide or rename the `+` button from the IG analyzer's view.
>    - Change coordinates/centers in a way that breaks tap execution.
>    - Reduce waits/timeouts so the UI isn't fully loaded before inspection.
>
> Output:
> - A bullet list of changes in UI dumping / screenshot behavior that may break IG navigation.
> - A proposed patch or set of rules like:
>   - "For Instagram, use the old `get_ui_tree()` behavior from `c260362` unchanged."
>   - "TikTok may use the new behavior, but it must be gated by a `platform == 'tiktok'` condition."
