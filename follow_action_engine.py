"""
FollowActionEngine - Action handlers for Instagram follow flow.

Completely separate from posting action_engine.py to avoid any risk of
breaking the working posting system.

Handles deterministic actions for each screen type in the follow flow.
"""
import time
import random
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from follow_screen_detector import FollowScreenType, FollowDetectionResult


@dataclass
class FollowActionResult:
    """Result of executing a follow action."""
    success: bool
    action_taken: str  # Description of what was done
    next_expected_screen: Optional[FollowScreenType] = None
    error: Optional[str] = None
    element_index: Optional[int] = None  # Which element was interacted with


class FollowActionEngine:
    """Executes deterministic actions for follow flow screens."""

    def __init__(self, driver, logger: Optional[logging.Logger] = None):
        """Initialize action engine.

        Args:
            driver: Appium WebDriver instance
            logger: Optional logger
        """
        self.driver = driver
        self.logger = logger or logging.getLogger(__name__)

    def execute(
        self,
        screen_result: FollowDetectionResult,
        elements: List[Dict],
        target_username: str
    ) -> FollowActionResult:
        """Execute appropriate action for detected screen.

        Args:
            screen_result: Detection result from FollowScreenDetector
            elements: UI elements list
            target_username: Username we're trying to follow

        Returns:
            FollowActionResult with action outcome
        """
        screen_type = screen_result.screen_type
        target_idx = screen_result.target_element_index

        # Route to appropriate handler
        handlers = {
            FollowScreenType.HOME_FEED: self._handle_home_feed,
            FollowScreenType.EXPLORE_PAGE: self._handle_explore_page,
            FollowScreenType.SEARCH_INPUT: self._handle_search_input,
            FollowScreenType.SEARCH_RESULTS: self._handle_search_results,
            FollowScreenType.TARGET_PROFILE: self._handle_target_profile,
            FollowScreenType.FOLLOW_SUCCESS: self._handle_follow_success,
            FollowScreenType.POPUP_DISMISSIBLE: self._handle_popup_dismissible,
            FollowScreenType.NOTIFICATIONS_POPUP: self._handle_popup_dismissible,
            FollowScreenType.ONBOARDING_POPUP: self._handle_popup_dismissible,  # Same as dismiss
            FollowScreenType.REELS_SCREEN: self._handle_reels_screen,  # Added Dec 2024
            FollowScreenType.ABOUT_ACCOUNT_PAGE: self._handle_about_account,  # Added Dec 2024
            FollowScreenType.ACTION_BLOCKED: self._handle_action_blocked,
            FollowScreenType.LOGIN_REQUIRED: self._handle_login_required,
            FollowScreenType.CAPTCHA: self._handle_captcha,
            FollowScreenType.UNKNOWN: self._handle_unknown,
        }

        handler = handlers.get(screen_type, self._handle_unknown)
        return handler(screen_result, elements, target_username, target_idx)

    # ==================== Screen Handlers ====================

    def _handle_home_feed(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle home feed - tap search tab."""
        # Find search tab
        idx = target_idx
        if idx is None:
            idx = self._find_element_by_id(elements, 'search_tab')

        if idx is None:
            return FollowActionResult(
                success=False,
                action_taken='none',
                error='Could not find search_tab element'
            )

        # Tap search tab
        self._tap_element(elements[idx])
        self._human_delay()

        return FollowActionResult(
            success=True,
            action_taken='tap_search_tab',
            next_expected_screen=FollowScreenType.EXPLORE_PAGE,
            element_index=idx
        )

    def _handle_explore_page(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle explore page - tap search bar."""
        # Find search bar
        idx = target_idx
        if idx is None:
            idx = self._find_element_by_id(elements, 'action_bar_search_edit_text')

        if idx is None:
            return FollowActionResult(
                success=False,
                action_taken='none',
                error='Could not find search bar element'
            )

        # Tap search bar to open search input
        self._tap_element(elements[idx])
        self._human_delay()

        return FollowActionResult(
            success=True,
            action_taken='tap_search_bar',
            next_expected_screen=FollowScreenType.SEARCH_INPUT,
            element_index=idx
        )

    def _handle_search_input(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle search input - type target username."""
        if not target:
            return FollowActionResult(
                success=False,
                action_taken='none',
                error='No target username provided'
            )

        # Find search input field
        idx = target_idx
        if idx is None:
            idx = self._find_element_by_id(elements, 'action_bar_search_edit_text')

        if idx is None:
            return FollowActionResult(
                success=False,
                action_taken='none',
                error='Could not find search input element'
            )

        # Tap to focus (might already be focused)
        self._tap_element(elements[idx])
        time.sleep(0.3)

        # Type the target username using Appium
        self._type_text(target)
        self._human_delay()

        return FollowActionResult(
            success=True,
            action_taken=f'type_username:{target}',
            next_expected_screen=FollowScreenType.SEARCH_RESULTS,
            element_index=idx
        )

    def _handle_search_results(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle search results - tap on target user."""
        # The detector should have found the target user's index
        idx = target_idx

        if idx is None:
            # Try to find the user ourselves
            idx = self._find_user_in_results(elements, target)

        if idx is None:
            return FollowActionResult(
                success=False,
                action_taken='none',
                error=f'Could not find @{target} in search results'
            )

        # Tap the user result
        self._tap_element(elements[idx])
        self._human_delay()

        return FollowActionResult(
            success=True,
            action_taken=f'tap_user_result:{target}',
            next_expected_screen=FollowScreenType.TARGET_PROFILE,
            element_index=idx
        )

    def _handle_target_profile(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle target profile - tap Follow button."""
        # Find Follow button
        idx = target_idx
        if idx is None:
            idx = self._find_element_by_id(elements, 'profile_header_follow_button')

        if idx is None:
            # Try by text
            idx = self._find_element_by_text(elements, 'Follow', exact=True)

        if idx is None:
            return FollowActionResult(
                success=False,
                action_taken='none',
                error='Could not find Follow button'
            )

        # Check if already following
        button_text = elements[idx].get('text', '').lower()
        if button_text in ['following', 'requested']:
            return FollowActionResult(
                success=True,
                action_taken=f'already_{button_text}',
                next_expected_screen=FollowScreenType.FOLLOW_SUCCESS,
                element_index=idx
            )

        # Tap Follow button
        self._tap_element(elements[idx])
        self._human_delay()

        return FollowActionResult(
            success=True,
            action_taken='tap_follow_button',
            next_expected_screen=FollowScreenType.FOLLOW_SUCCESS,
            element_index=idx
        )

    def _handle_follow_success(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle follow success - we're done!"""
        return FollowActionResult(
            success=True,
            action_taken='follow_complete',
            next_expected_screen=None  # No next screen - we're done
        )

    def _handle_popup_dismissible(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle dismissible popups."""
        # Find dismiss button
        idx = target_idx
        if idx is None:
            for term in ['not now', 'skip', 'maybe later', 'dismiss', 'no thanks']:
                idx = self._find_element_by_text(elements, term)
                if idx is not None:
                    break

        if idx is None:
            return FollowActionResult(
                success=False,
                action_taken='none',
                error='Could not find dismiss button'
            )

        # Tap dismiss
        self._tap_element(elements[idx])
        self._human_delay()

        return FollowActionResult(
            success=True,
            action_taken='dismiss_popup',
            element_index=idx
        )

    def _handle_reels_screen(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle reels screen - tap search tab to navigate away."""
        # Find search tab to navigate to explore/search
        idx = target_idx
        if idx is None:
            idx = self._find_element_by_id(elements, 'search_tab')

        if idx is None:
            return FollowActionResult(
                success=False,
                action_taken='none',
                error='Could not find search_tab on reels screen'
            )

        # Tap search tab
        self._tap_element(elements[idx])
        self._human_delay()

        return FollowActionResult(
            success=True,
            action_taken='tap_search_tab_from_reels',
            next_expected_screen=FollowScreenType.EXPLORE_PAGE,
            element_index=idx
        )

    def _handle_about_account(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle 'About this account' page - tap back to return to profile."""
        # Find back button
        idx = target_idx
        if idx is None:
            idx = self._find_element_by_id(elements, 'action_bar_button_back')

        if idx is None:
            return FollowActionResult(
                success=False,
                action_taken='none',
                error='Could not find back button on about account page'
            )

        # Tap back button
        self._tap_element(elements[idx])
        self._human_delay()

        return FollowActionResult(
            success=True,
            action_taken='tap_back_from_about_account',
            next_expected_screen=FollowScreenType.TARGET_PROFILE,
            element_index=idx
        )

    def _handle_action_blocked(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle action blocked - this is a terminal error."""
        return FollowActionResult(
            success=False,
            action_taken='none',
            error='Action blocked by Instagram'
        )

    def _handle_login_required(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle login required - this is a terminal error."""
        return FollowActionResult(
            success=False,
            action_taken='none',
            error='Login required - account logged out'
        )

    def _handle_captcha(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle captcha - this is a terminal error."""
        return FollowActionResult(
            success=False,
            action_taken='none',
            error='Captcha verification required'
        )

    def _handle_unknown(
        self,
        result: FollowDetectionResult,
        elements: List[Dict],
        target: str,
        target_idx: Optional[int]
    ) -> FollowActionResult:
        """Handle unknown screen - need AI fallback."""
        return FollowActionResult(
            success=False,
            action_taken='none',
            error='Unknown screen - need AI fallback'
        )

    # ==================== Helper Methods ====================

    def _find_element_by_id(self, elements: List[Dict], element_id: str) -> Optional[int]:
        """Find element index by ID."""
        for i, el in enumerate(elements):
            if el.get('id', '') == element_id:
                return i
        return None

    def _find_element_by_text(self, elements: List[Dict], text: str, exact: bool = False) -> Optional[int]:
        """Find element index by text."""
        text_lower = text.lower()
        for i, el in enumerate(elements):
            el_text = el.get('text', '').lower()
            if exact:
                if el_text == text_lower:
                    return i
            else:
                if text_lower in el_text:
                    return i
        return None

    def _find_user_in_results(self, elements: List[Dict], username: str) -> Optional[int]:
        """Find user in search results."""
        username_lower = username.lower()

        # First, find the username element
        for i, el in enumerate(elements):
            if el.get('id', '') == 'row_search_user_username':
                if el.get('text', '').lower() == username_lower:
                    # Find the parent container (row_search_user_container)
                    for j in range(i, -1, -1):
                        if elements[j].get('id', '') == 'row_search_user_container':
                            return j
                    return i

        # Fallback: search by text anywhere
        for i, el in enumerate(elements):
            if el.get('text', '').lower() == username_lower:
                if el.get('clickable', False):
                    return i
                # Find clickable parent
                for j in range(i, -1, -1):
                    if elements[j].get('clickable', False):
                        return j

        return None

    def _tap_element(self, element: Dict) -> None:
        """Tap on an element by its center coordinates."""
        center = element.get('center')
        if center:
            x, y = center
            self.driver.tap([(x, y)])
            self.logger.debug(f"Tapped element at ({x}, {y})")
        else:
            # Try to calculate from bounds
            bounds = element.get('bounds', '')
            if bounds:
                # Parse "[x1,y1][x2,y2]" format
                import re
                match = re.findall(r'\[(\d+),(\d+)\]', bounds)
                if len(match) == 2:
                    x1, y1 = int(match[0][0]), int(match[0][1])
                    x2, y2 = int(match[1][0]), int(match[1][1])
                    x = (x1 + x2) // 2
                    y = (y1 + y2) // 2
                    self.driver.tap([(x, y)])
                    self.logger.debug(f"Tapped element at ({x}, {y}) from bounds")

    def _type_text(self, text: str) -> None:
        """Type text using Appium."""
        # Use Appium's send_keys on the active element
        active = self.driver.switch_to.active_element
        active.send_keys(text)
        self.logger.debug(f"Typed: {text}")

    def _human_delay(self, min_sec: float = 0.5, max_sec: float = 1.5) -> None:
        """Add human-like random delay."""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)


if __name__ == "__main__":
    print("FollowActionEngine - requires Appium driver for testing")
