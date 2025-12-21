"""
ActionEngine - Deterministic action selection for Instagram posting.

Part of the Hybrid Posting System - Phase 5.
Knows what action to take for each ScreenType during Reel posting flow.
"""
from enum import Enum, auto
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass

from screen_detector import ScreenType


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


class ActionEngine:
    """Determines what action to take based on screen type and state."""

    def __init__(self, caption: str = "", video_selected: bool = False,
                 caption_entered: bool = False):
        """Initialize with posting state.

        Args:
            caption: The caption to post with the reel.
            video_selected: Whether a video has been selected.
            caption_entered: Whether the caption has been entered.
        """
        self.caption = caption
        self.video_selected = video_selected
        self.caption_entered = caption_entered

        # Build action handlers for each screen type
        self.handlers = {
            ScreenType.FEED_SCREEN: self._handle_feed,
            ScreenType.PROFILE_SCREEN: self._handle_profile,
            ScreenType.CREATE_MENU: self._handle_create_menu,
            ScreenType.GALLERY_PICKER: self._handle_gallery_picker,
            ScreenType.CAMERA_SCREEN: self._handle_camera,
            ScreenType.VIDEO_EDITING: self._handle_video_editing,
            ScreenType.SHARE_PREVIEW: self._handle_share_preview,
            ScreenType.SHARING_PROGRESS: self._handle_sharing_progress,
            ScreenType.SUCCESS_SCREEN: self._handle_success,
            ScreenType.REEL_VIEW: self._handle_reel_view,
            ScreenType.STORY_VIEW: self._handle_story_view,
            ScreenType.OWN_REEL_VIEW: self._handle_own_reel_view,
            ScreenType.FEED_POST: self._handle_feed_post,
            ScreenType.REELS_TAB: self._handle_reels_tab,
            ScreenType.STORY_EDITOR: self._handle_story_editor,
            ScreenType.SHARE_SHEET: self._handle_share_sheet,
            ScreenType.POPUP_DISMISSIBLE: self._handle_dismissible_popup,
            ScreenType.POPUP_VERIFICATION: self._handle_verification_popup,
            ScreenType.POPUP_ACTION_REQ: self._handle_action_required,
            ScreenType.POPUP_ONBOARDING: self._handle_onboarding_popup,
            ScreenType.POPUP_WARNING: self._handle_warning_popup,
            ScreenType.POPUP_CAPTCHA: self._handle_captcha,
            ScreenType.POPUP_SUGGESTED: self._handle_suggested_popup,
            ScreenType.BROWSER_POPUP: self._handle_browser_popup,
            ScreenType.DM_SCREEN: self._handle_dm_screen,
            ScreenType.LOADING_SCREEN: self._handle_loading_screen,
            ScreenType.ANDROID_HOME: self._handle_android_home,
            ScreenType.SPONSORED_POST: self._handle_sponsored_post,
            ScreenType.LOGIN_SCREEN: self._handle_login,
            ScreenType.ERROR_SCREEN: self._handle_error,
            ScreenType.UNKNOWN: self._handle_unknown,
        }

    def get_action(self, screen_type: ScreenType, elements: List[Dict]) -> Action:
        """Get the appropriate action for the current screen.

        Args:
            screen_type: Detected screen type from ScreenDetector.
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

    def _handle_feed(self, elements: List[Dict]) -> Action:
        """Handle home feed - tap + button to start create flow.

        IMPORTANT: We tap the + (create) button directly from feed,
        NOT navigate to profile first. The + button is in bottom nav.
        """
        # Look for create/plus button in bottom navigation
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            text = el.get('text', '').lower()

            # Create button patterns
            if 'create' in desc or 'new post' in desc or '+' in text:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap create (+) button to start posting flow",
                    confidence=0.95
                )

        # Look for profile tab ONLY in bottom nav area (y > 1100)
        # Must be exact match to avoid "Visit profile" false positives
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            bounds = el.get('bounds', '')

            # Parse y coordinate from bounds like "[x1,y1][x2,y2]"
            try:
                y1 = int(bounds.split(',')[1].split(']')[0])
                is_bottom_nav = y1 > 1100
            except:
                is_bottom_nav = False

            # Only match exact "profile" or "your profile" in bottom nav
            if is_bottom_nav and (desc == 'profile' or desc == 'your profile'):
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap profile tab in bottom navigation",
                    confidence=0.9
                )

        # Fallback: tap create button area (center bottom, above nav bar)
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(360, 1240),  # Create button position (center bottom)
            reason="Tap create button area (fallback)",
            confidence=0.7
        )

    def _handle_profile(self, elements: List[Dict]) -> Action:
        """Handle profile screen - start create flow.

        On Instagram profile, the + (create) button is in the TOP RIGHT corner,
        NOT the bottom navigation. We need to tap that to open the create menu.
        """
        # Find the create/plus button in TOP area (y < 200)
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            text = el.get('text', '').lower()
            bounds = el.get('bounds', '')

            # Parse y coordinate
            try:
                y1 = int(bounds.split(',')[1].split(']')[0])
                is_top_area = y1 < 200
            except:
                is_top_area = False

            # Only match create button in top area to avoid "Add to story" confusion
            if is_top_area and ('create' in desc or '+' in text or 'new post' in desc):
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap create (+) button in top right",
                    confidence=0.9
                )

        # Fallback: Create button is usually at top right (x~650, y~85)
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(650, 85),  # Top right create button
            reason="Tap create button area (top right fallback)",
            confidence=0.7
        )

    def _handle_create_menu(self, elements: List[Dict]) -> Action:
        """Handle create menu - select Reel option."""
        # Find the "Reel" option
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text == 'reel':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Reel option to create a reel",
                    confidence=0.95
                )

        # If no exact match, look for partial match
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if 'reel' in text:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Reel option",
                    confidence=0.85
                )

        return Action(
            action_type=ActionType.NEED_AI,
            reason="Could not find Reel option in create menu",
            confidence=0.0
        )

    def _handle_gallery_picker(self, elements: List[Dict]) -> Action:
        """Handle gallery picker - select video."""
        if self.video_selected:
            # Already selected, look for Next button
            for i, el in enumerate(elements):
                text = el.get('text', '').lower()
                if text == 'next':
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason="Tap Next to proceed with selected video",
                        confidence=0.95
                    )

        # Find first video thumbnail (usually marked as thumbnail or has no text)
        # Thumbnails are typically clickable elements without text in the grid
        clickable_elements = [
            (i, el) for i, el in enumerate(elements)
            if el.get('clickable', False)
        ]

        for i, el in clickable_elements:
            desc = el.get('desc', '').lower()
            # Look for video/thumbnail descriptions
            if 'thumbnail' in desc or 'video' in desc or 'select' in desc:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap video thumbnail to select",
                    confidence=0.85
                )

        # Fallback: Tap center area where gallery thumbnails typically are
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(270, 800),  # First thumbnail position
            reason="Tap gallery area to select video (fallback)",
            confidence=0.6
        )

    def _handle_camera(self, elements: List[Dict]) -> Action:
        """Handle camera screen - need to go back to gallery."""
        # We want to use gallery, not camera. Press back or find gallery tab
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            desc = el.get('desc', '').lower()
            if 'gallery' in text or 'gallery' in desc or 'recents' in text:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap gallery to switch from camera to gallery picker",
                    confidence=0.9
                )

        # Press back to exit camera
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to exit camera mode",
            confidence=0.8
        )

    def _handle_video_editing(self, elements: List[Dict]) -> Action:
        """Handle video editing screen - tap Next to proceed."""
        # Find Next button
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text == 'next':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Next to proceed to share preview",
                    confidence=0.95
                )

        return Action(
            action_type=ActionType.NEED_AI,
            reason="Could not find Next button on editing screen",
            confidence=0.0
        )

    def _handle_share_preview(self, elements: List[Dict]) -> Action:
        """Handle share preview - enter caption and share."""
        if not self.caption_entered and self.caption:
            # Find caption input field
            for i, el in enumerate(elements):
                text = el.get('text', '').lower()
                desc = el.get('desc', '').lower()
                if 'caption' in text or 'caption' in desc or 'write a caption' in text:
                    # First tap to focus the field
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason="Tap caption field to focus it",
                        confidence=0.9
                    )

            # If we can't find caption field, try typing anyway
            return Action(
                action_type=ActionType.TYPE_TEXT,
                text_to_type=self.caption,
                reason="Type caption (field should be focused)",
                confidence=0.7
            )

        # Caption entered, find Share button
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text == 'share':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Share to post the reel",
                    confidence=0.95
                )

        return Action(
            action_type=ActionType.NEED_AI,
            reason="Could not find Share button or caption field",
            confidence=0.0
        )

    def _handle_sharing_progress(self, elements: List[Dict]) -> Action:
        """Handle sharing in progress - wait for completion."""
        return Action(
            action_type=ActionType.WAIT,
            wait_seconds=3.0,
            reason="Waiting for upload to complete",
            confidence=0.9
        )

    def _handle_success(self, elements: List[Dict]) -> Action:
        """Handle success screen - posting complete!"""
        return Action(
            action_type=ActionType.SUCCESS,
            reason="Reel posted successfully!",
            confidence=1.0
        )

    def _handle_reel_view(self, elements: List[Dict]) -> Action:
        """Handle viewing a reel - navigate away."""
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to exit reel view",
            confidence=0.85
        )

    def _handle_story_view(self, elements: List[Dict]) -> Action:
        """Handle viewing stories - navigate away."""
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to exit story view",
            confidence=0.85
        )

    def _handle_own_reel_view(self, elements: List[Dict]) -> Action:
        """Handle viewing own posted reel - this means SUCCESS, navigate away."""
        # If we're viewing our own reel with "View insights", posting was successful!
        return Action(
            action_type=ActionType.SUCCESS,
            reason="Viewing own reel with insights - posting was successful!",
            confidence=0.95
        )

    def _handle_feed_post(self, elements: List[Dict]) -> Action:
        """Handle viewing a post in feed - navigate away to continue posting flow."""
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to exit feed post view",
            confidence=0.85
        )

    def _handle_reels_tab(self, elements: List[Dict]) -> Action:
        """Handle Reels tab - navigate away to profile."""
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to exit Reels tab",
            confidence=0.85
        )

    def _handle_story_editor(self, elements: List[Dict]) -> Action:
        """Handle story editor - we're in wrong flow, go back."""
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to exit story editor (wrong flow)",
            confidence=0.9
        )

    def _handle_share_sheet(self, elements: List[Dict]) -> Action:
        """Handle share sheet - dismiss it."""
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to dismiss share sheet",
            confidence=0.9
        )

    def _handle_onboarding_popup(self, elements: List[Dict]) -> Action:
        """Handle onboarding/tutorial popup - dismiss with Got it."""
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text == 'got it' or text == 'ok' or text == 'continue':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason=f"Dismiss onboarding by tapping '{text}'",
                    confidence=0.9
                )
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to dismiss onboarding",
            confidence=0.8
        )

    def _handle_warning_popup(self, elements: List[Dict]) -> Action:
        """Handle warning popup - proceed anyway."""
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text == 'share' or text == 'continue' or text == 'ok':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason=f"Proceed past warning by tapping '{text}'",
                    confidence=0.9
                )
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to dismiss warning",
            confidence=0.7
        )

    def _handle_captcha(self, elements: List[Dict]) -> Action:
        """Handle captcha - this is a problem, needs manual intervention."""
        return Action(
            action_type=ActionType.ERROR,
            reason="Captcha detected - cannot proceed automatically",
            confidence=1.0
        )

    def _handle_suggested_popup(self, elements: List[Dict]) -> Action:
        """Handle 'Suggested for you' popup - dismiss it."""
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            if 'dismiss' in desc:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Dismiss suggested follows popup",
                    confidence=0.9
                )
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to dismiss suggested popup",
            confidence=0.8
        )

    def _handle_browser_popup(self, elements: List[Dict]) -> Action:
        """Handle external browser - close it."""
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            if 'close browser' in desc or 'close' in desc:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Close browser popup",
                    confidence=0.9
                )
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to close browser",
            confidence=0.85
        )

    def _handle_dm_screen(self, elements: List[Dict]) -> Action:
        """Handle DM/messaging screen - go back."""
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to exit DM screen",
            confidence=0.9
        )

    def _handle_loading_screen(self, elements: List[Dict]) -> Action:
        """Handle loading screen - wait for it to load."""
        return Action(
            action_type=ActionType.WAIT,
            wait_seconds=2.0,
            reason="Waiting for screen to load",
            confidence=0.8
        )

    def _handle_android_home(self, elements: List[Dict]) -> Action:
        """Handle Android home screen - open Instagram."""
        # We're on Android home, need to open Instagram
        return Action(
            action_type=ActionType.TAP,
            target_text="open_instagram",  # Special flag for post_reel_smart.py
            reason="On Android home - need to open Instagram app",
            confidence=0.9
        )

    def _handle_sponsored_post(self, elements: List[Dict]) -> Action:
        """Handle sponsored post - scroll past it."""
        return Action(
            action_type=ActionType.SWIPE,
            swipe_direction="up",
            reason="Scroll past sponsored post",
            confidence=0.85
        )

    def _handle_dismissible_popup(self, elements: List[Dict]) -> Action:
        """Handle dismissible popup - dismiss it."""
        dismiss_texts = ['not now', 'skip', 'maybe later', 'no thanks',
                        "don't allow", 'cancel', 'dismiss']

        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text in dismiss_texts or any(d in text for d in dismiss_texts):
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason=f"Dismiss popup by tapping '{text}'",
                    confidence=0.9
                )

        # Try pressing back
        return Action(
            action_type=ActionType.PRESS_KEY,
            target_text="BACK",
            reason="Press back to dismiss popup",
            confidence=0.7
        )

    def _handle_verification_popup(self, elements: List[Dict]) -> Action:
        """Handle verification popup - this is a problem."""
        return Action(
            action_type=ActionType.ERROR,
            reason="Verification required - cannot proceed automatically",
            confidence=1.0
        )

    def _handle_action_required(self, elements: List[Dict]) -> Action:
        """Handle action required popup - need AI decision."""
        return Action(
            action_type=ActionType.NEED_AI,
            reason="Action required popup - need AI to decide",
            confidence=0.0
        )

    def _handle_login(self, elements: List[Dict]) -> Action:
        """Handle login screen - account logged out."""
        return Action(
            action_type=ActionType.ERROR,
            reason="Account logged out - cannot proceed",
            confidence=1.0
        )

    def _handle_error(self, elements: List[Dict]) -> Action:
        """Handle error screen."""
        return Action(
            action_type=ActionType.ERROR,
            reason="Error screen encountered",
            confidence=1.0
        )

    def _handle_unknown(self, elements: List[Dict]) -> Action:
        """Handle unknown screen - need AI fallback."""
        return Action(
            action_type=ActionType.NEED_AI,
            reason="Unknown screen - AI analysis required",
            confidence=0.0
        )


def get_action_for_screen(screen_type: ScreenType, elements: List[Dict],
                          caption: str = "", video_selected: bool = False,
                          caption_entered: bool = False) -> Action:
    """Convenience function to get action for a screen.

    Args:
        screen_type: The detected screen type.
        elements: UI elements from the screen.
        caption: Caption text to post.
        video_selected: Whether video has been selected.
        caption_entered: Whether caption has been entered.

    Returns:
        Action to take.
    """
    engine = ActionEngine(caption, video_selected, caption_entered)
    return engine.get_action(screen_type, elements)


if __name__ == "__main__":
    # Test the action engine
    from screen_detector import ScreenDetector

    test_cases = [
        # Video editing screen
        (ScreenType.VIDEO_EDITING, [
            {'text': 'Edit video', 'desc': '', 'clickable': True},
            {'text': 'Next', 'desc': '', 'clickable': True},
        ]),
        # Share preview
        (ScreenType.SHARE_PREVIEW, [
            {'text': 'Write a caption...', 'desc': '', 'clickable': True},
            {'text': 'Share', 'desc': '', 'clickable': True},
        ]),
        # Dismissible popup
        (ScreenType.POPUP_DISMISSIBLE, [
            {'text': 'Turn on notifications?', 'desc': '', 'clickable': False},
            {'text': 'Not now', 'desc': '', 'clickable': True},
            {'text': 'Turn on', 'desc': '', 'clickable': True},
        ]),
        # Create menu
        (ScreenType.CREATE_MENU, [
            {'text': 'Post', 'desc': '', 'clickable': True},
            {'text': 'Story', 'desc': '', 'clickable': True},
            {'text': 'Reel', 'desc': '', 'clickable': True},
        ]),
    ]

    engine = ActionEngine(caption="Test caption #test", video_selected=False,
                         caption_entered=False)

    print("ActionEngine Test Results:")
    print("=" * 60)

    for screen_type, elements in test_cases:
        action = engine.get_action(screen_type, elements)
        print(f"\nScreen: {screen_type.name}")
        print(f"  Action: {action.action_type.name}")
        print(f"  Reason: {action.reason}")
        if action.target_element is not None:
            print(f"  Target: element[{action.target_element}]")
        print(f"  Confidence: {action.confidence:.2f}")
