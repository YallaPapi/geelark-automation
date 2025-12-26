# PRD: TikTok ID Volatility Handling

## Problem Statement

TikTok's Android app uses obfuscated resource IDs that change across versions. The current automation hard-codes specific IDs (e.g., `mkn`, `lxd`, `fpj`) which break when TikTok updates. We need to treat IDs as hints, not single points of failure.

## Requirements

### 1. Multi-Signal Detection (Not ID-Only)

For each TikTok screen (`HOME_FEED`, `CREATE_MENU`, `GALLERY_PICKER`, `VIDEO_EDITOR`, `CAPTION_SCREEN`, `POST_SUCCESS`), detection must combine:

- **Visible texts**: e.g. "Add sound", "Next", "Post", duration labels like "10m", "60s", "15s"
- **Content-desc**: where available (e.g., desc='Create', desc='Post')
- **View class names**: `Button`, `ImageView`, `TextView`, `EditText`
- **Relative position**: e.g. "bottom-right thumbnail in camera view", "top-right button"
- **Resource IDs**: when present for the current build (as hints, not requirements)

`tiktok_screen_detector.py` should never rely on a single resource ID as the only criterion.

### 2. ID Abstraction Layer

Create `tiktok_id_map.py` with a semantic mapping structure:

```python
# Semantic element -> detection strategies
ELEMENT_MAP = {
    "home_create_button": {
        "ids": ["mkn", "lxd"],  # GrapheneOS, Geelark
        "desc": ["Create"],
        "text": [],
        "class": "Button",
        "position": "bottom_center",  # Navigation bar area
    },
    "camera_gallery_thumb": {
        "ids": ["r3r", "ymg", "c_u"],
        "desc": [],
        "text": [],
        "class": "ImageView",
        "position": "bottom_left",  # Left side of camera screen
    },
    "editor_next_button": {
        "ids": ["ntq", "ntn"],
        "desc": [],
        "text": ["Next"],
        "class": "Button",
        "position": "bottom_right",
    },
    "caption_description_field": {
        "ids": ["fpj", "g19"],
        "desc": [],
        "text": ["description", "views"],
        "class": "EditText",
        "position": "top_half",
    },
    "caption_post_button": {
        "ids": ["pwo", "pvz", "pvl", "qrb"],
        "desc": ["Post"],
        "text": ["Post"],
        "class": "Button",
        "position": "bottom_right",
    },
}
```

### 3. Graceful Degradation

When a known ID is missing:

1. Log a warning: "ID for X not found; falling back to text/position-based detection"
2. Attempt alternative strategies in order:
   - Find element by text match
   - Find element by desc match
   - Find element by class + region (e.g., bottom 15% of screen)
3. Only hard-fail when ALL strategies fail

### 4. Version Drift Handling

- Log TikTok app version at start of each run using `adb shell dumpsys package com.zhiliaoapp.musically | grep versionName`
- On detection/action failures, include:
  - App version
  - Current XML snippets
  - Which strategies were attempted
- This data helps quickly adapt mappings for new builds

### 5. Element Finder Utility

Create a reusable `find_element()` function that:

```python
def find_element(elements: List[Dict], semantic_key: str, screen_bounds: Tuple[int, int] = (1080, 2400)) -> Optional[Tuple[int, Dict]]:
    """
    Find element using multi-signal detection.

    Returns (index, element) or None if not found.
    Tries: IDs -> desc -> text -> class+position
    """
```

### 6. Testing Discipline

When TikTok updates:
1. Run an AI-only mapping session to collect new IDs
2. Update `tiktok_id_map.py` with new IDs
3. Keep text/position rules intact (they're more stable)

## Files to Modify

1. **NEW: `tiktok_id_map.py`** - Semantic element mappings
2. **MODIFY: `tiktok_screen_detector.py`** - Use multi-signal detection
3. **MODIFY: `tiktok_action_engine.py`** - Use find_element() utility
4. **MODIFY: `tiktok_poster.py`** - Log TikTok version at startup

## Success Criteria

- Screen detection works even when specific IDs are missing
- Action handlers fall back gracefully to text/position
- TikTok version is logged for debugging
- No hard-coded ID-only checks remain
