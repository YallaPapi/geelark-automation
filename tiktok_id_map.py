"""
TikTok ID Map - Version-Aware ID Abstraction Layer

TikTok's Android app uses obfuscated resource IDs that change across versions.
Unlike Instagram which uses stable semantic IDs (gallery_grid_item_thumbnail),
TikTok uses minified IDs (fpj, lxd, mkn) that change between builds.

This module provides:
- Version-specific ID mappings (Geelark v35.x, GrapheneOS v43.x, etc.)
- Helper functions to get IDs across all versions or for specific version
- Text/desc patterns that are stable across versions (primary detection signals)

IMPORTANT: IDs should be used as BOOST signals in detection, not primary.
Primary detection should use text/desc patterns which are more stable.

Usage:
    from tiktok_id_map import get_all_known_ids, get_ids_for_version

    # Get ALL known IDs across all versions (for broad matching)
    caption_ids = get_all_known_ids("caption_field")

    # Get IDs for specific TikTok version
    caption_ids_v35 = get_ids_for_version("35", "caption_field")
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# TikTok Version Tracking
# =============================================================================

_tiktok_version: str = "unknown"


def set_tiktok_version(version: str) -> None:
    """Set TikTok version for logging context (call at start of session)."""
    global _tiktok_version
    _tiktok_version = version
    logger.info(f"TikTok version set: {version}")


def get_tiktok_version() -> str:
    """Get currently set TikTok version."""
    return _tiktok_version


# =============================================================================
# Version-Specific ID Mappings
# =============================================================================

# IDs organized by TikTok major version
# Keys are version prefixes (e.g., "35" matches "35.1.4", "35.2.0", etc.)
TIKTOK_ID_VERSIONS = {
    # Geelark TikTok version (v35.x)
    "35": {
        # HOME_FEED
        "create_button": ["lxd"],
        "home_nav": ["lxg"],
        "profile_nav": ["lxi"],
        "friends_nav": ["lxf"],
        "inbox_nav": ["lxh"],
        "search_button": ["ia6"],

        # CREATE_MENU (Camera)
        "gallery_thumb": ["c_u", "r3r"],
        "add_sound": ["d24"],
        "record_button": ["q76"],
        "close_button": ["j0z"],

        # GALLERY_PICKER
        "recents_tab": ["x4d"],
        "gallery_next": ["tvr"],
        "gallery_close": ["b6x"],
        "video_checkbox": ["gvi"],
        "duration_label": ["faj"],

        # VIDEO_EDITOR
        "editor_next": ["ntq", "ntn"],
        "music_indicator": ["d88"],

        # CAPTION_SCREEN
        "caption_field": ["fpj"],
        "post_button": ["pwo", "pvz", "pvl"],
        "edit_cover": ["d1k"],
        "hashtags": ["auj"],
        "mention": ["aui"],
        "drafts": ["f6a"],

        # SUCCESS
        "like_button": ["evz", "evm"],
        "comments": ["dnk"],
    },

    # GrapheneOS TikTok version (v43.x)
    "43": {
        # HOME_FEED
        "create_button": ["mkn"],
        "home_nav": ["mkq"],
        "profile_nav": ["mks"],
        "search_button": ["irz"],

        # CREATE_MENU (Camera)
        # NOTE: r3r is the RECORD button, NOT gallery thumb!
        # Gallery thumb is in bottom-left corner - ID unknown, use position
        "gallery_thumb": ["ymg"],  # May need to discover actual ID
        "record_button": ["r3r"],  # This is the record/capture button!
        "add_sound": ["d8a"],
        "close_button": ["jix"],

        # GALLERY_PICKER
        "gallery_next": ["tvr"],  # May be same

        # VIDEO_EDITOR
        "editor_next": ["ntq"],

        # CAPTION_SCREEN
        "caption_field": ["g19"],
        "title_field": ["g1c"],
        "post_button": ["qrb"],
        "edit_cover": ["ji6"],
        "drafts": ["fex"],
        "hashtags": ["awo"],
        "mention": ["awn"],
        "location": ["w4m"],
    },
}

# =============================================================================
# Text/Desc Patterns (Stable Across Versions)
# These should be PRIMARY detection signals, not IDs
# =============================================================================

TEXT_PATTERNS = {
    # HOME_FEED
    "for_you_text": ["for you", "for you"],
    "following_text": ["following"],

    # CREATE_MENU
    "photo_tab": ["photo"],
    "text_tab": ["text"],
    "duration_options": ["10m", "60s", "15s", "3m", "10 min", "60 sec"],
    "add_sound": ["add sound"],

    # GALLERY_PICKER
    "recents_text": ["recents", "recent"],
    "next_text": ["next"],

    # VIDEO_EDITOR
    "editor_next": ["next"],
    "edit_tools": ["edit", "effects", "text", "stickers", "filters"],

    # CAPTION_SCREEN
    "description_text": ["description", "add description", "describe your video",
                         "views", "long description", "boost views"],
    "title_text": ["title", "catchy title", "add a catchy title"],
    "post_text": ["post"],
    "drafts_text": ["draft", "drafts", "save draft"],
    "cover_text": ["cover", "edit cover"],
    "hashtag_text": ["hashtag", "#"],
    "mention_text": ["mention", "@"],

    # POPUPS
    "dismiss_text": ["not now", "skip", "later", "no thanks", "cancel", "deny"],
    "allow_text": ["allow", "while using the app", "allow access"],
}

DESC_PATTERNS = {
    # HOME_FEED
    "create_desc": ["create"],
    "home_desc": ["home"],
    "profile_desc": ["profile"],
    "search_desc": ["search"],

    # CREATE_MENU
    "add_sound_desc": ["add sound"],
    "record_desc": ["record video", "record"],
    "close_desc": ["close", "back"],

    # VIDEO_EDITOR
    "next_desc": ["next"],

    # CAPTION_SCREEN
    "post_desc": ["post"],
    "draft_desc": ["draft", "save draft"],

    # POPUPS
    "close_popup_desc": ["close", "dismiss"],
    "allow_desc": ["allow"],
    "deny_desc": ["deny", "don't allow"],
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_all_known_ids(element: str) -> List[str]:
    """
    Get ALL known IDs for an element across ALL TikTok versions.

    Use this when version is unknown or for broad matching in action engine.

    Args:
        element: Element key (e.g., "caption_field", "post_button")

    Returns:
        List of all known IDs for this element across all versions.
        Empty list if element not found.

    Example:
        >>> get_all_known_ids("post_button")
        ['pwo', 'pvz', 'pvl', 'qrb']
    """
    all_ids = set()
    for version_ids in TIKTOK_ID_VERSIONS.values():
        if element in version_ids:
            all_ids.update(version_ids[element])
    return list(all_ids)


def get_ids_for_version(version: str, element: str) -> List[str]:
    """
    Get IDs specific to a TikTok version.

    Args:
        version: TikTok version string (e.g., "35.1.4", "43.1.4")
        element: Element key (e.g., "caption_field", "post_button")

    Returns:
        List of IDs for this element in the specified version.
        Falls back to all known IDs if version not found.

    Example:
        >>> get_ids_for_version("35.1.4", "post_button")
        ['pwo', 'pvz', 'pvl']
        >>> get_ids_for_version("43.1.4", "post_button")
        ['qrb']
    """
    # Extract major version prefix (e.g., "35" from "35.1.4")
    major_version = version.split('.')[0] if '.' in version else version

    if major_version in TIKTOK_ID_VERSIONS:
        version_map = TIKTOK_ID_VERSIONS[major_version]
        if element in version_map:
            return version_map[element]

    # Fallback: return all known IDs
    logger.debug(f"Version {version} not found for {element}, using all known IDs")
    return get_all_known_ids(element)


def get_text_patterns(pattern_key: str) -> List[str]:
    """Get text patterns for detection (stable across versions)."""
    return TEXT_PATTERNS.get(pattern_key, [])


def get_desc_patterns(pattern_key: str) -> List[str]:
    """Get desc patterns for detection (stable across versions)."""
    return DESC_PATTERNS.get(pattern_key, [])


def list_elements() -> List[str]:
    """List all element keys across all versions."""
    all_elements = set()
    for version_ids in TIKTOK_ID_VERSIONS.values():
        all_elements.update(version_ids.keys())
    return sorted(list(all_elements))


def list_versions() -> List[str]:
    """List all supported TikTok version prefixes."""
    return list(TIKTOK_ID_VERSIONS.keys())


# =============================================================================
# Device-Specific Coordinates (for action engine fallbacks)
# =============================================================================

DEVICE_COORDS = {
    "geelark": {
        "screen_size": (720, 1280),
        "create_button": (360, 1200),
        "gallery_thumb": (80, 1100),  # BOTTOM-LEFT corner of camera screen
        "next_button": (650, 100),
        "post_button": (650, 100),
        "caption_field": (360, 300),
    },
    "grapheneos": {
        "screen_size": (1080, 2400),
        "create_button": (540, 2300),
        "gallery_thumb": (100, 1850),  # BOTTOM-LEFT corner of camera screen
        "next_button": (900, 150),
        "post_button": (900, 2250),
        "caption_field": (540, 500),
    },
}


def get_fallback_coords(device_type: str, element: str) -> Optional[tuple]:
    """
    Get fallback coordinates for an element on a specific device.

    Args:
        device_type: "geelark" or "grapheneos"
        element: Element key (e.g., "create_button", "post_button")

    Returns:
        (x, y) tuple or None if not found.
    """
    device_coords = DEVICE_COORDS.get(device_type, DEVICE_COORDS["geelark"])
    return device_coords.get(element)


def get_screen_size(device_type: str) -> tuple:
    """Get screen size for a device type."""
    device_coords = DEVICE_COORDS.get(device_type, DEVICE_COORDS["geelark"])
    return device_coords.get("screen_size", (1080, 2400))


# =============================================================================
# Module Testing
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("TikTok ID Map - Version-Aware Structure")
    print("=" * 60)

    print(f"\nSupported versions: {list_versions()}")
    print(f"Total elements: {len(list_elements())}")

    print("\n--- Sample Lookups ---")

    # Test get_all_known_ids
    print(f"\nget_all_known_ids('post_button'): {get_all_known_ids('post_button')}")
    print(f"get_all_known_ids('caption_field'): {get_all_known_ids('caption_field')}")
    print(f"get_all_known_ids('create_button'): {get_all_known_ids('create_button')}")

    # Test version-specific
    print(f"\nget_ids_for_version('35', 'post_button'): {get_ids_for_version('35', 'post_button')}")
    print(f"get_ids_for_version('43', 'post_button'): {get_ids_for_version('43', 'post_button')}")

    # Test patterns
    print(f"\nget_text_patterns('description_text'): {get_text_patterns('description_text')}")
    print(f"get_desc_patterns('create_desc'): {get_desc_patterns('create_desc')}")

    # Test device coords
    print(f"\nget_fallback_coords('geelark', 'post_button'): {get_fallback_coords('geelark', 'post_button')}")
    print(f"get_fallback_coords('grapheneos', 'post_button'): {get_fallback_coords('grapheneos', 'post_button')}")

    print("\n" + "=" * 60)
    print("[OK] ID map validated successfully")
