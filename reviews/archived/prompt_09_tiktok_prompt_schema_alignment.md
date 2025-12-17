# Prompt 9 - Align TikTok Claude Prompt, UI Format, and Action Schema

**Goal:** Fix the mismatch between `TIKTOK_NAVIGATION_PROMPT`, the UI formatting we send, and the JSON we expect back, so Claude stops looping.

---

Now that screenshot capture and instrumentation are in place, your goal is to make the TikTok Claude navigation loop converge reliably by aligning:
- The `TIKTOK_NAVIGATION_PROMPT` in `posters/tiktok_poster.py`.
- The UI text we pass to Claude via `_format_elements_for_claude()`.
- The JSON schema we expect from `_analyze_ui()` and process in `_execute_action()`.

## Context
- `TIKTOK_NAVIGATION_PROMPT` describes the TikTok posting flow and UI patterns and instructs Claude to output JSON with fields like:
  - `action` (e.g., `"tap"`, `"tap_and_type"`, `"scroll_down"`, `"scroll_up"`, `"back"`, `"home"`, `"open_tiktok"`, `"done"`).
  - `element_index` (index into the UI elements list).
  - `text` (text to type).
  - `reason` (for logging only).
  - `video_selected`, `caption_entered`, `post_clicked` (booleans).
- `_format_elements_for_claude()` builds a textual description of UI elements (id/text/desc/clickable/center).
- `_analyze_ui()` uses `TIKTOK_NAVIGATION_PROMPT` and includes state flags in the prompt (`_video_uploaded`, `_caption_entered`, `_post_clicked`, and a truncated caption).
- `_execute_action()` interprets the JSON action dictionary and uses `self._ui_controller` to perform the action, and also sets some state flags (e.g., `_caption_entered = True` after typing).
- Currently, tests show:
  - Claude often never returns the `"done"` action, or sets state flags in a way that does not match the loop's expectations, causing `max_steps` to be reached.

## Task
1. Carefully read `TIKTOK_NAVIGATION_PROMPT`, `_format_elements_for_claude()`, `_analyze_ui()`, and `_execute_action()`.
2. Identify all mismatches, including but not limited to:
   - Field names described in the prompt vs fields actually read in `_execute_action()`.
   - Assumptions about when `_video_uploaded`, `_caption_entered`, or `_post_clicked` become `True`.
   - Conditions for returning `"done"` based on visible UI text (e.g., "Uploading", "Posted", etc.) that may be missing or underspecified.
3. Rewrite `TIKTOK_NAVIGATION_PROMPT` so that it:
   - Uses explicit, numbered steps tailored to the **actual** TikTok flow reflected in the code.
   - Contains concrete examples of UI text patterns for:
     - Create button, Upload option, gallery thumbnails, Next buttons, caption field ("Describe your video" / "Add a description"), Post button, and post confirmation.
   - Clearly defines the exact JSON schema expected, including required and optional fields, and when to set each state flag.
   - Explicitly defines when to return `"done"` (for example, after tapping Post and detecting upload/posted confirmation or a transition away from the composer).
4. Adjust `_analyze_ui()` and `_execute_action()` as needed to:
   - Robustly parse the JSON produced by the new prompt.
   - Safely handle malformed responses by falling back to a conservative action (e.g., small scroll) rather than crashing.
   - Correctly update `self._video_uploaded`, `self._caption_entered`, and `self._post_clicked` based on either the action taken or the explicit `video_selected/caption_entered/post_clicked` flags in the response.

## Constraints
- Keep changes localized to `posters/tiktok_poster.py`.
- Preserve the `BasePoster` interface and the overall `post()` control flow.

## Output Format
- Revised `TIKTOK_NAVIGATION_PROMPT` as a multi-line Python string literal.
- Updated implementations for `_analyze_ui()` and `_execute_action()`.
- Provide the diff for `posters/tiktok_poster.py` only.
