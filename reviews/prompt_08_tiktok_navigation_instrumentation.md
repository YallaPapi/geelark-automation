# Prompt 8 - Instrument TikTok Navigation Loop for Debugging

**Goal:** Add cheap debug hooks so you can see, step-by-step, the UI state, Claude's JSON actions, and why it never reaches "done".

---

You are now focused on making the TikTok navigation loop debuggable so you can see exactly why Claude keeps looping until `max_steps`. You have already aligned screenshot handling with Instagram.

## Context
- `TikTokPoster.post()` currently:
  - Resets state flags (`_video_uploaded`, `_caption_entered`, `_post_clicked`).
  - Uploads the video, restarts the TikTok app, optionally humanizes behavior, then enters a loop:
    - Dumps UI elements via `_dump_ui()` / `self._ui_controller.dump_ui()`.
    - Calls a method like `_analyze_ui(elements, caption)` which uses `TIKTOK_NAVIGATION_PROMPT` and Claude's API to produce a JSON action (`action`, `element_index`, `text`, `video_selected`, `caption_entered`, `post_clicked`, etc.).
    - Calls `_execute_action(action, elements, caption)` to perform taps, taps+type, scrolls, back, home, etc.
    - Repeats up to `max_steps` before returning a failure `PostResult`.
- Logging in `TikTokPoster` is currently minimal: some `print()` for steps and actions, but not a full trace.

## Task
1. Enhance instrumentation inside `TikTokPoster.post()` and related helpers *without* changing external behavior, focusing on:
   - At each loop iteration, log:
     - Step number.
     - Current values of `_video_uploaded`, `_caption_entered`, `_post_clicked`.
     - A compact summary of the first N UI elements (id/text/desc/clickable).
     - The raw Claude JSON action returned by `_analyze_ui()`.
   - Optionally, save a UI dump snapshot (e.g., JSON or text) every K steps (e.g., every 5 steps) to a file path you log, to inspect later.
2. Make sure the additional logs are:
   - Consistent with existing print/logging style in `TikTokPoster` and `post_reel_smart.py`.
   - Guarded so they do not crash the process if logging fails (wrap file I/O in try/except).
3. Write the **concrete code changes** in `posters/tiktok_poster.py` to:
   - Extend the main loop in `post()` with detailed debug prints.
   - Optionally add a helper like `_debug_dump_ui(self, step: int, elements: List[Dict]) -> None` to persist periodic UI snapshots.

## Constraints
- No changes to public APIs or external behavior.
- Keep log volume reasonable; you can limit the number of elements printed per step and only persist snapshots every K steps.

## Output Format
- Brief explanation of the logging strategy.
- Unified diff for `posters/tiktok_poster.py` showing:
  - New helper(s) if any.
  - Enhanced logging inside the navigation loop.
