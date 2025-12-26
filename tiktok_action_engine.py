"""
TikTokActionEngine - Deterministic action selection for TikTok posting.

Part of the TikTok Hybrid Posting System.
Knows what action to take for each screen type during video posting flow.

IMPORTANT: Actions use version-aware IDs from tiktok_id_map.py.
Coordinate fallbacks are device-specific (Geelark 720x1280 vs GrapheneOS 1080x2400).

Based on flow logs collected 2024-12-24 from AI-only test runs.
Updated 2024-12-26 for multi-device support (Geelark + GrapheneOS).
"""
from enum import Enum, auto
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from tiktok_screen_detector import TikTokScreenType
from tiktok_id_map import get_all_known_ids, get_fallback_coords, get_screen_size


class ActionType(Enum):
    """Types of actions that can be taken."""
    TAP = auto()           # Tap an element
    TAP_COORDINATE = auto() # Tap at specific coordinates
    TYPE_TEXT = auto()     # Type text into focused element
    SWIPE = auto()         # Swipe gesture
    WAIT = auto()          # Wait for transition
    PRESS_KEY = auto()     # Press a key (back, home, etc.)
    SUCCESS = auto()       # Posting completed successfully
    NEED_AI = auto()       # Need AI to decide (fallback)
    ERROR = auto()         # Unrecoverable error state


@dataclass
class Action:
    """Represents an action to take."""
    action_type: ActionType
    target_element: Optional[int] = None  # Element index to tap
    target_text: Optional[str] = None     # Text to find and tap
    text_to_type: Optional[str] = None    # Text to type
    coordinates: Optional[Tuple[int, int]] = None  # (x, y) for tap
    swipe_direction: Optional[str] = None  # up, down, left, right
    wait_seconds: float = 0.5
    reason: str = ""
    confidence: float = 1.0


class TikTokActionEngine:
    """Determines what action to take based on screen type and state."""

    def __init__(self, caption: str = "", video_selected: bool = False,
                 caption_entered: bool = False, device_type: str = "geelark"):
        """Initialize with posting state.

        Args:
            caption: The caption to post with the video.
            video_selected: Whether a video has been selected.
            caption_entered: Whether the caption has been entered.
            device_type: "geelark" or "grapheneos" - determines coordinate fallbacks.
        """
        self.caption = caption
        self.video_selected = video_selected
        self.caption_entered = caption_entered
        self.device_type = device_type
        self.screen_size = get_screen_size(device_type)
        # Track if we've already tapped the Videos tab filter
        self.videos_tab_selected = False

        # Build action handlers for each screen type
        self.handlers = {
            TikTokScreenType.HOME_FEED: self._handle_home_feed,
            TikTokScreenType.CREATE_MENU: self._handle_create_menu,
            TikTokScreenType.GALLERY_PICKER: self._handle_gallery_picker,
            TikTokScreenType.VIDEO_EDITOR: self._handle_video_editor,
            TikTokScreenType.CAPTION_SCREEN: self._handle_caption_screen,
            TikTokScreenType.UPLOAD_PROGRESS: self._handle_upload_progress,
            TikTokScreenType.SUCCESS: self._handle_success,
            TikTokScreenType.POPUP_PERMISSION: self._handle_permission_popup,
            TikTokScreenType.POPUP_DISMISSIBLE: self._handle_dismissible_popup,
            TikTokScreenType.LOGIN_REQUIRED: self._handle_login_required,
            TikTokScreenType.ACCOUNT_BANNED: self._handle_banned,
            TikTokScreenType.ACCOUNT_SUSPENDED: self._handle_suspended,
            TikTokScreenType.CAPTCHA: self._handle_captcha,
            TikTokScreenType.RESTRICTION: self._handle_restriction,
            TikTokScreenType.UNKNOWN: self._handle_unknown,
        }

    def get_action(self, screen_type: TikTokScreenType, elements: List[Dict]) -> Action:
        """Get the appropriate action for the current screen.

        Args:
            screen_type: Detected screen type from TikTokScreenDetector.
            elements: UI elements from dump_ui().

        Returns:
            Action to take.
        """
        handler = self.handlers.get(screen_type, self._handle_unknown)
        return handler(elements)

    def update_state(self, video_selected: bool = None, caption_entered: bool = None,
                     videos_tab_selected: bool = None):
        """Update posting state flags."""
        if video_selected is not None:
            self.video_selected = video_selected
        if caption_entered is not None:
            self.caption_entered = caption_entered
        if videos_tab_selected is not None:
            self.videos_tab_selected = videos_tab_selected

    def _find_element_by_any_id(self, elements: List[Dict], element_key: str) -> Optional[Tuple[int, Dict]]:
        """Find element matching any known ID for the element key.

        Args:
            elements: UI elements from dump_ui()
            element_key: Key from tiktok_id_map (e.g., 'create_button', 'post_button')

        Returns:
            Tuple of (index, element) or None if not found.
        """
        known_ids = get_all_known_ids(element_key)
        for i, el in enumerate(elements):
            if el.get('id', '') in known_ids:
                return i, el
        return None

    def _get_fallback_coords(self, element_key: str) -> Tuple[int, int]:
        """Get device-specific fallback coordinates for an element.

        Args:
            element_key: Key from tiktok_id_map (e.g., 'create_button', 'post_button')

        Returns:
            (x, y) coordinates appropriate for the device type.
        """
        coords = get_fallback_coords(self.device_type, element_key)
        if coords:
            return coords
        # Default to center of screen if not defined
        return (self.screen_size[0] // 2, self.screen_size[1] // 2)

    # ==================== Screen Handlers ====================

    def _handle_home_feed(self, elements: List[Dict]) -> Action:
        """Handle TikTok home feed - tap Create button.

        Uses version-aware IDs from tiktok_id_map:
        - v35 (Geelark): id='lxd' with desc='Create'
        - v43 (GrapheneOS): id='mkn' with desc='Create'
        """
        # Primary: Find Create button by any known ID
        result = self._find_element_by_any_id(elements, 'create_button')
        if result:
            i, el = result
            desc = el.get('desc', '').lower()
            if 'create' in desc:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason=f"Tap Create button (id='{el.get('id')}', desc='Create')",
                    confidence=0.98
                )

        # Secondary: Find by desc only
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            if desc == 'create':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Create button (desc match)",
                    confidence=0.9
                )

        # Tertiary: Device-specific coordinate fallback
        coords = self._get_fallback_coords('create_button')
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=coords,
            reason=f"Tap Create button ({self.device_type} coords: {coords})",
            confidence=0.7
        )

    def _handle_create_menu(self, elements: List[Dict]) -> Action:
        """Handle camera/create menu - tap gallery thumbnail to upload video.

        The gallery thumbnail is in the BOTTOM-LEFT corner of the camera screen.
        It shows a preview of the most recent photo/video.

        Uses version-aware IDs from tiktok_id_map:
        - v35 (Geelark): id='c_u' - Gallery thumbnail
        - v43 (GrapheneOS): id='ymg' - Gallery thumbnail (r3r is RECORD button!)
        """
        import re

        # Primary: Find gallery thumbnail by any known ID
        result = self._find_element_by_any_id(elements, 'gallery_thumb')
        if result:
            i, el = result
            # Verify it's in the bottom-left area (not center where record button is)
            bounds = el.get('bounds', '')
            if bounds:
                match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    x1, y1, x2, y2 = map(int, match.groups())
                    center_x = (x1 + x2) // 2
                    # On TikTok camera, gallery is on LEFT side (x < 300 for 1080 wide screen)
                    if center_x < self.screen_size[0] * 0.3:
                        return Action(
                            action_type=ActionType.TAP,
                            target_element=i,
                            reason=f"Tap gallery thumbnail (id='{el.get('id')}') to select video",
                            confidence=0.95
                        )

        # Secondary: Look for clickable element in bottom-left corner
        # Gallery thumbnail is typically a square in the bottom-left
        for i, el in enumerate(elements):
            if not el.get('clickable'):
                continue
            bounds = el.get('bounds', '')
            if bounds:
                match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    x1, y1, x2, y2 = map(int, match.groups())
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
                    width = x2 - x1
                    height = y2 - y1
                    # Gallery thumbnail: bottom-left, roughly square, reasonable size
                    is_left = center_x < self.screen_size[0] * 0.25
                    is_bottom = center_y > self.screen_size[1] * 0.7
                    is_square = 0.7 < (width / max(height, 1)) < 1.4
                    is_reasonable_size = 50 < width < 300
                    if is_left and is_bottom and is_square and is_reasonable_size:
                        return Action(
                            action_type=ActionType.TAP,
                            target_element=i,
                            reason=f"Tap gallery thumbnail (bottom-left, {width}x{height})",
                            confidence=0.85
                        )

        # Tertiary: Device-specific coordinate fallback for bottom-left corner
        # TikTok gallery thumbnail is in bottom-left of camera screen
        if self.device_type == "grapheneos":
            # 1080x2400 screen: gallery is around (100, 1850)
            coords = (100, 1850)
        else:
            # 720x1280 screen: gallery is around (80, 1100)
            coords = (80, 1100)
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=coords,
            reason=f"Tap gallery thumbnail ({self.device_type} bottom-left: {coords})",
            confidence=0.7
        )

    def _handle_gallery_picker(self, elements: List[Dict]) -> Action:
        """Handle gallery picker - FIRST tap Videos tab, THEN select video, THEN tap Next.

        Uses version-aware IDs from tiktok_id_map:
        - gallery_next: v35='tvr', v43='tvr' (same)
        - recents_tab: v35='x4d', etc.
        - duration_label: v35='faj', etc.
        - video_checkbox: v35='gvi', etc.

        CRITICAL FIX (2024-12-26):
        The gallery opens on "All" by default showing photos AND videos.
        We MUST tap "Videos" tab FIRST to filter out photos, otherwise we'll
        tap a photo thumbnail instead of the uploaded video.

        Flow:
        1. Tap "Videos" tab to filter gallery (if not done yet)
        2. Select a video thumbnail (must have duration label MM:SS)
        3. Tap "Next" to proceed
        """
        import re

        # Helper to get all texts in lowercase for searching
        all_texts = [el.get('text', '').lower() for el in elements]

        # STEP 1: If video is already selected, just tap Next
        if self.video_selected:
            result = self._find_element_by_any_id(elements, 'gallery_next')
            if result:
                i, el = result
                if el.get('text', '').lower() == 'next':
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason=f"Tap Next button (id='{el.get('id')}') - video already selected",
                        confidence=0.98
                    )
            # Fallback: Find by text
            for i, el in enumerate(elements):
                if el.get('text', '').lower() == 'next':
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason="Tap Next button (text match) - video already selected",
                        confidence=0.95
                    )

        # STEP 2: Tap "Videos" tab FIRST to filter out photos
        # This is CRITICAL - otherwise we tap photos instead of videos!
        if not self.videos_tab_selected:
            print(f"  [ACTION] Looking for 'Videos' tab to filter gallery...")
            # Look for "Videos" tab element
            for i, el in enumerate(elements):
                text = el.get('text', '').lower().strip()
                # Match exactly "videos" (the tab filter)
                if text == 'videos':
                    self.videos_tab_selected = True
                    print(f"  [ACTION] Found 'Videos' tab at element {i}, tapping to filter out photos")
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason="Tap 'Videos' tab to filter gallery (CRITICAL: filters out photos)",
                        confidence=0.98
                    )

            # If we can't find "Videos" tab by text, try by position
            # On TikTok gallery, tabs are usually: All | Videos | Photos | Live Photos
            # Look for clickable elements in the tab bar area (top of gallery)
            tab_candidates = []
            for i, el in enumerate(elements):
                if el.get('clickable'):
                    bounds = el.get('bounds', '')
                    if bounds:
                        match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                        if match:
                            x1, y1, x2, y2 = map(int, match.groups())
                            # Tab bar is near the top, below header
                            # Typically y is between 100-250 on a 2400 tall screen
                            if y1 < self.screen_size[1] * 0.15:
                                text = el.get('text', '').lower()
                                tab_candidates.append((i, x1, text))

            # Sort by x position (left to right)
            tab_candidates.sort(key=lambda x: x[1])

            # "Videos" is usually the second tab (after "All" or "Recents")
            if len(tab_candidates) >= 2:
                # Tap the second tab
                second_tab_idx = tab_candidates[1][0]
                self.videos_tab_selected = True
                return Action(
                    action_type=ActionType.TAP,
                    target_element=second_tab_idx,
                    reason="Tap second tab (likely 'Videos') to filter gallery",
                    confidence=0.75
                )

            # Fallback: If only one or no tabs found, assume videos are already shown
            # or tap coordinate where Videos tab usually is
            if self.device_type == "grapheneos":
                # Videos tab is roughly at x=300 on 1080 wide screen
                coords = (300, 150)
            else:
                coords = (200, 120)

            self.videos_tab_selected = True
            return Action(
                action_type=ActionType.TAP_COORDINATE,
                coordinates=coords,
                reason=f"Tap 'Videos' tab area ({self.device_type} coords: {coords})",
                confidence=0.6
            )

        # STEP 3: Videos tab is selected, now find and tap a VIDEO thumbnail
        # Videos have duration labels (MM:SS format) - photos don't!
        print(f"  [ACTION] Videos tab selected, now looking for video thumbnails with duration labels...")

        # First, collect video durations to identify which thumbnails have videos
        video_positions = []
        duration_ids = get_all_known_ids('duration_label')
        for i, el in enumerate(elements):
            text = el.get('text', '')
            # Duration format: MM:SS or M:SS (e.g., "0:15", "1:30", "10:45")
            if re.match(r'^\d{1,2}:\d{2}$', text.strip()):
                bounds = el.get('bounds', '')
                if bounds:
                    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if match:
                        x1, y1, x2, y2 = map(int, match.groups())
                        # Duration label is typically in bottom-right of thumbnail
                        # Calculate thumbnail center (left and up from duration label)
                        scale = self.screen_size[0] / 720.0
                        thumb_center_x = x1 - int(80 * scale)
                        thumb_center_y = y1 - int(100 * scale)
                        video_positions.append((i, thumb_center_x, thumb_center_y, text.strip()))

        # If we found videos by duration label, tap the first one
        if video_positions:
            print(f"  [ACTION] Found {len(video_positions)} video(s) with duration labels: {[v[3] for v in video_positions]}")
            # Get the first video's position
            _, x, y, duration = video_positions[0]
            self.video_selected = True
            print(f"  [ACTION] Tapping video at ({x}, {y}) with duration {duration}")
            return Action(
                action_type=ActionType.TAP_COORDINATE,
                coordinates=(x, y),
                reason=f"Tap video thumbnail with duration {duration}",
                confidence=0.92
            )
        else:
            print(f"  [ACTION] No duration labels found, will try finding clickable thumbnails...")

        # Secondary: Find clickable thumbnail containers in the video grid
        # After tapping Videos tab, all visible thumbnails should be videos
        for i, el in enumerate(elements):
            if el.get('clickable'):
                bounds = el.get('bounds', '')
                if bounds:
                    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if match:
                        x1, y1, x2, y2 = map(int, match.groups())
                        width = x2 - x1
                        height = y2 - y1
                        # Video thumbnails are roughly square, scale for device
                        min_size = int(180 * (self.screen_size[0] / 720.0))
                        max_size = int(400 * (self.screen_size[0] / 720.0))
                        # Check it's a reasonable thumbnail size and in gallery area
                        if min_size < width < max_size and min_size < height < max_size:
                            # Must be in gallery area (below tabs, above bottom bar)
                            gallery_min_y = int(200 * (self.screen_size[1] / 1280.0))
                            gallery_max_y = int(1200 * (self.screen_size[1] / 1280.0))
                            if gallery_min_y < y1 < gallery_max_y:
                                self.video_selected = True
                                return Action(
                                    action_type=ActionType.TAP,
                                    target_element=i,
                                    reason=f"Tap video thumbnail ({width}x{height}) in Videos tab",
                                    confidence=0.85
                                )

        # Tertiary: Find video checkbox as fallback
        result = self._find_element_by_any_id(elements, 'video_checkbox')
        if result:
            i, el = result
            if el.get('clickable'):
                bounds = el.get('bounds', '')
                if bounds:
                    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if match:
                        _, y1, _, y2 = map(int, match.groups())
                        gallery_max_y = int(1200 * (self.screen_size[1] / 1280.0))
                        if 150 < y1 < gallery_max_y:
                            self.video_selected = True
                            return Action(
                                action_type=ActionType.TAP,
                                target_element=i,
                                reason=f"Tap video selection checkbox (id='{el.get('id')}')",
                                confidence=0.8
                            )

        # Quaternary: Device-specific default coordinate fallback
        # First video thumbnail position (in the Videos tab, first item)
        if self.device_type == "grapheneos":
            # First thumbnail in a 3-column grid on 1080 wide screen
            # Each thumb is ~354px wide, first one centered at ~177px
            coords = (180, 450)  # Adjusted y to be in gallery area
        else:
            coords = (121, 312)  # Original Geelark position
        self.video_selected = True
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=coords,
            reason=f"Tap first video thumbnail ({self.device_type} coords: {coords})",
            confidence=0.65
        )

    def _handle_video_editor(self, elements: List[Dict]) -> Action:
        """Handle sounds/effects editor - tap Next to proceed.

        Uses version-aware IDs from tiktok_id_map:
        - editor_next: v35='ntq'/'ntn', v43='ntq'

        This screen appears after video selection with options for
        sounds, effects, text, etc. We want to skip and proceed.
        """
        # Primary: Find Next button by known ID
        result = self._find_element_by_any_id(elements, 'editor_next')
        if result:
            i, el = result
            return Action(
                action_type=ActionType.TAP,
                target_element=i,
                reason=f"Tap Next button (id='{el.get('id')}') to proceed to caption",
                confidence=0.98
            )

        # Secondary: Find Next button by text/desc
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            desc = el.get('desc', '').lower()
            if text == 'next' or desc == 'next':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Next button to proceed to caption",
                    confidence=0.95
                )

        # Tertiary: Find skip/done button
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text in ['skip', 'done', 'continue']:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason=f"Tap {text} to proceed",
                    confidence=0.85
                )

        # Quaternary: Device-specific coordinate fallback
        coords = self._get_fallback_coords('next_button')
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=coords,
            reason=f"Tap Next button area ({self.device_type} coords: {coords})",
            confidence=0.6
        )

    def _handle_caption_screen(self, elements: List[Dict]) -> Action:
        """Handle caption screen - enter caption and tap Post.

        Uses version-aware IDs from tiktok_id_map:
        - caption_field: v35='fpj', v43='g19'
        - title_field: v43='g1c'
        - post_button: v35='pwo'/'pvz'/'pvl', v43='qrb'
        """
        # STEP 1: Enter caption if not done yet
        if not self.caption_entered and self.caption:
            # Primary: Find description field by any known ID
            result = self._find_element_by_any_id(elements, 'caption_field')
            if result:
                i, el = result
                return Action(
                    action_type=ActionType.TYPE_TEXT,
                    target_element=i,
                    text_to_type=self.caption,
                    reason=f"Type caption into description field (id='{el.get('id')}')",
                    confidence=0.98
                )

            # Secondary: Try title field (GrapheneOS v43 uses this)
            result = self._find_element_by_any_id(elements, 'title_field')
            if result:
                i, el = result
                return Action(
                    action_type=ActionType.TYPE_TEXT,
                    target_element=i,
                    text_to_type=self.caption,
                    reason=f"Type caption into title field (id='{el.get('id')}')",
                    confidence=0.95
                )

            # Tertiary: Look for description input field by text
            for i, el in enumerate(elements):
                text = el.get('text', '').lower()
                desc = el.get('desc', '').lower()
                if ('describe' in text or 'describe' in desc or
                    'caption' in text or 'caption' in desc or
                    'add a description' in text or 'add description' in text or
                    'title' in text):
                    return Action(
                        action_type=ActionType.TYPE_TEXT,
                        target_element=i,
                        text_to_type=self.caption,
                        reason="Type caption into description field (text match)",
                        confidence=0.9
                    )

        # STEP 2: Tap Post button
        # Primary: Post button by any known ID
        result = self._find_element_by_any_id(elements, 'post_button')
        if result:
            i, el = result
            text = el.get('text', '').lower()
            desc = el.get('desc', '').lower()
            if 'post' in text or 'post' in desc or el.get('id'):
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason=f"Tap Post button (id='{el.get('id')}')",
                    confidence=0.98
                )

        # Secondary: Post button by text
        for i, el in enumerate(elements):
            text = el.get('text', '').strip().lower()
            if text == 'post':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Post button (text match)",
                    confidence=0.95
                )

        # Tertiary: Look for Post by desc
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            if desc == 'post':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Post button (desc match)",
                    confidence=0.9
                )

        # Quaternary: Device-specific coordinate fallback
        coords = self._get_fallback_coords('post_button')
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=coords,
            reason=f"Tap Post button area ({self.device_type} coords: {coords})",
            confidence=0.6
        )

    def _handle_upload_progress(self, elements: List[Dict]) -> Action:
        """Handle upload progress - wait for completion."""
        return Action(
            action_type=ActionType.WAIT,
            wait_seconds=2.0,
            reason="Waiting for video to upload",
            confidence=0.9
        )

    def _handle_success(self, elements: List[Dict]) -> Action:
        """Handle success - posting complete."""
        return Action(
            action_type=ActionType.SUCCESS,
            reason="Video posted successfully",
            confidence=1.0
        )

    # ==================== Popup Handlers ====================

    def _handle_permission_popup(self, elements: List[Dict]) -> Action:
        """Handle permission popup - grant permission.

        Key elements from flow logs:
        - id='permission_allow_foreground_only_button' - "WHILE USING THE APP"
        - id='permission_allow_button' - "ALLOW" button
        - id='permission_allow_one_time_button' - "ONLY THIS TIME"
        """
        # Primary: Find permission button by specific IDs
        permission_button_ids = [
            'permission_allow_foreground_only_button',  # "WHILE USING THE APP"
            'permission_allow_button',                   # "ALLOW"
            'permission_allow_one_time_button',         # "ONLY THIS TIME"
        ]
        for button_id in permission_button_ids:
            for i, el in enumerate(elements):
                if el.get('id', '') == button_id:
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason=f"Tap permission button (id='{button_id}')",
                        confidence=0.98
                    )

        # Secondary: Look for allow button by exact text match (not partial)
        allow_texts = ['while using the app', 'allow', 'only this time']
        for i, el in enumerate(elements):
            text = el.get('text', '').strip().lower()
            if text in allow_texts:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason=f"Tap '{text}' permission button",
                    confidence=0.9
                )

        # Tertiary: Coordinate fallback (middle button position)
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(359, 745),  # ALLOW button position from flow logs
            reason="Tap permission button area (coordinate fallback)",
            confidence=0.7
        )

    def _handle_dismissible_popup(self, elements: List[Dict]) -> Action:
        """Handle dismissible popup - tap dismiss option."""
        # Dismiss keywords - check if any appear in text (substring match)
        dismiss_keywords = [
            'not now', 'skip', 'maybe later', 'dismiss', 'no thanks',
            'cancel', "don't allow", "don't allow", 'deny', 'later', 'close'
        ]

        # Find dismiss button by text (contains check)
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if not text:
                continue
            # Check exact match first
            if text in dismiss_keywords:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason=f"Tap '{el.get('text')}' to dismiss popup",
                    confidence=0.95
                )
            # Check substring match (e.g., "Don't allow" contains "don't allow")
            for keyword in dismiss_keywords:
                if keyword in text:
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason=f"Tap '{el.get('text')}' to dismiss popup",
                        confidence=0.9
                    )

        # Secondary: Check desc
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            for keyword in dismiss_keywords:
                if keyword in desc:
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason=f"Tap dismiss button (desc contains '{keyword}')",
                        confidence=0.85
                    )

        # Fallback: Press back
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to dismiss popup",
            confidence=0.7
        )

    # ==================== Error Handlers ====================

    def _handle_login_required(self, elements: List[Dict]) -> Action:
        """Handle login required - unrecoverable error."""
        return Action(
            action_type=ActionType.ERROR,
            reason="Account logged out - login required",
            confidence=1.0
        )

    def _handle_banned(self, elements: List[Dict]) -> Action:
        """Handle banned account - unrecoverable error."""
        return Action(
            action_type=ActionType.ERROR,
            reason="Account permanently banned",
            confidence=1.0
        )

    def _handle_suspended(self, elements: List[Dict]) -> Action:
        """Handle suspended account - unrecoverable error."""
        return Action(
            action_type=ActionType.ERROR,
            reason="Account suspended",
            confidence=1.0
        )

    def _handle_captcha(self, elements: List[Dict]) -> Action:
        """Handle captcha - needs manual intervention."""
        return Action(
            action_type=ActionType.ERROR,
            reason="Captcha verification required - needs manual intervention",
            confidence=1.0
        )

    def _handle_restriction(self, elements: List[Dict]) -> Action:
        """Handle posting restriction - unrecoverable error."""
        return Action(
            action_type=ActionType.ERROR,
            reason="Posting is restricted for this account",
            confidence=1.0
        )

    def _handle_unknown(self, elements: List[Dict]) -> Action:
        """Handle unknown screen - need AI fallback."""
        return Action(
            action_type=ActionType.NEED_AI,
            reason="Unknown screen - need AI to analyze",
            confidence=0.0
        )


if __name__ == "__main__":
    # Test with sample scenarios
    engine = TikTokActionEngine(caption="Test caption #fyp")

    # Test home feed
    home_elements = [
        {'id': 'lxd', 'desc': 'Create', 'text': '', 'clickable': True},
        {'id': 'lxg', 'desc': 'Home', 'text': '', 'clickable': True},
    ]
    action = engine.get_action(TikTokScreenType.HOME_FEED, home_elements)
    print(f"Home Feed: {action.action_type.name} - {action.reason}")

    # Test permission popup
    perm_elements = [
        {'id': 'permission_message', 'text': 'Allow TikTok to take pictures?', 'desc': ''},
        {'id': 'permission_allow_foreground_only_button', 'text': 'WHILE USING THE APP', 'desc': ''},
    ]
    action = engine.get_action(TikTokScreenType.POPUP_PERMISSION, perm_elements)
    print(f"Permission: {action.action_type.name} - {action.reason}")

    # Test gallery picker
    gallery_elements = [
        {'id': 'x4d', 'text': 'Recents', 'desc': ''},
        {'id': 'tvr', 'text': 'Next', 'desc': ''},
    ]
    action = engine.get_action(TikTokScreenType.GALLERY_PICKER, gallery_elements)
    print(f"Gallery: {action.action_type.name} - {action.reason}")
