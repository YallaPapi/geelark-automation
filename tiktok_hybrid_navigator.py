"""
TikTokHybridNavigator - Combines TikTokScreenDetector + TikTokActionEngine with AI fallback.

Part of the TikTok Hybrid Posting System.
Reduces AI calls by 80-90% through deterministic rule-based navigation.
"""
import time
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

from tiktok_screen_detector import TikTokScreenDetector, TikTokScreenType, DetectionResult
from tiktok_action_engine import TikTokActionEngine, ActionType, Action


@dataclass
class NavigationResult:
    """Result of hybrid navigation decision."""
    action: Dict[str, Any]  # Action dict compatible with existing code
    used_ai: bool           # Whether AI was called
    screen_type: TikTokScreenType
    detection_confidence: float
    action_confidence: float
    reason: str


class TikTokHybridNavigator:
    """Hybrid navigation: rule-based detection with AI fallback for TikTok.

    Flow:
    1. TikTokScreenDetector analyzes UI elements
    2. If high confidence (>70%), TikTokActionEngine decides action
    3. If low confidence, fall back to AI (claude_analyzer)

    This reduces AI calls from 100% to ~10-20%, saving significant API costs.
    """

    def __init__(self, ai_analyzer=None, caption: str = ""):
        """Initialize hybrid navigator.

        Args:
            ai_analyzer: AI analyzer function for fallback (takes elements, returns action dict).
            caption: Caption text for the post.
        """
        self.detector = TikTokScreenDetector()
        self.engine = TikTokActionEngine(caption=caption)
        self.ai_analyzer = ai_analyzer
        self.caption = caption

        # State tracking
        self.video_selected = False
        self.caption_entered = False

        # Stuck detection - track consecutive same-screen appearances
        self._same_screen_attempts = 0
        self._last_screen_type = None

        # Statistics
        self.total_steps = 0
        self.ai_calls = 0
        self.rule_based_steps = 0

    def update_state(self, video_selected: bool = None, caption_entered: bool = None):
        """Update posting state."""
        if video_selected is not None:
            self.video_selected = video_selected
            self.engine.video_selected = video_selected
        if caption_entered is not None:
            self.caption_entered = caption_entered
            self.engine.caption_entered = caption_entered

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

        # Step 1b: Track stuck state
        if detection.screen_type == self._last_screen_type:
            self._same_screen_attempts += 1
            if self._same_screen_attempts >= 3:
                print(f"  [HYBRID] Stuck on {detection.screen_type.name} for {self._same_screen_attempts} attempts")
        else:
            if self._same_screen_attempts >= 3:
                print(f"  [HYBRID] Left {self._last_screen_type.name} after {self._same_screen_attempts} attempts")
            self._same_screen_attempts = 1

        self._last_screen_type = detection.screen_type

        # Step 2: If high confidence, use ActionEngine
        if detection.screen_type != TikTokScreenType.UNKNOWN:
            action = self.engine.get_action(detection.screen_type, elements)

            # Step 2b: Stuck fallback - if on same screen too long, try alternatives
            if self._same_screen_attempts >= 4 and action.action_type == ActionType.TAP:
                if detection.screen_type == TikTokScreenType.GALLERY_PICKER:
                    # Try scrolling to find different content
                    print(f"  [HYBRID] Gallery stuck! Scrolling to try different thumbnail")
                    action = Action(
                        action_type=ActionType.SWIPE,
                        swipe_direction='up',
                        reason=f"Scroll gallery to try different thumbnail (stuck fallback)",
                        confidence=0.7
                    )
                elif detection.screen_type == TikTokScreenType.CREATE_MENU:
                    # Try pressing back and retrying
                    print(f"  [HYBRID] Create menu stuck! Pressing back to retry")
                    action = Action(
                        action_type=ActionType.PRESS_KEY,
                        target_text="BACK",
                        reason=f"Press back to retry create flow (stuck fallback)",
                        confidence=0.7
                    )

            # If ActionEngine can handle it deterministically
            if action.action_type not in (ActionType.NEED_AI, ActionType.ERROR):
                self.rule_based_steps += 1
                return self._convert_action(action, detection, used_ai=False)

            # Handle error states from ActionEngine
            if action.action_type == ActionType.ERROR:
                return NavigationResult(
                    action={
                        'action': 'error',
                        'reason': action.reason,
                        'error_type': 'account_error',
                    },
                    used_ai=False,
                    screen_type=detection.screen_type,
                    detection_confidence=detection.confidence,
                    action_confidence=action.confidence,
                    reason=action.reason
                )

        # Step 3: Fall back to AI
        if self.ai_analyzer is None:
            # NO AI FALLBACK MODE (rules-only testing)
            print(f"  [HYBRID] NO AI FALLBACK - Rules cannot handle: {detection.screen_type.name}")
            print(f"  [HYBRID] Detection confidence: {detection.confidence:.2f}, Rule: {detection.matched_rule}")

            # Build element summary for debugging
            element_summary = []
            for e in elements[:10]:
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

            return NavigationResult(
                action={
                    'action': 'error',
                    'reason': error_reason,
                    'error_type': 'hybrid_rules_failed',
                    'screen_type': detection.screen_type.name,
                    'video_selected': self.video_selected,
                    'caption_entered': self.caption_entered,
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
            ai_action = self.ai_analyzer(
                elements=elements,
                caption=self.caption,
                video_selected=self.video_selected,
                caption_entered=self.caption_entered,
            )

            return NavigationResult(
                action=ai_action,
                used_ai=True,
                screen_type=detection.screen_type,
                detection_confidence=detection.confidence,
                action_confidence=ai_action.get('confidence', 0.8),
                reason=f"AI: {ai_action.get('reason', 'No reason given')}"
            )

        except Exception as e:
            print(f"  [HYBRID] AI fallback failed: {e}")
            return NavigationResult(
                action={
                    'action': 'wait',
                    'reason': f'AI fallback failed: {e}'
                },
                used_ai=True,
                screen_type=detection.screen_type,
                detection_confidence=detection.confidence,
                action_confidence=0.3,
                reason=f"AI error: {e}"
            )

    def _convert_action(self, action: Action, detection: DetectionResult,
                       used_ai: bool) -> NavigationResult:
        """Convert Action to NavigationResult with action dict."""
        # Convert ActionType to string for compatibility
        action_type_map = {
            ActionType.TAP: 'tap',
            ActionType.TAP_COORDINATE: 'tap',
            ActionType.TYPE_TEXT: 'tap_and_type',
            ActionType.SWIPE: 'scroll_down' if action.swipe_direction in ('up', None) else 'scroll_up',
            ActionType.WAIT: 'wait',
            ActionType.PRESS_KEY: 'back',
            ActionType.SUCCESS: 'done',
            ActionType.NEED_AI: 'wait',
            ActionType.ERROR: 'error',
        }

        action_dict = {
            'action': action_type_map.get(action.action_type, 'wait'),
            'element_index': action.target_element,
            'reason': action.reason,
            'confidence': action.confidence,
        }

        # Add coordinates for TAP_COORDINATE
        if action.action_type == ActionType.TAP_COORDINATE and action.coordinates:
            action_dict['coordinates'] = action.coordinates

        # Add text for typing
        if action.action_type == ActionType.TYPE_TEXT:
            action_dict['text_to_type'] = action.text_to_type

        return NavigationResult(
            action=action_dict,
            used_ai=used_ai,
            screen_type=detection.screen_type,
            detection_confidence=detection.confidence,
            action_confidence=action.confidence,
            reason=action.reason
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get navigation statistics."""
        ai_pct = (self.ai_calls / self.total_steps * 100) if self.total_steps > 0 else 0
        rule_pct = (self.rule_based_steps / self.total_steps * 100) if self.total_steps > 0 else 0

        return {
            'total_steps': self.total_steps,
            'ai_calls': self.ai_calls,
            'rule_based_steps': self.rule_based_steps,
            'ai_percentage': ai_pct,
            'rule_percentage': rule_pct,
        }


if __name__ == "__main__":
    # Test without AI fallback (rules-only mode)
    navigator = TikTokHybridNavigator(caption="Test caption #fyp")

    # Test home feed
    home_elements = [
        {'id': 'lxd', 'desc': 'Create', 'text': '', 'clickable': True},
        {'id': 'lxg', 'desc': 'Home', 'text': '', 'clickable': True},
        {'id': 'text1', 'text': 'For You', 'desc': '', 'clickable': True},
    ]
    result = navigator.navigate(home_elements)
    print(f"Home: {result.action['action']} (AI={result.used_ai}) - {result.reason}")

    # Test permission popup
    perm_elements = [
        {'id': 'grant_dialog', 'text': '', 'desc': ''},
        {'id': 'permission_message', 'text': 'Allow TikTok to take pictures?', 'desc': ''},
        {'id': 'permission_allow_foreground_only_button', 'text': 'WHILE USING THE APP', 'desc': ''},
    ]
    result = navigator.navigate(perm_elements)
    print(f"Permission: {result.action['action']} (AI={result.used_ai}) - {result.reason}")

    # Test gallery
    gallery_elements = [
        {'id': 'x4d', 'text': 'Recents', 'desc': ''},
        {'id': 'tvr', 'text': 'Next', 'desc': ''},
        {'id': 'b6x', 'desc': 'Close', 'text': ''},
    ]
    result = navigator.navigate(gallery_elements)
    print(f"Gallery: {result.action['action']} (AI={result.used_ai}) - {result.reason}")

    # Print stats
    stats = navigator.get_stats()
    print(f"\nStats: {stats}")
