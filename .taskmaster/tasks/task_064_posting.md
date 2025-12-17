# Task ID: 64

**Title:** Harden Claude Vision Prompts for Instagram Navigation Edge Cases in post_reel_smart.py

**Status:** pending

**Dependencies:** 7 ✓, 48 ✓, 49 ✓, 50 ✓, 51 ✓, 55 ✓

**Priority:** medium

**Description:** Update the Claude Vision prompt strategy in post_reel_smart.py so the navigation AI robustly recognizes and recovers from Meta Verified upsell popups, camera/media-selection dead ends, and ID verification loops during the Instagram Reel posting flow.

**Details:**

## Overview
Improve the robustness of the Instagram Reel posting flow by enhancing the Claude Vision prompt design and state-handling logic in `post_reel_smart.py`. The goal is to explicitly teach the AI about known failure UIs (Meta Verified popup, camera/media-selection traps, ID verification loops), add state-aware instructions, and introduce guardrails/fallbacks so these flows are detected early and escaped cleanly.

## Preparation & Analysis
1. **Review current Claude Vision integration**
   - Open `post_reel_smart.py` and locate:
     - The core class (likely `SmartInstagramPoster`) and the main navigation loop.
     - Any helper that builds Claude prompt text (e.g., `build_prompt`, `NAV_PROMPT`, or similar constants).
     - Call sites where screenshots are captured and sent to Claude, and how actions are interpreted.
   - Identify whether prompts are:
     - Single large system prompts reused across steps, or
     - Context-specific prompts (per phase: feed, camera, editor, share, etc.).
   - Note any existing descriptions of popups, login dialogs, or other Instagram UIs to follow the existing writing style.

2. **Catalog known failure modes and UI signatures**
   - From logs, screenshots, or prior incident reports (if available), capture for each case:
     - Key *visual cues* (icons, colors, layout) and *text fragments* that reliably appear.
     - Where in the flow it occurs (e.g., right after tapping “Next”, when opening camera, after tapping Share, etc.).
   - Define for each failure mode:
     1) **Meta Verified popup**
        - Typical features: "Meta Verified" header, price tag or subscription details, CTA buttons like **"Subscribe"**, **"Not now"**, **"X"** close icon.
        - Intended handling: **Always dismiss** immediately and return to the prior intended screen (tap close or "Not now"). Never subscribe.
     2) **Camera / media-selection / wrong-screen traps**
        - Cases where the AI:
          - Stays in **camera view** without selecting media.
          - Opens **gallery/media chooser** but never confirms selection.
          - Navigates to unrelated screens (DMs, profile, search) and gets stuck within the max step limit.
        - Intended handling:
          - Detect when we are not on any of the *allowed* target states for the current phase (e.g., not on feed, not on reel editor, not on share screen) and trigger **recovery navigation**.
     3) **ID verification loop**
        - Screens containing text like "Confirm your identity", "ID verification", "Upload ID", "We noticed unusual activity".
        - Often not resolvable programmatically within allowed time and should be treated as a **hard account-level failure**, not retried indefinitely.
        - Intended handling: Recognize this state quickly, tag as account-level verification required, and exit gracefully.

## Prompt Design Changes
3. **Refactor prompt structure for clarity and reuse**
   - Centralize vision prompt templates in clearly named constants or builder functions (if not already done), for example:
     - `BASE_VISION_SYSTEM_PROMPT`
     - `PROMPT_PHASE_FEED_NAV`, `PROMPT_PHASE_CAMERA_OR_GALLERY`, `PROMPT_PHASE_EDITOR_AND_SHARE`
   - Ensure prompts explicitly include:
     - High-level **objective** (e.g., "post this prepared reel successfully").
     - Allowed **action vocabulary** (tap, swipe, back, wait, etc.).
     - A concise **state model** (which core screens exist and what the AI should aim for in the current step).

4. **Add explicit instructions for Meta Verified popup handling**
   - In the shared system prompt (or a section reused in all phases), add clear rules:
     - Explain what the Meta Verified popup looks like: mention **"Meta Verified"**, subscription messaging, profile badges, and typical button labels such as **"Not now"**, **"Maybe later"**, **"X"**.
     - Directive: "If you see any Meta Verified or subscription upsell dialog, **do not subscribe**, **do not change account settings**, and **immediately dismiss it** by tapping the close or 'Not now' button, then continue with the original posting task."
   - Provide 1–2 concrete examples inside the prompt:
     - Example: "If a popup with title 'Meta Verified' appears with buttons 'Subscribe' and 'Not now', tap 'Not now'."
   - Ensure the result parser and action executor support taps at generic **top-right close icons** and labeled buttons, and that the prompt lists such actions as valid.

5. **Enhance prompts with robust state recognition**
   - Extend prompts to describe **canonical states** to recognize:
     - Home feed
     - Reel composer / editor
     - Share screen (caption, hashtags, cover)
     - Camera view (full-screen shutter button, etc.)
     - Gallery / media picker
     - Login and ID verification screens
     - Popups and sheets (including Meta Verified)
   - Add instructions like:
     - "First, determine which screen you are on based on visible UI elements and text."
     - "If you are in camera-only view with a shutter button and no selected media preview, you probably need to either open the gallery or go back to the feed/editor."
     - "If you are on an unrelated screen (profile, DMs, search, settings), navigate back to the previous screen or to the home feed before continuing."

6. **Introduce recovery behaviors for camera/media-selection traps**
   - In the camera/media-phase prompt:
     - Explicitly describe how to reach the gallery/media picker (e.g., tap on thumbnail in bottom-left, swipe up, or tap an icon labeled 'Gallery').
     - Specify a policy: if the AI has attempted 2–3 actions and still sees only the camera view without media selected, it should **back out** and try again from the last known safe state (e.g., feed or composer).
   - Add instructions to avoid infinite loops:
     - "Avoid repeating the same action more than twice if the screen does not change; instead, choose an alternative path such as going back or selecting a different navigation element."
   - Encourage the AI to confirm progress:
     - "After each action, verify whether you are closer to the goal (e.g., media preview visible, share button enabled). If not, reconsider your next step instead of repeating previous taps."

7. **Add ID verification loop detection and policy**
   - In the base prompt, describe characteristics of verification flows:
     - Phrases: "Confirm your identity", "We need to verify", "Upload a photo of your ID", "This helps us keep Instagram community safe".
     - UI: government ID card icons, help text about security and review.
   - Directive:
     - "If you see any screen that is asking to verify the account owner’s identity or upload an ID, **stop trying to post the reel**. Do not attempt to complete identity verification. Instead, indicate that you have encountered an **ID verification block** and cannot proceed."
   - Ensure the model is instructed to surface a distinct **structured outcome** (e.g., `state='id_verification_blocked'`) or clear textual marker that the Python code can parse.

## Python-Side Logic & Integration Changes
8. **Define structured navigation states and error outcomes**
   - If not present, introduce a small enum or string constants for navigation outcomes, for example:
     - `NAV_OK`, `NAV_META_VERIFIED_DISMISSED`, `NAV_RECOVERED_FROM_CAMERA_TRAP`, `NAV_ID_VERIFICATION_BLOCK`, `NAV_MAX_STEPS_EXCEEDED`, `NAV_UNRECOGNIZED_SCREEN`.
   - Update the code that parses Claude responses to map any special markers or phrases into these constants.
   - Ensure that **ID verification** maps to an error category compatible with the retry/error system from Tasks 46, 51, and 55:
     - Use an *account-level* error type such as `id_verification_required` so retries are not endlessly attempted.

9. **Implement step-count and loop-avoidance safeguards**
   - Review the existing `max_steps` handling in `post_reel_smart.py`:
     - If it simply stops after N steps and throws a generic error, refine it.
   - Introduce lightweight tracking for recent states or actions (e.g., last 3–5 screens/action descriptions) to detect repetition.
   - When the AI attempts the same action on the same apparent screen more than 2–3 times, trigger a **recovery strategy**:
     - For camera/media traps: tap back, try alternative gallery entry, or return to home.
     - For generic wrong screens: tap back or home icon to return to feed, then restart the appropriate sub-flow.
   - Only mark `max_steps` failure after at least one attempt at recovery; distinguish this from early detection of ID verification blocks.

10. **Wire navigation outcomes into error classification and progress tracking**
   - Where posting jobs produce final status/error strings, ensure:
     - Meta Verified popup cases that are successfully dismissed do **not** count as errors.
     - Persistent camera/media traps that exhaust recovery attempts are reported as an **infrastructure/navigation** issue, so the retry system can reattempt on another pass if appropriate.
     - ID verification detection produces a clear, consistent error message that will be categorized as **account-level** (e.g., includes keywords like "id verification required" or "confirm your identity" that map to the correct error category via `progress_tracker.py`).
   - Confirm that the error propagation path via `parallel_worker.py` (Task 55) is populated with the right `(category, error_type)` tuples.

11. **Logging and observability**
   - Add targeted logs (respecting existing logging conventions) around:
     - When Meta Verified popups are detected and dismissed.
     - When a camera/media trap is detected, including step count and chosen recovery action.
     - When an ID verification block is detected, with captured short textual evidence (redacted if necessary).
   - Ensure logs are concise but structured so failures can later be searched and aggregated.
   - Avoid logging full screenshots; instead log hashes or small textual summaries to maintain privacy.

12. **Maintainability & documentation**
   - Add inline comments near prompt constants explaining the rationale for the new instructions and listing key phrases used for detection.
   - Update any relevant developer documentation (e.g., `docs/MODULES.md` or `CLAUDE.md` if it documents vision navigation) to reflect:
     - The expanded state model.
     - How ID verification blocks propagate as account-level errors.
     - How to extend prompts when new Instagram UI variants appear.

## Implementation Best Practices
- **Prompt engineering patterns**:
  - Use clear headings/bullets in system prompts to separate "Goal", "Screen recognition", "Actions", and "Special cases (Meta Verified, ID verification)".
  - Prefer concise, unambiguous instructions; explicitly forbid risky actions like subscribing or changing security settings.
  - Include examples of *both* desired and undesired behavior.
- **Resilience**:
  - Design prompts to be tolerant to minor UI text changes by relying on multiple cues (icon shapes, button positions, general language).
  - Keep recovery policies simple and deterministic so behavior is predictable.
- **Testing-first mindset**:
  - Where possible, design the prompt output format (e.g., JSON with `state`, `action`, `reason`) to be machine-parseable, making it easier to unit-test and avoid ambiguity.

**Test Strategy:**

1. **Static Verification**
- Run `python -m compileall` or import checks to ensure `post_reel_smart.py` and any modified modules have no syntax errors.
- Grep or search for the new Meta Verified and ID verification instructions in the prompt constants to confirm they are present and free of typos.
- Verify any new enums/constants for navigation states are referenced consistently in both navigation and error/reporting code.

2. **Unit/Offline Tests for Prompt Parsing and Outcomes**
- If the Claude response is parsed into a structured object (e.g., JSON or dataclass), add unit tests that feed in sample model outputs and assert:
  - Meta Verified detection: sample output containing markers like `state: "meta_verified_popup"` maps to a dismissal action and does not finalize as an error.
  - Camera trap recovery: repeated actions on the same screen increment a counter and eventually trigger recovery actions (e.g., back, goto feed), not infinite repetition.
  - ID verification: outputs containing `state: "id_verification_blocked"` or equivalent text produce an account-level error classification (`error_category == 'account'`, `error_type == 'id_verification_required'`).
- Add tests to ensure `max_steps` failures distinguish between generic navigation failures and explicitly detected ID verification blocks.

3. **Screenshot-Driven Simulation Tests (Offline Vision Prompts)**
- Capture or use existing anonymized screenshots for each scenario:
  - A typical Meta Verified popup screen.
  - A pure camera view with no media selected.
  - A media picker/gallery screen.
  - An ID verification screen.
  - A normal composer/share screen for control.
- For each screenshot:
  - Feed the image plus the updated prompts into a test harness that calls Claude in a **dry-run or sandbox mode** (or use recorded Claude responses if live calls are not available).
  - Assert that:
    - Meta Verified screenshot yields a dismissal action and the model’s textual reasoning mentions closing/dismissing rather than subscribing.
    - Camera view screenshot yields an action to open gallery or back out, *not* repeated shutter presses.
    - ID verification screenshot yields an explicit signal that posting cannot continue and that ID verification is required.

4. **Integration Tests in Local/Dry-Run Mode**
- Use the existing dry-run/integration harness from Task 7 (mock `GeelarkDeviceController`, fake `ClaudeNavigator`) to simulate navigation sequences:
  - Scenario A (Meta Verified):
    - Script the fake vision component to report a Meta Verified popup; verify
      - The navigation logic issues a dismiss action.
      - The job continues to completion without error.
  - Scenario B (Camera/media trap):
    - Script a sequence where the screen stays on camera despite 2 repetitive taps; verify
      - The system does not loop indefinitely.
      - After the configured number of repeats, a recovery path is chosen (e.g., back to feed and re-enter composer).
      - If recovery fails, the error message is marked as navigation/infrastructure-level and eligible for retry.
  - Scenario C (ID verification loop):
    - Script an ID verification screen after launching Instagram; verify
      - The posting job aborts promptly.
      - The error is classified as account-level with a specific `error_type` matching expectations.

5. **Live Device Smoke Tests**
- On a test Instagram account in a controlled environment:
  - Manually trigger or wait for a Meta Verified popup during posting (if necessary by visiting relevant settings beforehand); run a real post job and check:
    - The popup is dismissed without subscribing.
    - The flow continues to reel sharing and logs show detection and dismissal.
  - Perform several posts and intentionally navigate the app into camera view and other non-target screens (if possible via manual interference) to see if the AI recovers.
  - If an ID verification screen can be safely triggered on a sacrificial test account, confirm that the job aborts correctly and logs/progress CSV show an account-level failure.

6. **Error Classification and Retry Behavior Checks**
- Run a small batch of jobs through the full orchestrator/worker pipeline:
  - Introduce at least one job that hits each of the three scenarios via mocks or test accounts.
  - Inspect `parallel_progress.csv` (or equivalent) and verify:
    - Meta Verified events that are dismissed are not marked as errors.
    - Camera trap failures (if any remain after recovery attempts) are categorized as infrastructure and show up as retryable.
    - ID verification events are categorized as account-level and *not* retried in later passes.
- Confirm that the error category and type fields propagated via `parallel_worker.py` align with expectations and any dashboards or log analysis scripts treat them correctly.

7. **Regression Checks**
- Re-run existing posting smoke tests (standard happy-path reel posting) to ensure:
  - No increase in step counts or timeouts on normal flows.
  - Captions, media selection, and final posting success rates remain unchanged or improved.
- Review logs for unexpected new warnings or error messages related to navigation or parsing.

## Subtasks

### 64.1. Review existing Claude Vision prompts and navigation flow in post_reel_smart.py

**Status:** pending  
**Dependencies:** None  

Open post_reel_smart.py and any related modules (e.g., claude_analyzer.py, ClaudeNavigator) to understand how prompts, navigation state, and error outcomes are currently defined and used during the Instagram Reel posting flow.

**Details:**

Locate where Claude Vision prompts are constructed (constants or builder functions), how they are passed into ClaudeUIAnalyzer / ClaudeNavigator, and how responses are parsed into actions and navigation outcomes. Document the current state model (screens/states Claude knows about), any existing handling of popups or verification screens, and where max_steps and loop-avoidance are enforced. Capture notes on how navigation outcomes are currently surfaced to parallel_worker.py and progress tracking, to inform later changes.

### 64.2. Design and implement updated vision prompt templates with explicit edge-case handling

**Status:** pending  
**Dependencies:** 64.1  

Refactor and extend the Claude Vision prompt templates to include a reusable base system prompt, phase-specific prompts, and explicit instructions for Meta Verified popups, camera/media-selection traps, and ID verification flows.

**Details:**

Create or update clearly named prompt constants or builder functions (e.g., BASE_VISION_SYSTEM_PROMPT, PROMPT_PHASE_FEED_NAV, PROMPT_PHASE_CAMERA_OR_GALLERY, PROMPT_PHASE_EDITOR_AND_SHARE) in claude_analyzer.py or the appropriate module. Add sections that: (1) describe canonical Instagram states (feed, reel composer, share screen, camera, gallery, login, ID verification, popups), (2) specify allowed action vocabulary (tap, swipe, back, wait), (3) define special-case behavior: always dismiss Meta Verified/subscription upsell dialogs using close or 'Not now' and never subscribe; detect camera/media traps and prefer recovery/back-out instead of repeating actions; detect ID verification screens via key phrases and visuals and stop posting with a clear marker like state='id_verification_blocked'. Include 1–2 inline examples for Meta Verified handling and instructions to avoid repeating the same action on the same screen more than 2–3 times.

### 64.3. Integrate new prompts into ClaudeUIAnalyzer and ensure structured navigation outcomes

**Status:** pending  
**Dependencies:** 64.2  

Wire the new prompt templates into ClaudeUIAnalyzer (or equivalent) so that analyze() selects the correct prompt per phase, emits structured navigation outcomes, and includes markers for Meta Verified dismissal, camera-trap recovery, and ID verification blocks.

**Details:**

Update ClaudeUIAnalyzer.analyze(...) to choose the appropriate phase-specific prompt based on current posting state, prepend or merge with BASE_VISION_SYSTEM_PROMPT, and send this to Claude Vision. Extend the expected JSON/structured response schema to include fields such as state, reason, and special flags (e.g., meta_verified_dismissed, recovered_from_camera_trap, id_verification_blocked). Map textual markers from the model output to internal enums or string constants (e.g., NAV_OK, NAV_META_VERIFIED_DISMISSED, NAV_RECOVERED_FROM_CAMERA_TRAP, NAV_ID_VERIFICATION_BLOCK, NAV_MAX_STEPS_EXCEEDED, NAV_UNRECOGNIZED_SCREEN). Ensure that action coordinates and types still validate correctly and that the new markers do not break existing callers.

### 64.4. Update post_reel_smart.py state/loop handling and error classification for new outcomes

**Status:** pending  
**Dependencies:** 64.3  

Modify post_reel_smart.py to use the new structured navigation outcomes for step-count safeguards, recovery from camera/media traps, Meta Verified popup dismissal, and early termination on ID verification blocks, wiring these into the existing retry/error classification system.

**Details:**

Introduce or refine navigation outcome constants/enums in post_reel_smart.py and update the main navigation loop to: (1) treat NAV_META_VERIFIED_DISMISSED as a normal, non-error path; (2) trigger recovery strategies when camera/media traps or repeated actions on the same screen are detected, only failing with NAV_MAX_STEPS_EXCEEDED after at least one recovery attempt; (3) immediately stop the posting flow on NAV_ID_VERIFICATION_BLOCK and surface an account-level error such as id_verification_required compatible with the progress tracker and parallel_worker.py changes from Task 55. Ensure that final status/error strings and (category, error_type) tuples correctly distinguish account-level blocks from infrastructure/navigation issues so retries behave as intended.

### 64.5. Add logging, documentation, and minimal tests for hardened navigation prompts

**Status:** pending  
**Dependencies:** 64.4  

Introduce targeted logging, lightweight tests, and documentation updates to capture the new edge-case handling behavior and make it maintainable for future UI changes.

**Details:**

Add concise, structured logs in post_reel_smart.py and/or claude_analyzer.py when Meta Verified popups are detected and dismissed, when camera/media traps trigger recovery (including step counts), and when ID verification blocks are encountered (logging only short, non-sensitive textual evidence). Create or extend unit tests or integration-style tests that mock Claude responses to cover: Meta Verified popup recognition and dismissal, camera trap detection with recovery then max-steps failure, and ID verification block mapping to an account-level error. Finally, update relevant documentation (e.g., CLAUDE.md or module-level comments) to describe the expanded state model, special-case policies, and how to extend prompts for new Instagram UI variants.
