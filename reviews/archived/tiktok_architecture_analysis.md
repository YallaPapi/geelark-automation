# TikTok Poster Architecture Debug Analysis

**Task 67 - Prompt 6 Implementation**
**Date:** 2025-12-16

---

## Section 1: Architecture Summary

### BasePoster Interface (`posters/base_poster.py`)

| Component | Description |
|-----------|-------------|
| `PostResult` dataclass | Standardized result with fields: `success`, `error`, `error_type`, `error_category`, `retryable`, `platform`, `account`, `duration_seconds`, `screenshot_path`, `timestamp` |
| `BasePoster.platform` | Abstract property returning platform identifier |
| `BasePoster.connect()` | Abstract method for device connection (Geelark + ADB + Appium) |
| `BasePoster.post()` | Abstract method for posting flow, returns `PostResult` |
| `BasePoster.cleanup()` | Abstract method for resource release |

### Instagram Implementation (`posters/instagram_poster.py` + `post_reel_smart.py`)

- **Pattern:** Adapter wrapping `SmartInstagramPoster`
- **Error extraction:** Pulls `last_error_message`, `last_error_type`, `last_screenshot_path` from underlying poster
- **Screenshot capture:** Delegated to `SmartInstagramPoster.analyze_failure_screenshot()` (lines 509-590 in post_reel_smart.py)
- **Loop detection:** Has `_track_action_for_loop_detection()` and `_check_and_recover_from_loop()` methods
- **Claude prompt:** Comprehensive 110+ line prompt in `claude_analyzer.py` with detailed error handling rules

### TikTok Implementation (`posters/tiktok_poster.py`)

- **Pattern:** Direct implementation (NOT adapter)
- **Error extraction:** Has `_last_error_type`, `_last_error_message`, `_last_screenshot_path` attributes but they are **never populated on failure**
- **Screenshot capture:** **MISSING** - no screenshot capture on max_steps or error detection
- **Loop detection:** **MISSING** - no loop detection or recovery logic
- **Claude prompt:** 60-line inline `TIKTOK_NAVIGATION_PROMPT` (lines 93-153)

### Key Architectural Differences

| Feature | Instagram | TikTok |
|---------|-----------|--------|
| Implementation pattern | Adapter around SmartInstagramPoster | Direct implementation |
| Claude prompt location | External (`claude_analyzer.py`) | Inline constant |
| Screenshot on failure | Yes (`analyze_failure_screenshot()`) | **No** |
| Loop detection | Yes (5-action window) | **No** |
| State variables | Managed by SmartInstagramPoster | `_video_uploaded`, `_caption_entered`, `_post_clicked` |
| Error context to PostResult | Full (`screenshot_path`, detailed `error_type`) | Partial (no screenshot) |

---

## Section 2: Root Causes for TikTok Navigation Failure

### RC-1: Missing `video_selected` State Update
**File:** `posters/tiktok_poster.py` lines 363-367

```python
# Current code only checks:
if action.get('caption_entered'):
    self._caption_entered = True
if action.get('post_clicked'):
    self._post_clicked = True
# MISSING: video_selected is never read from Claude's response!
```

**Impact:** The prompt (line 142) asks Claude to return `video_selected: true/false`, but the code ignores it. State never advances past video selection phase.

### RC-2: No Loop Detection
**File:** `posters/tiktok_poster.py` (entire post() method, lines 275-412)

**Instagram has:**
```python
# In post_reel_smart.py lines 929-1047
self._track_action_for_loop_detection(action_type, element_desc)
should_abort, loop_recovery_count, should_clear = self._check_and_recover_from_loop(...)
```

**TikTok has:** Nothing. Stuck navigation repeats same action indefinitely until `max_steps`.

### RC-3: Prompt-State Variable Mismatch
**File:** `posters/tiktok_poster.py` lines 95-98

```python
# Prompt shows:
# - Video uploaded to phone: {video_uploaded}  <- This is phone upload, not gallery selection
# - Caption entered: {caption_entered}
# - Post button clicked: {post_clicked}
```

**Problem:** The posting flow needs `video_selected` (gallery selection step) but prompt only shows `video_uploaded` (file transfer step). Claude may be confused about actual state.

### RC-4: No Keyboard Visibility Check
**File:** `posters/tiktok_poster.py` lines 494-505 (`tap_and_type` action)

```python
# TikTok does:
self._ui_controller.tap(x, y)
time.sleep(0.5)
self._ui_controller.type_text(text)
```

**Instagram has:** `_handle_tap_and_type()` with `is_keyboard_visible()` checks and retry logic.

**Impact:** Text input may fail silently if keyboard doesn't appear.

### RC-5: Missing Done Confirmation Logic
**File:** `posters/tiktok_poster.py` lines 369-378

```python
# TikTok relies entirely on Claude returning action='done'
if action['action'] == 'done':
    print("  Post completed!")
    return PostResult(success=True, ...)
```

**Instagram has:** `wait_for_upload_complete()` that polls for specific confirmation text like "your reel has been shared".

**Impact:** No verification that post actually succeeded. Claude might return "done" prematurely.

### RC-6: `_format_elements_for_claude()` Missing Class Attribute
**File:** `posters/tiktok_poster.py` lines 423-439

```python
# Current formatting includes:
# text, desc, id, center, clickable
# MISSING: class attribute (e.g., 'android.widget.Button')
```

**Impact:** TikTok UI may have important class info that helps Claude identify elements correctly.

### RC-7: No Screenshot on `max_steps` Timeout
**File:** `posters/tiktok_poster.py` lines 386-397

```python
# Max steps reached - NO SCREENSHOT CAPTURE
duration = time.time() - self._start_time if self._start_time else 0
return PostResult(
    success=False,
    error=f"Max steps ({max_steps}) reached without completing post",
    # screenshot_path is NOT SET!
)
```

**Impact:** When debugging, we have no visual evidence of what screen Claude was stuck on.

---

## Section 3: Observability Gaps

| Gap | Instagram | TikTok | Impact |
|-----|-----------|--------|--------|
| Error screenshot capture | `analyze_failure_screenshot()` saves PNG + Claude Vision analysis | **None** | Cannot see what UI state caused failure |
| Vision-based error analysis | Claude Vision analyzes screenshot on failure | **None** | No intelligent failure interpretation |
| Loop detection logging | Logs when action repeats 5+ times | **None** | Cannot detect stuck navigation patterns |
| Step-by-step element logging | Full element details printed | Limited (first 10 only, lines 355-359) | Partial visibility into UI state |
| `last_screenshot_path` population | Set by `analyze_failure_screenshot()` | **Never set** | `PostResult.screenshot_path` always empty |
| UI dump archival | No | No | Cannot replay/analyze navigation post-mortem |
| Claude response logging | Via ClaudeUIAnalyzer | Added debug print (line 461) | Only partial - truncated to 500 chars |
| State transition logging | Implicit in loop | `print(f"  Action: {action['action']}")` | Basic but insufficient |

### Missing Debug Artifacts for TikTok

1. **No `error_screenshots/` files for TikTok failures** - only Instagram failures are captured
2. **No UI XML dumps** - cannot inspect raw UI hierarchy
3. **No state transition log** - cannot trace `_video_uploaded` → `_caption_entered` → `_post_clicked` progression
4. **No Claude conversation log** - cannot review full prompt/response history

---

## Section 4: Prioritized Fix Recommendations

| Priority | Fix | File | Lines | Effort |
|----------|-----|------|-------|--------|
| P0 | Add `_capture_failure_screenshot()` method | `tiktok_poster.py` | New method | Medium |
| P0 | Capture screenshot on `max_steps` timeout | `tiktok_poster.py` | 386-397 | Low |
| P0 | Capture screenshot on error detection | `tiktok_poster.py` | 341-350 | Low |
| P1 | Add `video_selected` state tracking | `tiktok_poster.py` | 363-367, 176-179 | Low |
| P1 | Add loop detection (port from Instagram) | `tiktok_poster.py` | New methods | Medium |
| P2 | Add `class` attribute to element formatting | `tiktok_poster.py` | 423-439 | Low |
| P2 | Add keyboard visibility check for `tap_and_type` | `tiktok_poster.py` | 494-505 | Medium |
| P2 | Add post confirmation verification | `tiktok_poster.py` | 369-378 | Medium |
| P3 | Improve Claude prompt with more explicit rules | `tiktok_poster.py` | 93-153 | Medium |
| P3 | Add periodic UI dump archival | `tiktok_poster.py` | New method | Low |

---

## Files Referenced

- `posters/base_poster.py` - Interface definition (105 lines)
- `posters/instagram_poster.py` - Working adapter pattern (161 lines)
- `posters/tiktok_poster.py` - Broken direct implementation (599 lines)
- `post_reel_smart.py` - Instagram navigation loop with loop detection (lines 929-1047)
- `claude_analyzer.py` - Instagram prompt (lines 54-189)
- `appium_ui_controller.py` - Shared UI controller

---

## Next Steps

1. **Prompt 7:** Implement screenshot capture aligned with Instagram pattern
2. **Prompt 8:** Add navigation loop instrumentation for debugging
3. **Prompt 9:** Align Claude prompt, UI format, and action schema
4. **Prompt 10:** End-to-end test plan for validation
