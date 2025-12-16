# Prompt 7 - Align TikTok Screenshot Handling with Instagram

**Goal:** Port the Instagram screenshot/failure-analysis pattern into `TikTokPoster` so failures always have screenshots and `PostResult.screenshot_path` set.

---

You are improving observability for TikTok posting in a multi-platform poster architecture. You have already run the "TikTok Poster Feature Debugger" prompt and understand both the Instagram and TikTok flows.

## Context
- `post_reel_smart.py` has a working pattern for failure handling on Instagram:
  - Capturing screenshots when posting fails.
  - Storing `last_error_type`, `last_error_message`, and `last_screenshot_path` on the underlying poster object.
  - A helper `analyze_failure_screenshot()` that uses Claude Vision to explain what went wrong, based on a screenshot and the last known UI state.
- `InstagramPoster` in `posters/instagram_poster.py` exposes error information via the `PostResult` dataclass, including `screenshot_path` passed through from `SmartInstagramPoster`.
- `TikTokPoster` in `posters/tiktok_poster.py` already defines:
  - `self._last_error_type`, `self._last_error_message`, `self._last_screenshot_path`.
  - A Claude-driven navigation loop inside `post()` that returns `PostResult` on max steps, detected error states, or exceptions.
- Currently, TikTok code does **not** reliably:
  - Capture a screenshot on failure.
  - Update `self._last_screenshot_path`.
  - Attach `screenshot_path` to the returned `PostResult`.

## Task
1. Design a **minimal, consistent** screenshot-capture strategy for TikTok, aligned with the Instagram implementation, using only components visible in the digest. Specifically:
   - Identify where in `TikTokPoster.post()` to call a new helper such as `_capture_failure_screenshot(reason: str)`.
     - At least:
       - When `max_steps` is exceeded.
       - When `_detect_error_state()` returns an error.
       - When an unexpected exception is caught.
   - Define what the helper should do using existing building blocks (e.g., `self._ui_controller` and/or `self._conn`):
     - Take a screenshot of the device.
     - Save it to a consistent path (e.g., under an `error_screenshots` directory, including platform, account, and timestamp).
     - Update `self._last_screenshot_path` with the saved file path.
2. Propose any new or updated methods in `TikTokPoster` that are idiomatic for this repo, for example:
   - `def _capture_failure_screenshot(self, reason: str) -> Optional[str]: ...`
   - Optionally, a lightweight `_analyze_failure_screenshot()` that mirrors the Instagram approach but tailored for TikTok and the existing Claude client; keep it simple at first.
3. Write the **exact code patches** (Python) needed to:
   - Add the helper function(s) into `posters/tiktok_poster.py`.
   - Invoke them from:
     - The `max_steps` early-return path.
     - The error detection branch where `_detect_error_state(elements)` finds an error.
     - The generic exception handler in `post()`.
   - Ensure each failing `PostResult` includes `screenshot_path=self._last_screenshot_path`.

## Constraints
- Do not change the signature of `BasePoster` or `PostResult`.
- Do not modify any Instagram-related files.
- Follow existing logging / `print()` style and naming conventions used in `TikTokPoster`.

## Output Format
- Short rationale: 3-5 bullet points describing the design.
- Then unified diff-style patches (`diff` blocks) for `posters/tiktok_poster.py` only.
- Use real function and variable names found in the digest (no pseudocode).
