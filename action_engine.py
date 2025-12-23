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
        """Handle home feed - navigate to profile."""
        # Primary: Find profile_tab by element ID (92.4% of successful flows)
        for i, el in enumerate(elements):
            if el.get('id', '') == 'profile_tab':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap profile_tab (ID match) to navigate to profile",
                    confidence=0.98
                )

        # Secondary: Find profile tab by desc
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            if 'profile' in desc or 'your profile' in desc:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap profile tab (desc match) to navigate to profile",
                    confidence=0.9
                )

        # Tertiary: Look for profile icon by position (usually bottom-right)
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(540, 2200),  # Approximate profile tab position
            reason="Tap profile tab area (coordinate fallback)",
            confidence=0.6
        )

    def _handle_profile(self, elements: List[Dict]) -> Action:
        """Handle profile screen - start create flow."""
        # Primary: Find "Create New" by desc (91.5% of successful flows)
        for i, el in enumerate(elements):
            desc = el.get('desc', '')
            if desc == 'Create New':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap 'Create New' button (desc match)",
                    confidence=0.98
                )

        # Secondary: Find creation_tab by element ID
        for i, el in enumerate(elements):
            if el.get('id', '') == 'creation_tab':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap creation_tab (ID fallback)",
                    confidence=0.9
                )

        # Tertiary: Partial desc match
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            if 'create' in desc or 'new post' in desc:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap create button (partial desc match)",
                    confidence=0.8
                )

        # Quaternary: Position fallback
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(540, 2200),  # Center bottom area
            reason="Tap create button area (coordinate fallback)",
            confidence=0.5
        )

    def _handle_create_menu(self, elements: List[Dict]) -> Action:
        """Handle create menu - select Reel option."""
        # Primary: Find "Create new reel" by desc (90.8% of successful flows)
        # NOTE: This is in desc, NOT text!
        for i, el in enumerate(elements):
            desc = el.get('desc', '')
            if desc == 'Create new reel':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap 'Create new reel' (desc match)",
                    confidence=0.98
                )

        # Secondary: Partial desc match
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            if 'reel' in desc and 'create' in desc:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap reel option (partial desc match)",
                    confidence=0.9
                )

        # Tertiary: Text-based fallback (less reliable)
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text == 'reel':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Reel option (text fallback)",
                    confidence=0.8
                )

        # Last resort
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if 'reel' in text:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap reel option (partial text match)",
                    confidence=0.7
                )

        return Action(
            action_type=ActionType.NEED_AI,
            reason="Could not find Reel option in create menu",
            confidence=0.0
        )

    def _handle_gallery_picker(self, elements: List[Dict]) -> Action:
        """Handle gallery picker - select video."""
        # CRITICAL: Check if REEL tab needs to be selected first (18.6% of flows need this)
        # If cam_dest_clips is visible, we may need to tap it to switch to REEL mode
        reel_tab_idx = None
        for i, el in enumerate(elements):
            if el.get('id', '') == 'cam_dest_clips':
                reel_tab_idx = i
                break

        # Check if gallery is showing thumbnails yet
        has_thumbnails = any(
            el.get('id', '') == 'gallery_grid_item_thumbnail'
            for el in elements
        )

        # If REEL tab exists but no thumbnails visible, tap the REEL tab
        if reel_tab_idx is not None and not has_thumbnails:
            return Action(
                action_type=ActionType.TAP,
                target_element=reel_tab_idx,
                reason="Tap REEL tab (cam_dest_clips) to switch to reel mode",
                confidence=0.95
            )

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

        # Primary: Find video thumbnail by element ID (72.9% of successful flows)
        for i, el in enumerate(elements):
            if el.get('id', '') == 'gallery_grid_item_thumbnail':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap video thumbnail (ID match)",
                    confidence=0.95
                )

        # Secondary: Look for desc-based thumbnail
        for i, el in enumerate(elements):
            desc = el.get('desc', '').lower()
            if 'thumbnail' in desc or 'video' in desc or 'select' in desc:
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap video thumbnail (desc match)",
                    confidence=0.85
                )

        # Tertiary: Fallback to coordinate tap
        return Action(
            action_type=ActionType.TAP_COORDINATE,
            coordinates=(270, 800),  # First thumbnail position
            reason="Tap gallery area to select video (coordinate fallback)",
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
        # Primary: Find clips_right_action_button by element ID (73.3% of flows)
        for i, el in enumerate(elements):
            if el.get('id', '') == 'clips_right_action_button':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Next button (clips_right_action_button ID)",
                    confidence=0.98
                )

        # Secondary: Find Next button by desc
        for i, el in enumerate(elements):
            desc = el.get('desc', '')
            if desc == 'Next':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Next button (desc match)",
                    confidence=0.9
                )

        # Tertiary: Find Next button by text
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text == 'next':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Next button (text match)",
                    confidence=0.85
                )

        return Action(
            action_type=ActionType.NEED_AI,
            reason="Could not find Next button on editing screen",
            confidence=0.0
        )

    def _handle_share_preview(self, elements: List[Dict]) -> Action:
        """Handle share preview - enter caption, dismiss keyboard, and share."""
        # STEP 1: Check if we need to enter caption
        if not self.caption_entered and self.caption:
            # Primary: Find caption_input_text_view by element ID (71.4% of flows)
            # Use TYPE_TEXT to both tap the field AND type the caption
            for i, el in enumerate(elements):
                if el.get('id', '') == 'caption_input_text_view':
                    return Action(
                        action_type=ActionType.TYPE_TEXT,
                        target_element=i,
                        text_to_type=self.caption,
                        reason="Type caption into caption_input_text_view field",
                        confidence=0.98
                    )

            # Secondary: Find caption field by text/desc
            for i, el in enumerate(elements):
                text = el.get('text', '').lower()
                desc = el.get('desc', '').lower()
                if 'caption' in text or 'caption' in desc or 'write a caption' in text:
                    return Action(
                        action_type=ActionType.TYPE_TEXT,
                        target_element=i,
                        text_to_type=self.caption,
                        reason="Type caption into field (text/desc match)",
                        confidence=0.9
                    )

            # If we can't find caption field, try typing anyway
            return Action(
                action_type=ActionType.TYPE_TEXT,
                text_to_type=self.caption,
                reason="Type caption (field should be focused)",
                confidence=0.7
            )

        # STEP 2: Check if OK button needs to be tapped to dismiss keyboard (62.4% of flows)
        # This step was COMPLETELY MISSING before - critical fix!
        for i, el in enumerate(elements):
            if el.get('id', '') == 'action_bar_button_text':
                desc = el.get('desc', '')
                if desc == 'OK':
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason="Tap OK to dismiss keyboard (action_bar_button_text)",
                        confidence=0.95
                    )

        # Also check for OK by desc without ID match
        for i, el in enumerate(elements):
            desc = el.get('desc', '')
            text = el.get('text', '')
            if desc == 'OK' or text == 'OK':
                # Verify it's clickable
                if el.get('clickable', False):
                    return Action(
                        action_type=ActionType.TAP,
                        target_element=i,
                        reason="Tap OK to dismiss keyboard (desc/text match)",
                        confidence=0.9
                    )

        # STEP 3: Find Share button
        # Primary: Find share_button by element ID (65% of flows)
        for i, el in enumerate(elements):
            if el.get('id', '') == 'share_button':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Share button (share_button ID)",
                    confidence=0.98
                )

        # Secondary: Find Share button by desc
        for i, el in enumerate(elements):
            desc = el.get('desc', '')
            if desc == 'Share':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Share button (desc match)",
                    confidence=0.9
                )

        # Tertiary: Find Share button by text
        for i, el in enumerate(elements):
            text = el.get('text', '').lower()
            if text == 'share':
                return Action(
                    action_type=ActionType.TAP,
                    target_element=i,
                    reason="Tap Share button (text match)",
                    confidence=0.85
                )

        return Action(
            action_type=ActionType.NEED_AI,
            reason="Could not find Share button, OK button, or caption field",
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
