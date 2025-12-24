"""
HybridFollowNavigator - Combines FollowScreenDetector + FollowActionEngine with AI fallback.

Completely separate from posting hybrid_navigator.py to avoid any risk of
breaking the working posting system.

Reduces AI calls by using deterministic rule-based navigation for the follow flow.
"""
import time
import logging
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

from follow_screen_detector import FollowScreenDetector, FollowScreenType, FollowDetectionResult
from follow_action_engine import FollowActionEngine, FollowActionResult


@dataclass
class FollowNavigationResult:
    """Result of hybrid follow navigation decision."""
    action: Dict[str, Any]  # Action dict compatible with follow_single.py
    used_ai: bool
    screen_type: FollowScreenType
    detection_confidence: float
    action_taken: str
    reason: str
    is_terminal: bool = False  # True if this is the final state (success or error)


class HybridFollowNavigator:
    """Hybrid navigation for follow flow: rule-based detection with AI fallback.

    Flow:
    1. FollowScreenDetector analyzes UI elements
    2. If high confidence (>70%), FollowActionEngine executes action
    3. If low confidence OR on UNKNOWN screen, fall back to AI
    """

    def __init__(
        self,
        driver,
        target_username: str,
        ai_analyzer=None,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize hybrid follow navigator.

        Args:
            driver: Appium WebDriver instance
            target_username: Username to follow
            ai_analyzer: ClaudeUIAnalyzer for fallback (optional)
            logger: Logger instance
        """
        self.driver = driver
        self.target_username = target_username.lstrip('@').lower()
        self.ai_analyzer = ai_analyzer
        self.logger = logger or logging.getLogger(__name__)

        # Initialize detector and action engine
        self.detector = FollowScreenDetector()
        self.engine = FollowActionEngine(driver, self.logger)

        # State tracking
        self.search_opened = False
        self.username_typed = False
        self.profile_opened = False
        self.follow_clicked = False

        # Statistics
        self.total_steps = 0
        self.ai_calls = 0
        self.rule_based_steps = 0

    def update_state(
        self,
        search_opened: bool = None,
        username_typed: bool = None,
        profile_opened: bool = None,
        follow_clicked: bool = None
    ):
        """Update follow flow state."""
        if search_opened is not None:
            self.search_opened = search_opened
        if username_typed is not None:
            self.username_typed = username_typed
        if profile_opened is not None:
            self.profile_opened = profile_opened
        if follow_clicked is not None:
            self.follow_clicked = follow_clicked

    def navigate(self, elements: List[Dict]) -> FollowNavigationResult:
        """Decide and execute next action using hybrid approach.

        Args:
            elements: UI elements from dump_ui()

        Returns:
            FollowNavigationResult with action outcome
        """
        self.total_steps += 1

        # Step 1: Detect screen type
        detection = self.detector.detect(elements, self.target_username)

        self.logger.debug(
            f"[FOLLOW-HYBRID] Detected: {detection.screen_type.name} "
            f"(conf={detection.confidence:.2f}, rule={detection.matched_rule})"
        )

        # Step 2: If known screen, use ActionEngine
        if detection.screen_type != FollowScreenType.UNKNOWN:
            action_result = self.engine.execute(
                detection,
                elements,
                self.target_username
            )

            # Update state based on action
            self._update_state_from_action(detection.screen_type, action_result)

            if action_result.success:
                self.rule_based_steps += 1
                return self._convert_action_result(
                    action_result, detection, used_ai=False
                )
            else:
                # Action failed but we know the screen - might need AI
                if action_result.error and 'need AI' not in action_result.error:
                    # Terminal error (blocked, captcha, etc)
                    return self._create_error_result(
                        action_result.error,
                        detection,
                        is_terminal=True
                    )

        # Step 3: Fall back to AI for unknown screens
        if self.ai_analyzer is None:
            # NO AI FALLBACK MODE - return detailed error
            self.logger.warning(
                f"[FOLLOW-HYBRID] NO AI FALLBACK - Cannot handle: {detection.screen_type.name}"
            )
            return self._create_error_result(
                f"Rules cannot handle {detection.screen_type.name} (conf={detection.confidence:.2f})",
                detection,
                is_terminal=False  # Not terminal, just need AI
            )

        # Use AI
        self.ai_calls += 1
        self.logger.info(
            f"[FOLLOW-HYBRID] AI fallback for: {detection.screen_type.name}"
        )

        try:
            ai_action = self.ai_analyzer.analyze_for_follow(
                elements=elements,
                target=self.target_username,
                search_opened=self.search_opened,
                username_typed=self.username_typed,
                profile_opened=self.profile_opened,
                follow_clicked=self.follow_clicked
            )

            # Execute AI's suggested action
            return self._execute_ai_action(ai_action, detection)

        except Exception as e:
            self.logger.error(f"[FOLLOW-HYBRID] AI error: {e}")
            return self._create_error_result(str(e), detection, is_terminal=False)

    def _update_state_from_action(
        self,
        screen_type: FollowScreenType,
        action_result: FollowActionResult
    ):
        """Update state based on successful action."""
        if screen_type == FollowScreenType.EXPLORE_PAGE:
            self.search_opened = True
        elif screen_type == FollowScreenType.SEARCH_INPUT:
            if 'type_username' in action_result.action_taken:
                self.username_typed = True
        elif screen_type == FollowScreenType.SEARCH_RESULTS:
            if 'tap_user' in action_result.action_taken:
                self.profile_opened = True
        elif screen_type == FollowScreenType.TARGET_PROFILE:
            if 'tap_follow' in action_result.action_taken:
                self.follow_clicked = True
        elif screen_type == FollowScreenType.FOLLOW_SUCCESS:
            self.follow_clicked = True

    def _convert_action_result(
        self,
        action_result: FollowActionResult,
        detection: FollowDetectionResult,
        used_ai: bool
    ) -> FollowNavigationResult:
        """Convert FollowActionResult to FollowNavigationResult."""
        is_terminal = (
            detection.screen_type == FollowScreenType.FOLLOW_SUCCESS or
            detection.screen_type in (
                FollowScreenType.ACTION_BLOCKED,
                FollowScreenType.LOGIN_REQUIRED,
                FollowScreenType.CAPTCHA
            )
        )

        return FollowNavigationResult(
            action={
                'action': action_result.action_taken,
                'screen': detection.screen_type.name,
                'element_index': action_result.element_index,
                'search_opened': self.search_opened,
                'username_typed': self.username_typed,
                'profile_opened': self.profile_opened,
                'follow_clicked': self.follow_clicked
            },
            used_ai=used_ai,
            screen_type=detection.screen_type,
            detection_confidence=detection.confidence,
            action_taken=action_result.action_taken,
            reason=action_result.error or f"Executed {action_result.action_taken}",
            is_terminal=is_terminal
        )

    def _create_error_result(
        self,
        error: str,
        detection: FollowDetectionResult,
        is_terminal: bool
    ) -> FollowNavigationResult:
        """Create error result."""
        return FollowNavigationResult(
            action={
                'action': 'error',
                'error': error,
                'screen': detection.screen_type.name,
                'search_opened': self.search_opened,
                'username_typed': self.username_typed,
                'profile_opened': self.profile_opened,
                'follow_clicked': self.follow_clicked
            },
            used_ai=False,
            screen_type=detection.screen_type,
            detection_confidence=detection.confidence,
            action_taken='error',
            reason=error,
            is_terminal=is_terminal
        )

    def _execute_ai_action(
        self,
        ai_action: Dict,
        detection: FollowDetectionResult
    ) -> FollowNavigationResult:
        """Execute AI-suggested action."""
        action_type = ai_action.get('action', '')
        reason = ai_action.get('reason', '')

        # Update state from AI's response
        if ai_action.get('search_opened'):
            self.search_opened = True
        if ai_action.get('username_typed'):
            self.username_typed = True
        if ai_action.get('profile_opened'):
            self.profile_opened = True
        if ai_action.get('follow_clicked'):
            self.follow_clicked = True

        # Check for terminal states
        is_terminal = action_type in ('done', 'success', 'follow_complete', 'error')

        return FollowNavigationResult(
            action=ai_action,
            used_ai=True,
            screen_type=detection.screen_type,
            detection_confidence=detection.confidence,
            action_taken=action_type,
            reason=reason,
            is_terminal=is_terminal
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get navigation statistics."""
        ai_rate = (self.ai_calls / self.total_steps * 100) if self.total_steps > 0 else 0
        rule_rate = (self.rule_based_steps / self.total_steps * 100) if self.total_steps > 0 else 0

        return {
            'total_steps': self.total_steps,
            'ai_calls': self.ai_calls,
            'rule_based_steps': self.rule_based_steps,
            'ai_rate_percent': round(ai_rate, 1),
            'rule_rate_percent': round(rule_rate, 1)
        }


def create_hybrid_follow_navigator(
    driver,
    target_username: str,
    ai_analyzer=None,
    logger: Optional[logging.Logger] = None
) -> HybridFollowNavigator:
    """Factory function to create a HybridFollowNavigator."""
    return HybridFollowNavigator(
        driver=driver,
        target_username=target_username,
        ai_analyzer=ai_analyzer,
        logger=logger
    )


if __name__ == "__main__":
    print("HybridFollowNavigator - requires Appium driver for testing")
    print("Run follow_single.py for integration tests")
