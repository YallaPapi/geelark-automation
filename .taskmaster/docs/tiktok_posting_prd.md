# PRD: TikTok Hybrid Posting System

## Overview

Extend the existing Instagram hybrid posting system to support TikTok video posting. This follows the **exact same architecture** as Instagram (ScreenDetector + ActionEngine + HybridNavigator) with TikTok-specific screen types and detection rules.

## Background

### Current Instagram Architecture (What We're Copying)

```
Vision-Action Loop:
1. dump_ui()           → Get UI elements from Appium
2. ScreenDetector      → Identify current screen (24 types)
3. ActionEngine        → Get action for screen (tap, type, etc.)
4. HybridNavigator     → Execute with AI fallback if rules fail
5. FlowLogger          → Log step for analysis
6. Repeat until SUCCESS or ERROR
```

**Key Components:**
- `screen_detector.py` - 24 screen types, detection rules by ID/desc/text
- `action_engine.py` - Handler per screen type, returns Action
- `hybrid_navigator.py` - Coordinates detection + action, AI fallback
- `post_reel_smart.py` - Main poster with vision-action loop

**Results:** 88% hybrid accuracy, 12% AI fallback, $0.05/post (vs $0.40 AI-only)

### Why TikTok Is Simpler

| Aspect | Instagram | TikTok |
|--------|-----------|--------|
| Posting flow screens | 8+ screens | ~5-6 screens |
| Popup variations | 15+ types | ~5 types |
| State flags | 4 (video_selected, caption_entered, etc.) | 3-4 same concept |
| Complexity | High (many edge cases) | Lower (linear flow) |

**Estimated Effort:** Since we're copying an existing pattern (not inventing), this is primarily screen mapping work.

## TikTok Posting Flow (Expected)

Based on TikTok Android app analysis:

```
HOME_FEED → [Tap + button]
    ↓
CREATE_MENU → [Tap "Upload" or Camera Roll icon]
    ↓
GALLERY_PICKER → [Tap video thumbnail]
    ↓
VIDEO_PREVIEW → [Tap "Next"]
    ↓
SOUNDS_EFFECTS → [Tap "Next" or Skip]
    ↓
CAPTION_SCREEN → [Type caption, Tap "Post"]
    ↓
UPLOAD_PROGRESS → [Wait for completion]
    ↓
SUCCESS → [Back on feed or profile]
```

## Implementation Approach

### What We're Copying (Existing Files)

| Instagram File | TikTok File | Change |
|----------------|-------------|--------|
| `screen_detector.py` | `tiktok_screen_detector.py` | TikTok screen types + rules |
| `action_engine.py` | `tiktok_action_engine.py` | TikTok action handlers |
| `hybrid_navigator.py` | `tiktok_hybrid_navigator.py` | Minimal changes (same logic) |
| `post_reel_smart.py` | `tiktok_poster.py` | TikTok package name + loop |
| `flow_logger.py` | **REUSE AS-IS** | Same logging |
| `appium_ui_controller.py` | **REUSE AS-IS** | Same tap/type/swipe |
| `device_connection.py` | **REUSE AS-IS** | Same connection logic |

### Files to Create

```
tiktok_screen_detector.py     # TikTokScreenType enum + detection rules
tiktok_action_engine.py       # TikTok screen → action handlers
tiktok_hybrid_navigator.py    # Coordinator (copy hybrid_navigator.py, change imports)
tiktok_poster.py              # Main poster (copy post_reel_smart.py pattern)
```

**DO NOT MODIFY:** Any existing Instagram files.

## Detailed Design

### 1. TikTokScreenType Enum

```python
class TikTokScreenType(Enum):
    # Main posting flow
    HOME_FEED = auto()           # Main For You / Following feed
    CREATE_MENU = auto()         # Bottom sheet with Upload, Camera, etc.
    GALLERY_PICKER = auto()      # Video selection grid
    VIDEO_PREVIEW = auto()       # Selected video with trim controls
    SOUNDS_EFFECTS = auto()      # Add sounds, effects, text
    CAPTION_SCREEN = auto()      # Description, hashtags, visibility
    UPLOAD_PROGRESS = auto()     # "Uploading..." or "Posting..."
    SUCCESS = auto()             # Post complete (back on feed)

    # Popups / Interruptions
    POPUP_DISMISSIBLE = auto()   # "Not now", "Skip", "Later"
    POPUP_PERMISSION = auto()    # Camera/storage permissions
    LOGIN_REQUIRED = auto()      # Account logged out
    ACCOUNT_ISSUE = auto()       # Banned, suspended, etc.

    # Fallback
    UNKNOWN = auto()             # Couldn't identify
```

### 2. Detection Rules Pattern

Copy the same pattern from Instagram:

```python
class TikTokScreenDetector:
    DETECTION_THRESHOLD = 0.7

    def __init__(self):
        # Priority order (highest first)
        self.rules = [
            ('ACCOUNT_ISSUE', self._detect_account_issue),
            ('LOGIN_REQUIRED', self._detect_login_required),
            ('POPUP_PERMISSION', self._detect_permission_popup),
            ('POPUP_DISMISSIBLE', self._detect_dismissible_popup),
            ('UPLOAD_PROGRESS', self._detect_upload_progress),
            ('SUCCESS', self._detect_success),
            ('CAPTION_SCREEN', self._detect_caption_screen),
            ('SOUNDS_EFFECTS', self._detect_sounds_effects),
            ('VIDEO_PREVIEW', self._detect_video_preview),
            ('GALLERY_PICKER', self._detect_gallery_picker),
            ('CREATE_MENU', self._detect_create_menu),
            ('HOME_FEED', self._detect_home_feed),
        ]

    def detect(self, elements):
        texts, descs, all_text = self._extract_text(elements)

        for rule_name, detector_fn in self.rules:
            confidence, key_elements = detector_fn(elements, texts, descs, all_text)
            if confidence >= self.DETECTION_THRESHOLD:
                return DetectionResult(
                    screen_type=TikTokScreenType[rule_name],
                    confidence=confidence,
                    key_elements=key_elements
                )

        return DetectionResult(TikTokScreenType.UNKNOWN, 0.0, [])
```

### 3. TikTok Detection Examples

```python
def _detect_home_feed(self, elements, texts, descs, all_text):
    """TikTok home feed with For You / Following tabs."""
    score = 0.0
    found = []

    # Primary: Bottom navigation bar
    if self._has_element_id(elements, 'com.zhiliaoapp.musically:id/b6v'):  # + button
        score += 0.4
        found.append('create_button')

    # Secondary: Tab indicators
    if 'for you' in all_text or 'following' in all_text:
        score += 0.3
        found.append('feed_tabs')

    # Tertiary: Video playback indicators
    if self._has_element_id(elements, 'like_button') or 'like' in descs:
        score += 0.2
        found.append('video_actions')

    return min(score, 0.95), found

def _detect_caption_screen(self, elements, texts, descs, all_text):
    """Caption entry with Post button."""
    score = 0.0
    found = []

    # Primary: Description input field
    if 'describe your video' in all_text or 'add a description' in all_text:
        score += 0.4
        found.append('description_hint')

    # Primary: Post button
    if 'post' in texts and 'post' not in all_text.replace('post', '', 1):
        score += 0.35
        found.append('post_button')

    # Secondary: Visibility settings
    if 'who can watch' in all_text or 'everyone' in texts:
        score += 0.15
        found.append('visibility')

    return min(score, 0.95), found
```

### 4. Action Engine Pattern

```python
class TikTokActionEngine:
    def __init__(self, caption=""):
        self.caption = caption
        self.video_selected = False
        self.caption_entered = False

        self.handlers = {
            TikTokScreenType.HOME_FEED: self._handle_home_feed,
            TikTokScreenType.CREATE_MENU: self._handle_create_menu,
            TikTokScreenType.GALLERY_PICKER: self._handle_gallery_picker,
            TikTokScreenType.VIDEO_PREVIEW: self._handle_video_preview,
            TikTokScreenType.SOUNDS_EFFECTS: self._handle_sounds_effects,
            TikTokScreenType.CAPTION_SCREEN: self._handle_caption_screen,
            TikTokScreenType.UPLOAD_PROGRESS: self._handle_upload_progress,
            TikTokScreenType.SUCCESS: self._handle_success,
            TikTokScreenType.POPUP_DISMISSIBLE: self._handle_popup_dismissible,
            # ... other handlers
        }

    def _handle_home_feed(self, elements):
        """Tap + button to create."""
        for i, el in enumerate(elements):
            if el.get('desc', '').lower() in ['create', 'new video', 'upload']:
                return Action(ActionType.TAP, target_element=i, confidence=0.95)

        # Fallback: Center bottom + button position
        return Action(ActionType.TAP_COORDINATE, coordinates=(540, 1850), confidence=0.7)

    def _handle_caption_screen(self, elements):
        """Type caption then tap Post."""
        if not self.caption_entered:
            # Find description field
            for i, el in enumerate(elements):
                if 'describe' in el.get('text', '').lower() or 'description' in el.get('desc', '').lower():
                    return Action(
                        ActionType.TAP,
                        target_element=i,
                        follow_up=Action(ActionType.TYPE_TEXT, text_to_type=self.caption),
                        confidence=0.95
                    )

        # Caption entered, tap Post
        for i, el in enumerate(elements):
            if el.get('text', '').lower() == 'post':
                return Action(ActionType.TAP, target_element=i, confidence=0.98)

        return Action(ActionType.NEED_AI, confidence=0.0)
```

### 5. Poster Main Loop

```python
class TikTokPoster:
    def __init__(self, phone_name, ...):
        # Same setup as SmartInstagramPoster
        self._conn = DeviceConnectionManager(phone_name, ...)
        self._ui_controller = AppiumUIController(...)
        self._flow_logger = FlowLogger(f"{phone_name}_tiktok", log_dir="tiktok_flow_analysis")

    def post(self, video_path, caption, max_steps=30):
        # 1. Upload video to phone
        self._upload_video(video_path)

        # 2. Open TikTok
        self.adb("am force-stop com.zhiliaoapp.musically")
        self.adb("monkey -p com.zhiliaoapp.musically 1")
        time.sleep(5)

        # 3. Initialize hybrid navigator
        navigator = TikTokHybridNavigator(
            detector=TikTokScreenDetector(),
            engine=TikTokActionEngine(caption=caption),
            ai_analyzer=self._analyzer if use_hybrid else None
        )

        # 4. Vision-action loop (same as Instagram)
        for step in range(max_steps):
            elements, raw_xml = self.dump_ui()

            # Check for errors
            error_type, error_msg = self._detect_error_state(elements)
            if error_type:
                return False

            # Navigate
            nav_result = navigator.navigate(elements)
            action = nav_result.action

            # Log step
            self._flow_logger.log_step(elements, action, ai_called=nav_result.used_ai)

            # Execute action
            if action.action_type == ActionType.SUCCESS:
                return True
            elif action.action_type == ActionType.ERROR:
                return False
            else:
                self._execute_action(action, elements)

            time.sleep(1)

        return False
```

## Implementation Phases

### Phase 1: Data Collection (1-2 hours)

**Goal:** Capture TikTok UI dumps to validate detection rules.

1. Create minimal `tiktok_poster_ai_only.py`:
   - Copy `post_reel_smart.py` structure
   - Change package to `com.zhiliaoapp.musically`
   - Use 100% AI mode (no hybrid)
   - Log every screen to `tiktok_flow_analysis/`

2. Run 5-10 test posts manually:
   - Accounts: `themotivationmischief`, `talkingsquidbaby`, etc.
   - Capture all screen transitions
   - Note any popups or edge cases

### Phase 2: Screen Mapping (2-3 hours)

**Goal:** Document all TikTok screen types and their markers.

1. Analyze flow logs from Phase 1
2. Document each screen type:
   - Key element IDs
   - Key text markers
   - Key desc markers
3. Create `TIKTOK_SCREEN_REFERENCE.md`

### Phase 3: Build Hybrid Components (2-3 hours)

**Goal:** Create the 4 TikTok files.

1. `tiktok_screen_detector.py`:
   - Copy `screen_detector.py` structure
   - Implement TikTok detection rules

2. `tiktok_action_engine.py`:
   - Copy `action_engine.py` structure
   - Implement TikTok handlers

3. `tiktok_hybrid_navigator.py`:
   - Copy `hybrid_navigator.py`
   - Change imports to TikTok versions

4. `tiktok_poster.py`:
   - Copy `post_reel_smart.py` pattern
   - Use TikTok hybrid navigator

### Phase 4: Test & Iterate (2-3 hours)

**Goal:** Achieve 90%+ success rate.

1. Run hybrid-only (no AI fallback) to expose rule gaps
2. Add missing detection rules
3. Add missing action handlers
4. Repeat until 10+ consecutive successes

### Phase 5: Integration (1 hour)

**Goal:** Separate orchestration for TikTok.

1. Create `tiktok_orchestrator.py`:
   - Copy `parallel_orchestrator.py` pattern
   - Point to TikTok poster
   - Separate progress tracking

2. Usage:
   ```bash
   # Instagram (unchanged)
   python parallel_orchestrator.py --campaign podcast --workers 5

   # TikTok (separate)
   python tiktok_orchestrator.py --campaign tiktok --workers 3
   ```

## Critical Constraints

1. **DO NOT MODIFY** any existing Instagram files
2. **CREATE NEW FILES** for all TikTok code
3. **REUSE SHARED UTILITIES** (flow_logger, appium_ui_controller, etc.)
4. **SEPARATE ORCHESTRATION** - TikTok runs independently from Instagram
5. **TEST STANDALONE FIRST** - Validate TikTok before any integration

## Success Criteria

- 10+ consecutive successful TikTok posts
- 90%+ success rate over 30 posts
- <15% AI fallback rate (85%+ rule-based)
- Zero regressions in Instagram posting
- Separate orchestration working

## Test Accounts

TikTok accounts available for testing:
- `themotivationmischief`
- `talkingsquidbaby`
- `calknowsbestsometimes`
- `inspirebanana`
- `glowingscarlets`
- `crookedwafflezing`

## Estimated Effort

| Phase | Hours |
|-------|-------|
| Phase 1: AI-only poster + test runs | 1-2 |
| Phase 2: Screen mapping | 2-3 |
| Phase 3: Build hybrid components | 2-3 |
| Phase 4: Test & iterate | 2-3 |
| Phase 5: Separate orchestrator | 1 |
| **Total** | **8-12 hours** |

## Files to Create

```
tiktok_screen_detector.py      # ~400 lines (detection rules)
tiktok_action_engine.py        # ~300 lines (action handlers)
tiktok_hybrid_navigator.py     # ~150 lines (coordinator)
tiktok_poster.py               # ~400 lines (main poster)
tiktok_orchestrator.py         # ~200 lines (parallel execution)
```

## Files to Reuse (No Modification)

```
flow_logger.py                 # Same logging
appium_ui_controller.py        # Same tap/type/swipe
device_connection.py           # Same device connection
geelark_client.py              # Same Geelark API
config.py                      # Same configuration
appium_server_manager.py       # Same Appium lifecycle
```
