# PRD: GrapheneOS TikTok Poster with Account-Seeded Humanization

## 1. Goal & scope

- **Goal:** Make `tiktok_poster.py` reliably auto-post TikTok videos on GrapheneOS Pixels with:
  - Parity with the working Geelark TikTok poster.
  - Built-in humanization (jittered taps, scrolls, swipes, wait variance).
  - Account-seeded behavior profiles so each account looks like a distinct human.
- **Scope:**
  - TikTok posting only (Instagram is out of scope here).
  - GrapheneOS device path, without breaking the Geelark path.

## 2. Environment & assumptions

- Project path: `C:\Users\asus\Desktop\projects\geelark-automation`.
- OS: Windows host, using bash (WSL) and Python.
- Android:
  - Physical Pixel device running GrapheneOS.
  - TikTok installed and logged in on target accounts.
- Automation stack:
  - Appium server expected on `http://127.0.0.1:4723` (configurable).
  - `adb` (Android platform-tools) must be installed and available to the Python process.
- Code artifacts:
  - Working Geelark implementation (baseline).
  - GrapheneOS-specific files:
    - `grapheneos_config.py`
    - `grapheneos_device_manager.py`
    - `device_manager_base.py`
  - TikTok modules:
    - `tiktok_poster.py`
    - `tiktok_screen_detector.py`
    - `tiktok_action_engine.py`
    - `tiktok_engagement.py` (if present)
  - Logs:
    - `tiktok_error_logs/`
    - `tiktok_flow_analysis/`

## 3. High-level problems

1. **Device connectivity not guaranteed**
   - `adb devices` returned `adb: command not found` in earlier logs, meaning the script may run with no real device attached.
   - Appium `/status` gave no content, suggesting server not running or wrong URL.
2. **CLI mismatch**
   - Legacy flags like `--account`, `--video`, `--caption`, `--mode ai-only` no longer match `tiktok_poster.py`'s parser, causing immediate argument errors.
3. **GrapheneOS TikTok flow incomplete**
   - Screen detector misclassifies GrapheneOS camera as `VIDEO_EDITOR` and may not recognize Graphene-specific IDs/layout.
   - Action engine taps may still use Geelark IDs or coordinates, causing wrong navigation (e.g., into template picker).
4. **Humanization incomplete / not wired**
   - Good randomness parameters exist in recent commits, but:
     - They aren't centralized.
     - They aren't consistently used in the TikTok Graphene path.
   - No account-specific seeding, so behavior patterns are not tied to account/device.
5. **No single documented "happy path" for comparison**
   - Geelark TikTok flow is not documented as an explicit reference to port against.

## 4. Functional requirements

### 4.1 Connectivity & startup checks

When `tiktok_poster.py` runs with `--device grapheneos`:

- Before trying to control TikTok:
  - Validate `adb` is installed:
    - Run `adb version` and handle failure with a clear error message.
  - Validate at least one device is attached:
    - Run `adb devices` and ensure at least one non-emulator device is listed.
  - Validate Appium is reachable:
    - HTTP GET `<appium_url>/status` returns a valid JSON status.
- On failure:
  - Abort early with explicit messages:
    - `ADB not found in PATH`
    - `No devices attached`
    - `Appium not reachable at <url>`
- Centralize these checks in `device_connection.py` / `grapheneos_device_manager.py`.

### 4.2 CLI behavior

`tiktok_poster.py` must:

- Accept positional arguments:
  - `phone_name`
  - `video_path`
  - `caption`
- Accept flags:
  - `--device {geelark,grapheneos}`
  - `--appium-url APPIUM_URL`
  - `--ai-only`
  - `--rules-only`
  - `--hybrid`
  - `--no-humanize`
  - `--max-steps MAX_STEPS`
- For backwards compatibility:
  - If old flags `--account`, `--video`, `--caption`, `--mode` are used:
    - Either:
      - Show a friendly error explaining new syntax, or
      - Map them internally and issue a deprecation warning.

### 4.3 Geelark TikTok reference flow (baseline)

Document (in code comments + docs) the working Geelark path:

1. Start on TikTok HOME_FEED (For You page).
2. Tap `+` to open camera.
3. On camera (`CREATE_MENU`):
   - Tap gallery thumbnail.
4. In `GALLERY_PICKER`:
   - Select target video.
5. In `VIDEO_EDITOR`:
   - Optionally tweak, then tap `Next`.
6. In `CAPTION_SCREEN`:
   - Enter caption, finalize options, tap `Post`.
7. Confirm success (either a dedicated POST_SUCCESS screen or by verifying in the profile feed).

For each step, identify in the code:

- Screen detector:
  - Detection rules in `tiktok_screen_detector.py`.
- Action handler:
  - Functions in `tiktok_action_engine.py`.

### 4.4 GrapheneOS TikTok flow requirements

For GrapheneOS, implement the same high-level flow:

1. Ensure TikTok is on HOME_FEED.
2. Tap `+` to open camera.
3. Detect `CREATE_MENU` (camera):
   - Texts like "Add sound".
   - Duration options ("10m", "60s", "15s").
   - PHOTO / TEXT tabs.
   - Big record button.
   - Gallery thumbnails at bottom right (Graphene IDs like `r3r`/`ymg` where applicable).
4. Tap gallery thumbnail to open `GALLERY_PICKER`.
5. Select specified video.
6. Detect `VIDEO_EDITOR`:
   - Must detect "Next" button (Graphene resource ID/text).
   - Must **not** show PHOTO/TEXT tabs.
7. Proceed to `CAPTION_SCREEN`:
   - Enter caption text.
   - Optionally scroll settings.
8. Tap "Post".
9. Confirm success.

`tiktok_screen_detector.py` must be updated so GrapheneOS-specific rules and ID mappings are explicit and the detector:

- Prioritizes `CREATE_MENU` over `VIDEO_EDITOR`.
- Uses Graphene-specific resource IDs where Geelark IDs differ.

`tiktok_action_engine.py` must provide GrapheneOS branches for each screen:

- HOME_FEED
- CREATE_MENU
- GALLERY_PICKER
- VIDEO_EDITOR
- CAPTION_SCREEN
- POST_SUCCESS

Each branch must use Graphene-correct IDs/xpaths and not rely on hardcoded pixel coordinates when reliable elements exist.

### 4.5 Humanization primitives (shared)

Implement a generic humanization module, e.g. `humanization.py`, with:

1. `tap_with_jitter(driver, element=None, center=None, profile, rng)`
   - Compute tap center from `element` or `center`.
   - Add random offset within `[profile.tap_jitter_min_px, profile.tap_jitter_max_px]`.
   - Use Appium W3C actions / touch actions to perform the tap.
2. `human_scroll_vertical(driver, direction, profile, rng)`
   - Use percentages of screen height:
     - Start Y in `[profile.scroll_min_pct, profile.scroll_max_pct]`.
     - End Y in `[profile.scroll_min_pct, profile.scroll_max_pct]`, with direction controlling sign.
   - Randomize duration within profile-specified bounds.
3. `human_sleep(profile, rng, base=None)`
   - If `base` provided, jitter around it.
   - Else derive from profile's `sleep_base_range` and `sleep_jitter_ratio`.

These primitives must be **platform-agnostic** (no TikTok or Geelark/Graphene assumptions inside).

### 4.6 Account-seeded behavior profiles

Introduce a `BehaviorProfile` used by TikTok humanization:

- Fields (example, not exhaustive):
  - `tap_jitter_min_px`
  - `tap_jitter_max_px`
  - `scroll_min_pct`
  - `scroll_max_pct`
  - `scroll_count_pre_post_range`
  - `prob_scroll_before_post`
  - `prob_scroll_after_post`
  - `prob_explore_video_after_post`
  - `sleep_base_range` (min, max)
  - `sleep_jitter_ratio`

Seed and profile logic:

1. **Base seed per (device, account):**
   - Use a stable identifier such as:
     - Device type: `grapheneos` or specific Pixel name.
     - TikTok account username.
   - Compute base seed as stable hash of this pair:
     - `base_seed = hash(f"{device}::{phone_name}::tiktok::{account}") % 2**31`.
   - Store in a small JSON store (e.g. `random_profiles.json`) so that:
     - First run: entry created.
     - Subsequent runs: same base seed reused.
2. **Session seed:**
   - Derive from base seed + time bucket:
     - `session_seed = base_seed ^ int(current_time / SESSION_BUCKET_SECONDS)` (e.g. 6-hour buckets).
   - Create RNG:
     - `rng = random.Random(session_seed)`.
3. **Profile building:**
   - `build_behavior_profile(base_seed)`:
     - Uses `random.Random(base_seed)` to create deterministic but unique parameter ranges per account.
     - Clamp to globally safe bounds consistent with your existing Graphene commit ranges.
   - This allows each account to have a unique "personality".

### 4.7 Humanized TikTok flow integration (GrapheneOS)

For the GrapheneOS TikTok path in `tiktok_action_engine.py`, use `profile` and `rng`:

1. **HOME_FEED**
   - Before tapping `+`:
     - With probability `profile.prob_scroll_before_post`, perform 1-2 `human_scroll_vertical('up')` calls.
   - Use `human_sleep`.
   - Tap `+` via `tap_with_jitter`.

2. **CREATE_MENU (camera)**
   - Optional small wait and micro scroll (if safe).
   - Tap gallery thumbnail via `tap_with_jitter`.

3. **GALLERY_PICKER**
   - Use `human_scroll_vertical` 0-2 times even if target video is visible.
   - Tap video thumbnail via `tap_with_jitter`.

4. **VIDEO_EDITOR**
   - Optional:
     - Tap in video area with jitter (simulated preview).
     - Short `human_sleep`.
   - Tap "Next" via `tap_with_jitter`.

5. **CAPTION_SCREEN**
   - Type caption in a human-like way:
     - Either via simulated typing (chunks + `human_sleep`) or existing humanizer.
   - Optionally scroll settings using `human_scroll_vertical`.
   - Tap "Post" via `tap_with_jitter`.

6. **POST_SUCCESS / back to HOME_FEED**
   - With probability `profile.prob_scroll_after_post`, scroll feed a few times.
   - Optionally explore one video (if a safe back path is defined).

All humanization actions must be:

- Configurable (can be turned off via `--no-humanize` or config flag).
- Logged for debugging (screen, action, parameters).

## 5. Non-functional requirements

- **Logging:**
  - For each run:
    - Log device, account, base_seed, session_seed.
    - Log the generated `BehaviorProfile`.
    - Log every humanization action with its parameters.
- **Determinism & variation:**
  - For the same account and time bucket, behavior profile must be reproducible.
  - Across accounts, profiles differ.
- **Backward compatibility:**
  - Geelark TikTok path must still work unchanged (or with equivalent behavior).

## 6. Implementation tasks (for Taskmaster / Claude)

1. **Task 1 - Connectivity & CLI**
   - Implement adb/Appium checks in `device_connection.py` / `grapheneos_device_manager.py`.
   - Normalize `tiktok_poster.py` CLI to the positional + flags schema.
   - Add nice error handling for legacy flags.

2. **Task 2 - Document Geelark TikTok flow & diffs**
   - Extract Geelark happy path from:
     - `tiktok_poster.py`
     - `tiktok_action_engine.py`
     - `tiktok_screen_detector.py`
   - Save into `.taskmaster/docs/geelark_tiktok_flow.md`.
   - Diff Geelark vs GrapheneOS TikTok logic and write `.taskmaster/docs/grapheneos_vs_geelark_tiktok_diffs.md`.

3. **Task 3 - Fix GrapheneOS screen detection**
   - Use `tiktok_error_logs/` and `tiktok_flow_analysis/` to:
     - Implement robust `_detect_create_menu`, `_detect_video_editor`, `_detect_gallery_picker` for GrapheneOS.
   - Ensure `CREATE_MENU` detection is stronger than `VIDEO_EDITOR` when PHOTO/TEXT + durations are present.
   - Keep Geelark behavior intact.

4. **Task 4 - Align GrapheneOS action engine**
   - For each TikTok screen:
     - Implement GrapheneOS-specific handlers that use correct element IDs/xpaths.
   - Replace brittle coordinate taps with element-based taps when possible.

5. **Task 5 - Centralize existing humanization config**
   - Find all randomness/humanization constants from recent commits.
   - Consolidate into `humanization_config.py` or into the new `BehaviorProfile`.
   - Remove dead or unused constants.

6. **Task 6 - Implement humanization primitives**
   - Create `humanization.py` with:
     - `tap_with_jitter`
     - `human_scroll_vertical`
     - `human_sleep`
   - Implement using Appium's touch actions (W3C Actions) and parametrized by a `BehaviorProfile` + `rng`.

7. **Task 7 - Implement account-seeded BehaviorProfile**
   - Add `BehaviorProfile` dataclass.
   - Implement:
     - `get_or_create_base_seed(device, account)`
     - `build_behavior_profile(base_seed)` using your existing parameter ranges.
   - Wire session seeding and RNG into TikTok runs.

8. **Task 8 - Wire humanization into GrapheneOS TikTok flow**
   - In `tiktok_poster.py`:
     - At run start, build profile + `rng` and pass them into the TikTok posting pipeline.
   - In `tiktok_action_engine.py`:
     - Use profile + `rng` in all GrapheneOS TikTok action handlers.
   - Honor `--no-humanize` to bypass extra actions when needed.

9. **Task 9 - Logging & validation**
   - Log seeds, profile, and actions.
   - Run AI-only flows to verify:
     - Correct screen mapping.
     - Non-deterministic but bounded humanization patterns.
   - Confirm non-AI posting successfully uploads a video on GrapheneOS TikTok.
