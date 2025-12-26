# PRD: TikTok Hybrid Navigation Fix - Multi-Device Support

## Problem Statement

The TikTok hybrid navigation system works on Geelark but fails on GrapheneOS. The root cause is that TikTok uses obfuscated IDs (`fpj`, `lxd`, `mkn`) that change between app versions, unlike Instagram which uses stable semantic IDs (`gallery_grid_item_thumbnail`, `share_button`).

The previous fix attempt broke Geelark by:
1. Using position-based fallbacks in screen DETECTION (caused false positives)
2. Changing detection priority order
3. Treating volatile IDs as primary signals instead of text/desc

## Solution Overview

Mirror Instagram's working architecture:
- **Detection**: TEXT/DESC primary, IDs as confidence boosters only
- **Action**: ID → desc → text → device-specific coordinates (last resort)
- **No position-based detection** - only coordinate fallbacks in action engine

## Requirements

### 1. Reorganize tiktok_id_map.py by TikTok Version

Current structure is flat. Need version-aware structure:

```python
TIKTOK_ID_VERSIONS = {
    "35": {  # Geelark TikTok version
        "caption_field": ["fpj"],
        "post_button": ["pwo", "pvz", "pvl"],
        "create_button": ["lxd"],
        "home_nav": ["lxg"],
        "gallery_thumb": ["c_u", "r3r"],
        "next_button": ["ntq", "ntn"],
    },
    "43": {  # GrapheneOS TikTok version
        "caption_field": ["g19", "g1c"],
        "post_button": ["qrb"],
        "create_button": ["mkn"],
        "gallery_thumb": ["ymg"],
    },
}

def get_all_known_ids(element: str) -> List[str]:
    """Get ALL known IDs for an element across all versions."""
    # Used when version is unknown or for broad matching

def get_ids_for_version(version: str, element: str) -> List[str]:
    """Get IDs specific to a TikTok version."""
```

### 2. Fix tiktok_screen_detector.py - Text/Desc Primary

Refactor ALL detection methods to follow this pattern:

```python
def _detect_caption_screen(self, elements, texts, descs, all_text):
    score = 0.0
    found = []

    # PRIMARY: Text-based detection (stable across versions)
    if any(t in all_text for t in ['description', 'add description', 'describe your video']):
        score += 0.35
        found.append('description_text')

    if 'post' in texts:  # Exact match in text list
        score += 0.30
        found.append('post_button_text')

    # SECONDARY: Desc-based detection
    if any('post' in d.lower() for d in descs):
        score += 0.20
        found.append('post_desc')

    # TERTIARY: ID-based boost (NOT primary signal)
    known_caption_ids = get_all_known_ids('caption_field')
    known_post_ids = get_all_known_ids('post_button')

    if self._has_any_id(elements, known_caption_ids):
        score += 0.10
        found.append('caption_id_boost')

    if self._has_any_id(elements, known_post_ids):
        score += 0.10
        found.append('post_id_boost')

    # NO POSITION-BASED DETECTION
    return min(score, 0.95), found
```

Key screens to fix:
- `_detect_home_feed()` - look for "For You", "Following", create button desc
- `_detect_create_menu()` - look for "Photo", "Text", duration options as TEXT
- `_detect_gallery_picker()` - look for "Recents", "Next", video durations
- `_detect_video_editor()` - look for "Next", "Add sound", effects
- `_detect_caption_screen()` - look for "description", "Post" button

### 3. Fix tiktok_action_engine.py - Device-Aware Coordinates

Add device type parameter and device-specific coordinate fallbacks:

```python
class TikTokActionEngine:
    # Device-specific screen sizes and coordinates
    DEVICE_COORDS = {
        "geelark": {
            "screen_size": (720, 1280),
            "create_button_fallback": (360, 1200),
            "gallery_thumb_fallback": (120, 400),
            "next_button_fallback": (650, 100),
            "post_button_fallback": (650, 100),
        },
        "grapheneos": {
            "screen_size": (1080, 2400),
            "create_button_fallback": (540, 2300),
            "gallery_thumb_fallback": (180, 600),
            "next_button_fallback": (900, 2250),
            "post_button_fallback": (900, 2250),
        },
    }

    def __init__(self, caption: str = "", device_type: str = "geelark"):
        self.device_type = device_type
        self.coords = self.DEVICE_COORDS.get(device_type, self.DEVICE_COORDS["geelark"])
```

Action handlers should try in order:
1. Find by ANY known ID (all versions)
2. Find by desc match
3. Find by text match
4. Device-specific coordinate fallback

### 4. Add _has_any_id() Helper Method

```python
def _has_any_id(self, elements: List[Dict], id_list: List[str]) -> bool:
    """Check if any element has any of the given IDs."""
    element_ids = {el.get('id', '') for el in elements}
    return bool(element_ids & set(id_list))
```

### 5. Update tiktok_poster.py - Pass Device Type

```python
# In post() method, pass device_type to action engine
self.action_engine = TikTokActionEngine(
    caption=caption,
    device_type=self.device_type  # "geelark" or "grapheneos"
)
```

### 6. Preserve Detection Order

The detection order in tiktok_screen_detector.py MUST remain:
```python
self.rules = [
    ('CAPTION_SCREEN', ...),
    ('VIDEO_EDITOR', ...),
    ('GALLERY_PICKER', ...),
    ('CREATE_MENU', ...),
    ('HOME_FEED', ...),  # HOME_FEED must be AFTER CREATE_MENU
]
```

Do NOT change this order - it was carefully tuned for Geelark.

## Success Criteria

1. **Geelark still works** - Run full posting test, must succeed
2. **GrapheneOS works** - Run full posting test, must succeed
3. **No position-based detection** - grep for position checks in detector, should be zero
4. **All IDs are version-organized** - tiktok_id_map.py has version structure
5. **Device-aware coordinates** - action engine uses device-specific fallbacks

## Files to Modify

1. `tiktok_id_map.py` - Reorganize by version, add helper functions
2. `tiktok_screen_detector.py` - Text/desc primary, IDs as boost
3. `tiktok_action_engine.py` - Add device_type, device-specific coords
4. `tiktok_poster.py` - Pass device_type to action engine

## Testing Plan

1. After each file change, run syntax check: `python -m py_compile <file>`
2. After all changes, test Geelark first (must not break)
3. Then test GrapheneOS
4. If either fails, capture error logs and iterate

## Anti-Patterns to Avoid

1. **NO position-based detection** - causes false positives
2. **NO ID-only detection** - IDs change between versions
3. **NO changing detection order** - breaks carefully tuned priorities
4. **NO device-specific detection** - detection should be universal, only actions are device-specific
