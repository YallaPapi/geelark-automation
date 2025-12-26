"""
TikTokActionEngine - Deterministic action selection for TikTok posting.

Part of the TikTok Hybrid Posting System.
Knows what action to take for each screen type during video posting flow.

Based on flow logs collected 2024-12-24 from AI-only test runs.
"""
from enum import Enum, auto
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from tiktok_screen_detector import TikTokScreenType


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
                 caption_entered: bool = False):
        """Initialize with posting state.

        Args:
            caption: The caption to post with the video.
            video_selected: Whether a video has been selected.
            caption_entered: Whether the caption has been entered.
        """
        self.caption = caption
        self.video_selected = video_selected
        self.caption_entered = caption_entered

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

    def update_state(self, video_selected: bool = None, caption_entered: bool = None):
        """Update posting state flags."""
        if video_selected is not None:
            self.video_selected = video_selected
        if caption_entered is not None:
            self.caption_entered = caption_entered

    # ==================== Screen Handlers ====================

    def _handle_home_feed(self, elements: List[Dict]) -> Action:
        """Handle TikTok home feed - tap Create button.

        Key elements from flow logs:
        Geelark: id='lxd' with desc='Create' - Create button in bottom nav
        GrapheneOS v43.1.4: id='mkn' with desc='Create' - Create button in bottom nav
        """
        # Primary: Find Create button by ID (lxd for Geelark, mkn for GrapheneOS v43.1.4)
        for create_id in ['lxd', 'mkn']:
            for i, el in enumerate(elements):
                if el.get('id', '') == create_id:
                    desc = el.get('desc', '').lower()
                    if 'create' in desc:
                        return Action(
                            action_type=ActionType.TAP,
                            target_element=i,
                            reason=f"Tap Create button (id='{create_id}', desc='Create')",
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

        # Tertiary: Coordinate fallback (center bottom)
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(360, 1322),  # Create button position from flow logs
            reason="Tap Create button area (coordinate fallback)",
            confidence=0.7
        )

    def _handle_create_menu(self, elements: List[Dict]) -> Action:
        """Handle camera/create menu - tap gallery to upload video.

        Key elements from flow logs:
        Geelark:
        - id='c_u' - Gallery thumbnail (tap to open gallery)
        - id='q76' with desc='Record video' - Record button (not what we want)

        GrapheneOS v43.1.4:
        - id='r3r' - Gallery thumbnail (center bottom, clickable)
        - id='ymg' - Gallery preview (bottom left)
        """
        # Primary: Find gallery thumbnail by ID
        # Geelark: c_u, GrapheneOS: r3r, ymg
        gallery_ids = ['c_u', 'r3r', 'ymg']
        for gallery_id in gallery_ids:
            for i, el in enumerate(elements):
                if el.get('id', '') == gallery_id and el.get('clickable', False):
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason=f"Tap gallery thumbnail (id='{gallery_id}') to select video",
                        confidence=0.95
                    )

        # Secondary: Find gallery by ID without clickable check
        for gallery_id in gallery_ids:
            for i, el in enumerate(elements):
                if el.get('id', '') == gallery_id:
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason=f"Tap gallery thumbnail (id='{gallery_id}')",
                        confidence=0.9
                    )

        # Tertiary: Find gallery by looking at bottom-left corner elements
        for i, el in enumerate(elements):
            if el.get('id', '') == 'frz':  # Gallery thumbnail containers
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap gallery thumbnail (id='frz')",
                    confidence=0.85
                )

        # Quaternary: Coordinate fallback (gallery thumbnail position)
        # GrapheneOS: gallery is at center-bottom around (540, 1900)
        # Geelark: gallery is at (580, 1165)
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(540, 1900),  # GrapheneOS gallery position from flow logs
            reason="Tap gallery area (coordinate fallback)",
            confidence=0.7
        )

    def _handle_gallery_picker(self, elements: List[Dict]) -> Action:
        """Handle gallery picker - select video and tap Next.

        Key elements from flow logs:
        - id='tvr' with text='Next' - Next button (only works after video is selected)
        - id='x4d' with text='Recents' - Album selector
        - id='faj' - Video duration label (NOT clickable! Just text)
        - id='gvi' - Video selection checkbox (CLICKABLE)
        - id='m65' - Video thumbnail container (not clickable)
        - Clickable thumbnails have no id but are clickable=true

        IMPORTANT: Must tap a video thumbnail FIRST, then tap Next.
        The Next button is present but disabled until a video is selected.
        """
        # STEP 1: If video is already selected, just tap Next
        if self.video_selected:
            for i, el in enumerate(elements):
                if el.get('id', '') == 'tvr':
                    if el.get('text', '').lower() == 'next':
                        return Action(
                            action_type=ActionType.TAP,
                            target_element=i,
                            reason="Tap Next button (id='tvr') - video already selected",
                            confidence=0.98
                        )

        # STEP 2: Need to select a video first
        # Strategy: Find duration labels (faj), then find the CLICKABLE thumbnail nearby

        # First, collect video durations to identify which thumbnails have videos
        video_positions = []
        for i, el in enumerate(elements):
            if el.get('id', '') == 'faj':
                text = el.get('text', '')
                if ':' in text:  # Looks like a duration (MM:SS)
                    bounds = el.get('bounds', '')
                    if bounds:
                        import re
                        match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                        if match:
                            x1, y1, x2, y2 = map(int, match.groups())
                            # Duration is in bottom-right, thumbnail is up and left
                            # Typical thumbnail is 236x238 pixels
                            thumb_center_x = x1 - 80  # Move left from duration label
                            thumb_center_y = y1 - 100  # Move up from duration label
                            video_positions.append((thumb_center_x, thumb_center_y, text))

        # Primary: Find clickable thumbnail containers (no id but clickable, square shape)
        # These are the ACTUAL video thumbnails that select when tapped
        for i, el in enumerate(elements):
            if el.get('clickable') and not el.get('id'):
                bounds = el.get('bounds', '')
                if bounds:
                    import re
                    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if match:
                        x1, y1, x2, y2 = map(int, match.groups())
                        width = x2 - x1
                        height = y2 - y1
                        # Video thumbnails are roughly square, ~200-250px each
                        if 180 < width < 280 and 180 < height < 280:
                            # Must be in gallery area (y between 190-1200)
                            if 150 < y1 < 1200:
                                self.video_selected = True
                                return Action(
                                    action_type=ActionType.TAP,
                                    target_element=i,
                                    reason=f"Tap video thumbnail ({width}x{height})",
                                    confidence=0.93
                                )

        # Secondary: Find gvi checkbox as fallback (selection indicator)
        for i, el in enumerate(elements):
            if el.get('id', '') == 'gvi' and el.get('clickable'):
                bounds = el.get('bounds', '')
                if bounds:
                    import re
                    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if match:
                        _, y1, _, y2 = map(int, match.groups())
                        # Gallery area is between y=190 and y=1200
                        if 150 < y1 < 1200:
                            self.video_selected = True
                            return Action(
                                action_type=ActionType.TAP,
                                target_element=i,
                                reason=f"Tap video selection checkbox (id='gvi')",
                                confidence=0.85
                            )

        # Tertiary: Use coordinate tap on first video position from faj analysis
        if video_positions:
            x, y, duration = video_positions[0]
            self.video_selected = True
            return Action(
                action_type=ActionType.TAP_COORDINATE,
                coordinates=(x, y),
                reason=f"Tap video with duration {duration} (coordinate from faj)",
                confidence=0.8
            )

        # Quaternary: Default coordinate fallback
        # Videos are typically in a 3-column grid starting around y=250
        self.video_selected = True
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(121, 312),  # First video thumbnail center from flow logs
            reason="Tap first video thumbnail (coordinate fallback)",
            confidence=0.7
        )

    def _handle_video_editor(self, elements: List[Dict]) -> Action:
        """Handle sounds/effects editor - tap Next to proceed.

        This screen appears after video selection with options for
        sounds, effects, text, etc. We want to skip and proceed.

        GrapheneOS: Next button at bottom-right (796, 2181)
        Geelark: Next button at top-right
        """
        # Primary: Find Next button by id (GrapheneOS: ntn or ntq)
        for i, el in enumerate(elements):
            el_id = el.get('id', '')
            text = el.get('text', '').lower()
            if el_id in ['ntn', 'ntq'] and (text == 'next' or el.get('clickable', False)):
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason=f"Tap Next button (id='{el_id}') to proceed to caption",
                    confidence=0.98
                )

        # Secondary: Find Next button by text
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

        # Quaternary: Coordinate fallback
        # GrapheneOS: Next button at bottom-right (796, 2181)
        # Geelark: Next button at top-right (650, 100)
        # Use GrapheneOS position as it's more common now
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(796, 2181),  # GrapheneOS bottom-right Next button
            reason="Tap Next button area (coordinate fallback)",
            confidence=0.7
        )

    def _handle_caption_screen(self, elements: List[Dict]) -> Action:
        """Handle caption screen - enter caption and tap Post.

        Key elements (from flow logs):
        - id='fpj' - Description field with 'Add description...'
        - id='pvl' / 'pvz' / 'pwo' - Post button
        - id='d1k' - Edit cover
        - id='auj' - Hashtags
        """
        # STEP 1: Enter caption if not done yet
        if not self.caption_entered and self.caption:
            # Primary: Find description field by ID (id='fpj')
            for i, el in enumerate(elements):
                if el.get('id', '') == 'fpj':
                    return Action(
                        action_type=ActionType.TYPE_TEXT,
                        target_element=i,
                        text_to_type=self.caption,
                        reason="Type caption into description field (id='fpj')",
                        confidence=0.98
                    )

            # Secondary: Look for description input field by text
            for i, el in enumerate(elements):
                text = el.get('text', '').lower()
                desc = el.get('desc', '').lower()
                if ('describe' in text or 'describe' in desc or
                    'caption' in text or 'caption' in desc or
                    'add a description' in text or 'add description' in text):
                    return Action(
                        action_type=ActionType.TYPE_TEXT,
                        target_element=i,
                        text_to_type=self.caption,
                        reason="Type caption into description field",
                        confidence=0.9
                    )

        # STEP 2: Tap Post button
        # Primary: Post button by ID (id='pvl', 'pvz', 'pwo')
        post_ids = ['pwo', 'pvz', 'pvl']  # pwo has text='Post', most reliable
        for pid in post_ids:
            for i, el in enumerate(elements):
                if el.get('id', '') == pid:
                    text = el.get('text', '').lower()
                    desc = el.get('desc', '').lower()
                    if 'post' in text or 'post' in desc:
                        return Action(
                            action_type=ActionType.TAP,
                            target_element=i,
                            reason=f"Tap Post button (id='{pid}')",
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

        return Action(
            action_type=ActionType.NEED_AI,
            reason="Could not find Post button on caption screen",
            confidence=0.0
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
        dismiss_options = ['not now', 'skip', 'maybe later', 'dismiss',
                          'no thanks', 'cancel', "don't allow"]

        # Find dismiss button
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text in dismiss_options:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason=f"Tap '{text}' to dismiss popup",
                    confidence=0.9
                )

        # Secondary: Check desc
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            for option in dismiss_options:
                if option in desc:
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason=f"Tap dismiss button (desc contains '{option}')",
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
