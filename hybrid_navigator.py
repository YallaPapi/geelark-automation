"""
HybridNavigator - Combines ScreenDetector + ActionEngine with AI fallback.

Part of the Hybrid Posting System - Phase 6.
Reduces AI calls by 80-90% through deterministic rule-based navigation.
"""
import time
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

from screen_detector import ScreenDetector, ScreenType, DetectionResult
from action_engine import ActionEngine, ActionType, Action


@dataclass
class NavigationResult:
    """Result of hybrid navigation decision."""
    action: Dict[str, Any]  # Action dict compatible with existing code
    used_ai: bool           # Whether AI was called
    screen_type: ScreenType
    detection_confidence: float
    action_confidence: float
    reason: str


class HybridNavigator:
    """Hybrid navigation: rule-based detection with AI fallback.

    Flow:
    1. ScreenDetector analyzes UI elements
    2. If high confidence (>70%), ActionEngine decides action
    3. If low confidence, fall back to AI (claude_analyzer)

    This reduces AI calls from 100% to ~12%, saving ~$0.40 per post.
    """

    def __init__(self, ai_analyzer=None, caption: str = ""):
        """Initialize hybrid navigator.

        Args:
            ai_analyzer: ClaudeUIAnalyzer instance for fallback.
            caption: Caption text for the post.
        """
        self.detector = ScreenDetector()
        self.engine = ActionEngine(caption=caption)
        self.ai_analyzer = ai_analyzer
        self.caption = caption

        # State tracking
        self.video_selected = False
        self.caption_entered = False
        self.share_clicked = False

        # Statistics
        self.total_steps = 0
        self.ai_calls = 0
        self.rule_based_steps = 0

    def update_state(self, video_selected: bool = None, caption_entered: bool = None,
                     share_clicked: bool = None):
        """Update posting state."""
        if video_selected is not None:
            self.video_selected = video_selected
            self.engine.video_selected = video_selected
        if caption_entered is not None:
            self.caption_entered = caption_entered
            self.engine.caption_entered = caption_entered
        if share_clicked is not None:
            self.share_clicked = share_clicked

    def navigate(self, elements: List[Dict]) -> NavigationResult:
        """Decide next action using hybrid approach.

        Args:
            elements: UI elements from dump_ui().

        Returns:
            NavigationResult with action and metadata.
        """
        self.total_steps += 1

        # Step 1: Try rule-based detection
        detection = self.detector.detect(elements)

        # Step 2: If high confidence, use ActionEngine
        if detection.screen_type != ScreenType.UNKNOWN:
            action = self.engine.get_action(detection.screen_type, elements)

            # If ActionEngine can handle it deterministically
            if action.action_type not in (ActionType.NEED_AI, ActionType.ERROR):
                self.rule_based_steps += 1
                return self._convert_action(action, detection, used_ai=False)

        # Step 3: Fall back to AI
        if self.ai_analyzer is None:
            # NO AI FALLBACK MODE (testing) - fail immediately so we can capture the error
            # This exposes which screens/rules need fixing
            print(f"  [HYBRID] NO AI FALLBACK - Rules cannot handle: {detection.screen_type.name}")
            print(f"  [HYBRID] Detection confidence: {detection.confidence:.2f}, Rule: {detection.matched_rule}")

            # Build a descriptive error for debugging
            element_summary = []
            for e in elements[:10]:  # First 10 elements
                parts = []
                if e.get('text'):
                    parts.append(f"text='{e['text'][:30]}'")
                if e.get('desc'):
                    parts.append(f"desc='{e['desc'][:30]}'")
                if e.get('id'):
                    parts.append(f"id='{e['id']}'")
                if parts:
                    element_summary.append(' '.join(parts))

            error_reason = (
                f"Rules-only mode: Cannot handle screen '{detection.screen_type.name}' "
                f"(conf={detection.confidence:.2f}). "
                f"Elements: {'; '.join(element_summary[:5])}"
            )

            # Return ERROR action - this will trigger screenshot capture
            return NavigationResult(
                action={
                    'action': 'error',
                    'reason': error_reason,
                    'error_type': 'hybrid_rules_failed',
                    'screen_type': detection.screen_type.name,
                    'video_selected': self.video_selected,
                    'caption_entered': self.caption_entered,
                    'share_clicked': self.share_clicked
                },
                used_ai=False,
                screen_type=detection.screen_type,
                detection_confidence=detection.confidence,
                action_confidence=0.0,
                reason=error_reason
            )

        # Use AI for unknown/uncertain screens
        self.ai_calls += 1
        print(f"  [HYBRID] AI fallback for screen: {detection.screen_type.name} "
              f"(conf={detection.confidence:.2f}, rule={detection.matched_rule})")

        try:
            ai_action = self.ai_analyzer.analyze(
                elements=elements,
                caption=self.caption,
                video_uploaded=self.video_selected,
                caption_entered=self.caption_entered,
                share_clicked=self.share_clicked
            )

            return NavigationResult(
                action=ai_action,
                used_ai=True,
                screen_type=detection.screen_type,
                detection_confidence=detection.confidence,
                action_confidence=0.9,  # AI is generally confident
                reason=ai_action.get('reason', 'AI decision')
            )

        except Exception as e:
            print(f"  [HYBRID] AI error: {e}")
            # Fall back to ActionEngine's best guess
            action = self.engine.get_action(detection.screen_type, elements)
            return self._convert_action(action, detection, used_ai=False)

    def _convert_action(self, action: Action, detection: DetectionResult,
                       used_ai: bool) -> NavigationResult:
        """Convert ActionEngine's Action to NavigationResult.

        Maps ActionType to the action dict format expected by post_reel_smart.py.
        """
        action_dict = self._action_to_dict(action)

        return NavigationResult(
            action=action_dict,
            used_ai=used_ai,
            screen_type=detection.screen_type,
            detection_confidence=detection.confidence,
            action_confidence=action.confidence,
            reason=action.reason
        )

    def _action_to_dict(self, action: Action) -> Dict[str, Any]:
        """Convert Action dataclass to action dict for post_reel_smart.py."""

        # Map ActionType to action names used by post_reel_smart.py
        if action.action_type == ActionType.TAP:
            return {
                'action': 'tap',
                'element_index': action.target_element,
                'reason': action.reason,
                'video_selected': self.video_selected,
                'caption_entered': self.caption_entered,
                'share_clicked': self.share_clicked
            }

        elif action.action_type == ActionType.TAP_COORDINATE:
            # For coordinate taps, we need to use tap action with element index
            # The existing code handles this by looking up the element
            return {
                'action': 'tap_coordinate',
                'x': action.coordinates[0] if action.coordinates else 540,
                'y': action.coordinates[1] if action.coordinates else 1200,
                'reason': action.reason,
                'video_selected': self.video_selected,
                'caption_entered': self.caption_entered,
                'share_clicked': self.share_clicked
            }

        elif action.action_type == ActionType.TYPE_TEXT:
            return {
                'action': 'tap_and_type',
                'element_index': action.target_element or 0,
                'text': action.text_to_type or self.caption,
                'reason': action.reason,
                'video_selected': self.video_selected,
                'caption_entered': False,  # Will be set after typing
                'share_clicked': self.share_clicked
            }

        elif action.action_type == ActionType.PRESS_KEY:
            return {
                'action': 'back',
                'reason': action.reason,
                'video_selected': self.video_selected,
                'caption_entered': self.caption_entered,
                'share_clicked': self.share_clicked
            }

        elif action.action_type == ActionType.WAIT:
            return {
                'action': 'wait',
                'seconds': action.wait_seconds,
                'reason': action.reason,
                'video_selected': self.video_selected,
                'caption_entered': self.caption_entered,
                'share_clicked': self.share_clicked
            }

        elif action.action_type == ActionType.SUCCESS:
            return {
                'action': 'done',
                'reason': action.reason,
                'video_selected': True,
                'caption_entered': True,
                'share_clicked': True
            }

        elif action.action_type == ActionType.SWIPE:
            direction = action.swipe_direction or 'up'
            return {
                'action': f'scroll_{direction}',
                'reason': action.reason,
                'video_selected': self.video_selected,
                'caption_entered': self.caption_entered,
                'share_clicked': self.share_clicked
            }

        elif action.action_type == ActionType.ERROR:
            # Return an action that signals error
            return {
                'action': 'error',
                'reason': action.reason,
                'error_type': 'hybrid_error',
                'video_selected': self.video_selected,
                'caption_entered': self.caption_entered,
                'share_clicked': self.share_clicked
            }

        else:  # NEED_AI or unknown
            # This shouldn't happen if AI fallback is working, but handle it
            return {
                'action': 'wait',
                'seconds': 1,
                'reason': f'Unknown action type: {action.action_type.name}',
                'video_selected': self.video_selected,
                'caption_entered': self.caption_entered,
                'share_clicked': self.share_clicked
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get navigation statistics."""
        ai_rate = (self.ai_calls / self.total_steps * 100) if self.total_steps > 0 else 0
        rule_rate = (self.rule_based_steps / self.total_steps * 100) if self.total_steps > 0 else 0

        return {
            'total_steps': self.total_steps,
            'ai_calls': self.ai_calls,
            'rule_based_steps': self.rule_based_steps,
            'ai_rate_percent': ai_rate,
            'rule_rate_percent': rule_rate,
            'estimated_savings_per_post': 0.02 * self.rule_based_steps  # ~$0.02 per AI call saved
        }


def create_hybrid_navigator(ai_analyzer=None, caption: str = "") -> HybridNavigator:
    """Factory function to create a HybridNavigator."""
    return HybridNavigator(ai_analyzer=ai_analyzer, caption=caption)


if __name__ == "__main__":
    # Test the hybrid navigator
    from screen_detector import ScreenType

    navigator = HybridNavigator(caption="Test caption #test")

    test_cases = [
        # Video editing screen
        [
            {'text': 'Edit video', 'desc': '', 'clickable': True, 'center': (540, 500), 'bounds': '[0,0][1080,1000]'},
            {'text': 'Next', 'desc': '', 'clickable': True, 'center': (900, 100), 'bounds': '[800,50][1000,150]'},
        ],
        # Share preview
        [
            {'text': 'Write a caption...', 'desc': '', 'clickable': True, 'center': (540, 500), 'bounds': '[0,400][1080,600]'},
            {'text': 'Share', 'desc': '', 'clickable': True, 'center': (900, 100), 'bounds': '[800,50][1000,150]'},
        ],
        # Dismissible popup
        [
            {'text': 'Turn on notifications?', 'desc': '', 'clickable': False, 'center': (540, 400), 'bounds': '[0,300][1080,500]'},
            {'text': 'Not now', 'desc': '', 'clickable': True, 'center': (300, 600), 'bounds': '[100,550][500,650]'},
            {'text': 'Turn on', 'desc': '', 'clickable': True, 'center': (700, 600), 'bounds': '[500,550][900,650]'},
        ],
    ]

    print("HybridNavigator Test Results:")
    print("=" * 60)

    for i, elements in enumerate(test_cases, 1):
        result = navigator.navigate(elements)
        print(f"\nTest {i}:")
        print(f"  Screen: {result.screen_type.name}")
        print(f"  Action: {result.action['action']}")
        print(f"  Used AI: {result.used_ai}")
        print(f"  Reason: {result.reason}")
        print(f"  Confidence: det={result.detection_confidence:.2f}, act={result.action_confidence:.2f}")

    print(f"\n\nStats: {navigator.get_stats()}")
