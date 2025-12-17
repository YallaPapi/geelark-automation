# Prompt 2 Response – Coupling & Cohesion Analysis for Posters

## Objective
Evaluate coupling between SmartInstagramPoster, device controllers, and orchestrator/worker to safely introduce BasePoster with minimal regression risk.

---

## 1. Direct Calls vs. Through Managers

### GOOD: Properly Delegated to DeviceConnectionManager
| Operation | Location | Notes |
|-----------|----------|-------|
| `connect()` | Line 858 | Delegates to `_conn.connect()` |
| `connect_appium()` | Line 870 | Delegates to `_conn.connect_appium()` |
| `reconnect_appium()` | Line 132 | Delegates to `_conn.reconnect_appium()` |
| `verify_adb_connection()` | Line 863 | Delegates to `_conn.verify_adb_connection()` |
| `adb()` commands | Line 124 | Delegates to `_conn.adb_command()` |
| `cleanup()` | Line 1049 | Delegates to `_conn.disconnect()` |

### GOOD: Properly Delegated to AppiumUIController
| Operation | Location | Notes |
|-----------|----------|-------|
| `tap()` | Line 138 | Delegates to `ui_controller.tap()` |
| `swipe()` | Line 145 | Delegates to `ui_controller.swipe()` |
| `press_key()` | Line 152 | Delegates to `ui_controller.press_key()` |
| `type_text()` | Line 776 | Delegates to `ui_controller.type_text()` |

### PROBLEMATIC: Direct ADB Shell Commands (Instagram-Specific)
These bypass the UI controller and mix **platform-specific app control** with infra:

| Command | Location | Purpose |
|---------|----------|---------|
| `am force-stop com.instagram.android` | Lines 669, 748, 913 | Kill Instagram app |
| `monkey -p com.instagram.android 1` | Lines 671, 751, 915 | Open Instagram app |
| `input swipe` | Lines 689, 693 | Direct scroll (bypasses AppiumUIController) |
| `dumpsys input_method` | Line 761 | Check keyboard visibility |
| `dumpsys window` | Lines 766, 770 | Check keyboard visibility |
| `am broadcast` (media scanner) | Line 887 | Trigger media index |
| `rm -f /sdcard/Download/*.mp4` | Line 1053 | Video cleanup |
| `rm -f /sdcard/DCIM/Camera/IMG_*.png` | Lines 892-893 | Screenshot cleanup |

**Impact:** These hardcoded package names (`com.instagram.android`) and paths prevent code reuse for TikTok.

---

## 2. Dependencies from SmartInstagramPoster

### A. Geelark Client
```python
self.client = self._conn.client  # Line 68 - exposed for compatibility
```
**Used for:**
- `upload_file_to_geelark()` - Upload video to cloud (Line 878)
- `upload_file_to_phone()` - Push to device (Line 881)
- `wait_for_upload()` - Wait for transfer (Line 883)

**Coupling:** Low (via DeviceConnectionManager). Clean API.

### B. Claude Navigator (ClaudeUIAnalyzer)
```python
self._analyzer = ClaudeUIAnalyzer()  # Line 70
self.anthropic = self._analyzer.client  # Line 71 - exposed for Vision API
```
**Used for:**
- `analyze_ui()` - Get next action (Line 970)
- `analyze_failure_screenshot()` - Vision analysis of errors (Lines 545-582)

**Coupling:** HIGH. The entire prompt in `claude_analyzer.py` is Instagram-specific:
- References "Reel" (Instagram terminology)
- Package name `com.instagram.android`
- Instagram-specific UI patterns (Create, Profile tab, Gallery selector)
- Instagram-specific popup handling (Meta Verified, Suggested for you)

### C. Logging/Progress Tracker
**No direct coupling.** SmartInstagramPoster uses `print()` statements.
Progress tracking is handled by `parallel_worker.py`, not the poster.

### D. Config Loading
```python
from config import Config, setup_environment
setup_environment()  # Line 20
```
**Used for:**
- Screen coordinates (SCREEN_CENTER_X/Y, FEED_TOP_Y, etc.)
- Appium URL default

**Coupling:** Low. Config is read-only and platform-agnostic.

---

## 3. Unnecessary or Bidirectional Coupling

### RED FLAG 1: Compatibility Properties Exposing Internals
```python
# Lines 85-115: Properties exposing DeviceConnectionManager internals
@property
def phone_id(self): return self._conn.phone_id
@phone_id.setter
def phone_id(self, value): self._conn.phone_id = value

@property
def device(self): return self._conn.device
@device.setter
def device(self, value): self._conn.device = value

@property
def appium_driver(self): return self._conn.appium_driver
@appium_driver.setter
def appium_driver(self, value): self._conn.appium_driver = value
```

**Problem:** External code can reach into and mutate internal connection state. This is used by tests and makes refactoring risky.

**Who uses these?**
- `dump_ui()` - Accesses `self.appium_driver` directly (Line 793)
- `analyze_failure_screenshot()` - Accesses `self.appium_driver` (Lines 531, 535)
- `take_error_screenshot()` - Accesses `self.appium_driver` (Line 500)

### RED FLAG 2: Direct Appium Driver Access in dump_ui()
```python
def dump_ui(self):
    if not self.appium_driver:  # Line 789
        raise Exception(...)
    xml_str = self.appium_driver.page_source  # Line 793
```

**Problem:** Bypasses AppiumUIController. Should use `self.ui_controller.dump_ui()`.

### RED FLAG 3: Instagram Package Name Hardcoded
```python
self.adb("am force-stop com.instagram.android")  # Lines 669, 748, 913
self.adb("monkey -p com.instagram.android 1")    # Lines 671, 751, 915
```

**Problem:** Platform-specific. TikTok uses `com.zhiliaoapp.musically` (or `com.ss.android.ugc.trill`).

### RED FLAG 4: Error Patterns Hardcoded (Instagram-Specific)
```python
error_patterns = {
    'terminated': ['we disabled your account', ...],
    'suspended': ['account has been suspended', ...],
    'id_verification': ['confirm your identity', ...],
    'logged_out': ['log in to instagram', ...],  # Instagram-specific!
    ...
}
```

**Problem:** TikTok has different error messages. This belongs in platform poster.

### RED FLAG 5: State Variables Mixed Across Concerns
```python
# Posting state (platform-specific)
self.video_uploaded = False
self.caption_entered = False
self.share_clicked = False

# Error tracking (should be in PostResult)
self.last_error_type = None
self.last_error_message = None
self.last_screenshot_path = None
```

**Problem:** These should be scoped per-post, not instance variables. And error tracking should be in PostResult.

---

## 4. Recommended Refactors

### Refactor 1: Move App Control to Platform Poster
**Current:**
```python
# post_reel_smart.py
self.adb("am force-stop com.instagram.android")
self.adb("monkey -p com.instagram.android 1")
```

**After:**
```python
# posters/instagram_poster.py
class InstagramPoster(BasePoster):
    APP_PACKAGE = "com.instagram.android"

    def _restart_app(self):
        self.adb(f"am force-stop {self.APP_PACKAGE}")
        time.sleep(2)
        self.adb(f"monkey -p {self.APP_PACKAGE} 1")
```

**Result:** Package name encapsulated per platform.

### Refactor 2: Move dump_ui() to AppiumUIController
**Current:**
```python
# post_reel_smart.py
def dump_ui(self):
    xml_str = self.appium_driver.page_source  # Direct driver access
```

**After:**
```python
# appium_ui_controller.py
def dump_ui(self):
    """Get UI hierarchy from Appium."""
    xml_str = self.driver.page_source
    return self._parse_elements(xml_str), xml_str
```

```python
# post_reel_smart.py
def dump_ui(self):
    return self.ui_controller.dump_ui()  # Proper delegation
```

**Result:** UI controller fully owns driver access.

### Refactor 3: Platform-Specific Claude Prompts
**Current:**
```python
# claude_analyzer.py (Instagram-specific prompt hardcoded)
prompt = f"""You are controlling an Android phone to post a Reel to Instagram...
```

**After:**
```python
# posters/instagram_poster.py
class InstagramPoster(BasePoster):
    def _get_claude_prompt(self, elements, caption):
        return f"""You are controlling an Android phone to post a Reel to Instagram...

# posters/tiktok_poster.py
class TikTokPoster(BasePoster):
    def _get_claude_prompt(self, elements, caption):
        return f"""You are controlling an Android phone to post a video to TikTok...
```

**Result:** Each poster owns its prompt.

### Refactor 4: Error Pattern Registry per Platform
**Current:**
```python
# post_reel_smart.py
error_patterns = {
    'logged_out': ['log in to instagram', ...],  # Hardcoded
}
```

**After:**
```python
# posters/instagram_poster.py
ERROR_PATTERNS = {
    'logged_out': ['log in to instagram', 'create new account', ...],
}

# posters/tiktok_poster.py
ERROR_PATTERNS = {
    'logged_out': ['log in to tiktok', 'sign up', ...],
}
```

**Result:** Error detection is platform-specific and testable.

---

## 5. Interface Boundaries for BasePoster

### Clean Surface for Adapter

The current SmartInstagramPoster has a clean outer surface that BasePoster can wrap:

```python
class BasePoster(ABC):
    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to device."""
        pass

    @abstractmethod
    def post(self, video_path: str, caption: str) -> PostResult:
        """Execute posting flow."""
        pass

    @abstractmethod
    def cleanup(self):
        """Release resources."""
        pass
```

### Internal Methods That Must Remain Internal

These should NOT be part of BasePoster:
- `dump_ui()` - Platform-specific UI parsing
- `analyze_ui()` - Platform-specific Claude prompts
- `detect_error_state()` - Platform-specific error patterns
- `_humanize_*()` - Platform-specific UI actions
- `upload_video()` - Currently shared, but video paths may differ per platform

### Shared Infrastructure (via Composition)

These remain as shared dependencies, passed to posters:
- `DeviceConnectionManager` - Device lifecycle (find, start, ADB, Appium)
- `AppiumUIController` - UI operations (tap, swipe, type)
- `GeelarkClient` - Cloud phone API (exposed via DeviceConnectionManager)

---

## Summary of Coupling Hotspots

| Hotspot | Severity | Fix |
|---------|----------|-----|
| Hardcoded `com.instagram.android` | HIGH | Move to poster class constant |
| Instagram-specific Claude prompt | HIGH | Move to poster, inject into analyzer |
| Instagram-specific error patterns | HIGH | Move to poster as class constant |
| Direct `appium_driver` access in dump_ui | MEDIUM | Delegate to AppiumUIController |
| Compatibility property setters (phone_id, device, etc.) | MEDIUM | Remove after refactor |
| Direct `input swipe` ADB commands | LOW | Use AppiumUIController.swipe() |
| Instance-level error state tracking | LOW | Move to PostResult |

---

## Safe Migration Path

1. **Phase 1:** Create `posters/base_poster.py` with abstract interface
2. **Phase 2:** Create `posters/instagram_poster.py` as thin adapter around SmartInstagramPoster
3. **Phase 3:** Move Instagram-specific constants into InstagramPoster (package name, error patterns)
4. **Phase 4:** Extract Claude prompt to be injected by poster
5. **Phase 5:** Implement TikTokPoster following the same pattern
6. **Phase 6:** Remove compatibility properties once all callers updated
