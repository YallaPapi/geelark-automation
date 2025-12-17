# Prompt 10 - End-to-End TikTok Posting Test Plan

**Goal:** Use the new logs/screenshots + test command to verify behavior and generate an iterative debug plan.

---

After applying the previous changes, you now want to validate TikTok posting end-to-end and refine the system until it reaches reliability similar to Instagram.

## Context
- Test accounts (TikTok): `glowingscarlets`, `crookedwafflezing`.
- TikTok campaign config: `campaigns/tiktok/campaign.json` (contains `"platform": "tiktok"`).
- Test command:
  ```bash
  python parallel_orchestrator.py --campaign tiktok --workers 1 --run
  ```
- `PostResult` includes:
  - `success`, `error`, `error_type`, `error_category`, `retryable`, `platform`, `account`, `duration_seconds`, and `screenshot_path`.
- TikTok poster now:
  - Captures screenshots on failure.
  - Logs detailed navigation steps and Claude actions.
  - Uses a refined `TIKTOK_NAVIGATION_PROMPT`.

## Task
1. Propose an **iterative test plan** (in 3-5 steps) to validate TikTok posting, including:
   - Running the TikTok campaign with 1 worker and a single test account.
   - Inspecting logs, screenshots, and UI dumps for failed posts.
   - Identifying recurring failure patterns (e.g., stuck on caption field, mis-tapping Upload vs Record, not detecting post confirmation).
2. For each recurring failure pattern, suggest targeted prompt or logic tweaks *within* `posters/tiktok_poster.py` that can be applied in subsequent iterations, using the same style as previous prompts.
3. Provide clear "success criteria" for declaring TikTok posting production-ready (e.g., X consecutive successful posts across both test accounts with no max-steps failures).

## Output Format
- Section 1: "Test plan" - numbered list.
- Section 2: "How to interpret logs & screenshots" - bullet list.
- Section 3: "Iteration criteria" - bullet list of readiness thresholds.
