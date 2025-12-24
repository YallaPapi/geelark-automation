# Hybrid Navigation System

Rule-based screen detection and action engine that reduces or eliminates AI API calls for Instagram automation.

## Overview

The hybrid navigation system replaces Claude AI for UI navigation with deterministic rule-based logic. This provides:

- **Zero AI costs** when rules handle all screens
- **Faster execution** - no API round-trips
- **Deterministic behavior** - same UI = same action
- **Debuggable flows** - JSONL logs show exact decisions

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     HybridNavigator                             │
├────────────────────────────────────────────────────────────────┤
│  1. Dump UI elements from Appium                               │
│  2. Pass elements to ScreenDetector                            │
│  3. ScreenDetector returns ScreenType + confidence             │
│  4. Pass ScreenType + state to ActionEngine                    │
│  5. ActionEngine returns action dict                           │
│  6. Execute action (tap, type, swipe, etc.)                    │
│  7. If UNKNOWN screen, optionally fall back to Claude AI       │
└────────────────────────────────────────────────────────────────┘
```

## Components

### 1. ScreenDetector

Analyzes UI elements to determine the current screen type.

**File:** `screen_detector.py` (posting), `follow_screen_detector.py` (follow)

```python
from screen_detector import ScreenDetector, ScreenType

detector = ScreenDetector()
screen_type, confidence, details = detector.detect(elements)

# Returns:
# screen_type: ScreenType.HOME_FEED
# confidence: 0.95
# details: {"markers": ["feed_tab", "clips_tab"], "element_index": None}
```

### 2. ActionEngine

Returns the appropriate action based on screen type and current state.

**File:** `action_engine.py` (posting), `follow_action_engine.py` (follow)

```python
from action_engine import ActionEngine

engine = ActionEngine()
action = engine.get_action(
    screen_type=ScreenType.HOME_FEED,
    elements=elements,
    state={"video_uploaded": False, "caption_entered": False}
)

# Returns:
# {"action": "tap", "element_index": 5, "reason": "Tap + button to create"}
```

### 3. HybridNavigator

Coordinates detection and action, with optional AI fallback.

**File:** `hybrid_navigator.py` (posting), `hybrid_follow_navigator.py` (follow)

```python
from hybrid_navigator import HybridNavigator

navigator = HybridNavigator(
    ui_controller=appium_controller,
    ai_analyzer=claude_analyzer,  # Optional, for fallback
    flow_logger=logger
)

action = navigator.get_next_action(
    state={"video_uploaded": True, "caption_entered": False}
)
```

## Screen Types

### Posting Flow (ScreenType)

```python
class ScreenType(Enum):
    HOME_FEED = "home_feed"           # Main Instagram feed
    REELS_TAB = "reels_tab"           # Reels viewing tab
    CREATE_MENU = "create_menu"       # Create content menu
    GALLERY_PICKER = "gallery_picker" # Photo/video picker
    VIDEO_EDITOR = "video_editor"     # Video editing screen
    CAPTION_SCREEN = "caption_screen" # Add caption screen
    SHARING_SCREEN = "sharing_screen" # Share options screen
    POST_COMPLETE = "post_complete"   # Post success confirmation
    POPUP_DISMISSIBLE = "popup"       # Dismissible overlay
    UNKNOWN = "unknown"               # Unrecognized screen
```

### Follow Flow (FollowScreenType)

```python
class FollowScreenType(Enum):
    HOME_FEED = "home_feed"           # Instagram home feed
    EXPLORE_PAGE = "explore_page"     # Search/explore grid
    SEARCH_INPUT = "search_input"     # Search bar focused
    SEARCH_RESULTS = "search_results" # Search results displayed
    TARGET_PROFILE = "target_profile" # User profile page
    FOLLOW_SUCCESS = "follow_success" # Following confirmed
    ABOUT_ACCOUNT_PAGE = "about_page" # Account info page
    REELS_SCREEN = "reels_screen"     # Reels viewing
    POPUP_DISMISSIBLE = "popup"       # Dismissible popup
    UNKNOWN = "unknown"               # Unrecognized
```

## Detection Rules

Screen detection uses element IDs, text content, and UI structure.

### Example: Detecting HOME_FEED

```python
def _detect_home_feed(self, elements, texts, descs, ids, all_text, all_ids, target):
    # Must have bottom nav tabs
    has_tabs = all(tab in all_ids for tab in ['feed_tab', 'clips_tab', 'profile_tab'])

    # Must have Instagram logo or title
    has_logo = 'title_logo' in all_ids or 'instagram' in all_text

    if has_tabs and has_logo:
        return (0.95, ["feed_tab", "clips_tab", "title_logo"], None)

    return (0.0, [], None)
```

### Example: Detecting SEARCH_INPUT

```python
def _detect_search_input(self, elements, ...):
    # Has search bar with placeholder or empty text
    has_search_bar = 'action_bar_search_edit_text' in all_ids
    has_back_button = 'action_bar_button_back' in all_ids

    # Check for placeholder text indicating empty search
    search_bar_empty = False
    for el in elements:
        if el.get('id') == 'action_bar_search_edit_text':
            text = el.get('text', '').lower()
            if 'search' in text or text == '':
                search_bar_empty = True

    if has_search_bar and has_back_button and search_bar_empty:
        # Find search bar index for typing
        idx = self._find_element_index_by_id(elements, 'action_bar_search_edit_text')
        return (0.90, ["search_bar_empty"], idx)

    return (0.0, [], None)
```

## Action Rules

Action engine maps screen types to actions.

### Posting Flow Actions

| Screen Type | Action | Description |
|-------------|--------|-------------|
| HOME_FEED | tap + button | Open create menu |
| CREATE_MENU | tap "Reel" | Select reel creation |
| GALLERY_PICKER | tap video | Select uploaded video |
| VIDEO_EDITOR | tap "Next" | Proceed to caption |
| CAPTION_SCREEN | type caption | Enter post caption |
| CAPTION_SCREEN | tap "Share" | Publish post |
| POST_COMPLETE | success | Flow complete |
| POPUP_DISMISSIBLE | tap dismiss | Close popup |

### Follow Flow Actions

| Screen Type | Action | Description |
|-------------|--------|-------------|
| HOME_FEED | tap search_tab | Open search |
| EXPLORE_PAGE | tap search_bar | Focus search input |
| SEARCH_INPUT | type username | Enter target username |
| SEARCH_RESULTS | tap target row | Open profile |
| TARGET_PROFILE | tap Follow | Follow user |
| FOLLOW_SUCCESS | success | Flow complete |
| POPUP_DISMISSIBLE | tap dismiss | Close popup |

## Flow Logging

All navigation decisions are logged to JSONL for debugging.

**File:** `flow_logger.py`

```python
from flow_logger import FlowLogger

logger = FlowLogger("account_name")

# Log each step
logger.log_step(
    step=1,
    elements=elements,
    screen_type=ScreenType.HOME_FEED,
    action={"action": "tap", "element_index": 5},
    ai_called=False
)

# End session
logger.end_session(success=True, total_steps=5)
```

### Log Output

Logs are written to `flow_analysis/<account>_<timestamp>.jsonl`:

```json
{"event": "session_start", "account": "myaccount", "timestamp": "2025-12-24T10:00:00"}
{"event": "step", "step": 1, "screen_type": "home_feed", "action": {"action": "tap", "element_index": 5}, "ai_called": false}
{"event": "step", "step": 2, "screen_type": "explore_page", "action": {"action": "tap", "element_index": 0}, "ai_called": false}
{"event": "success", "total_steps": 5, "duration_seconds": 12.5}
```

## AI Fallback

When the screen type is UNKNOWN, the navigator can optionally call Claude AI:

```python
navigator = HybridNavigator(
    ui_controller=controller,
    ai_analyzer=claude_analyzer  # Pass None to disable fallback
)
```

### Fallback Behavior

1. ScreenDetector returns `ScreenType.UNKNOWN`
2. HybridNavigator checks if `ai_analyzer` is available
3. If available, call Claude AI with elements
4. Log `ai_called=True` in flow log
5. If not available, return error action

### Disabling AI Fallback

For 100% rule-based operation:

```python
navigator = HybridNavigator(
    ui_controller=controller,
    ai_analyzer=None  # No fallback
)
```

## Confidence Thresholds

Each detection method returns a confidence score (0.0 - 1.0).

| Confidence | Meaning |
|------------|---------|
| 0.95+ | High confidence, proceed |
| 0.80-0.94 | Medium confidence, proceed |
| 0.60-0.79 | Low confidence, may need fallback |
| < 0.60 | UNKNOWN, trigger fallback |

## Adding New Screens

To add detection for a new screen type:

### 1. Add Enum Value

```python
class ScreenType(Enum):
    # ... existing
    NEW_SCREEN = "new_screen"
```

### 2. Add Detection Method

```python
def _detect_new_screen(self, elements, texts, descs, ids, all_text, all_ids, target):
    # Define markers unique to this screen
    has_marker1 = 'unique_element_id' in all_ids
    has_marker2 = 'unique text' in all_text

    if has_marker1 and has_marker2:
        return (0.90, ["marker1", "marker2"], element_index_or_none)

    return (0.0, [], None)
```

### 3. Register in detect()

```python
def detect(self, elements, target=None):
    # ... existing checks

    # Add new screen check
    conf, markers, idx = self._detect_new_screen(...)
    if conf > best_confidence:
        best_screen = ScreenType.NEW_SCREEN
        best_confidence = conf
        best_details = {"markers": markers, "element_index": idx}
```

### 4. Add Action Rule

```python
def get_action(self, screen_type, elements, state):
    if screen_type == ScreenType.NEW_SCREEN:
        return {
            "action": "tap",
            "element_index": self._find_button_index(elements),
            "reason": "Tap button on new screen"
        }
```

## Debugging

### View Flow Logs

```bash
# View latest flow log
cat flow_analysis/*_latest.jsonl | jq .

# Find failed flows
grep '"event": "failure"' flow_analysis/*.jsonl
```

### Test Detection

```python
from screen_detector import ScreenDetector

detector = ScreenDetector()

# Test with sample elements
elements = [{"id": "feed_tab", "text": "", ...}, ...]
screen_type, conf, details = detector.detect(elements)
print(f"Detected: {screen_type} (confidence: {conf})")
```

## Performance Comparison

| Mode | Speed | Cost | Reliability |
|------|-------|------|-------------|
| Pure AI (Claude) | ~2-3s/step | $0.01-0.03/step | High |
| Hybrid (rules + AI fallback) | ~0.1s/step | $0 (usually) | High |
| Pure Rules (no AI) | ~0.1s/step | $0 | Medium-High |

## File Reference

| File | Purpose |
|------|---------|
| `screen_detector.py` | Posting screen type detection |
| `action_engine.py` | Posting action decisions |
| `hybrid_navigator.py` | Posting hybrid coordinator |
| `follow_screen_detector.py` | Follow screen type detection |
| `follow_action_engine.py` | Follow action decisions |
| `hybrid_follow_navigator.py` | Follow hybrid coordinator |
| `flow_logger.py` | JSONL flow logging |
