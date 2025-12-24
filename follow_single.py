"""
Follow a target account on Instagram via Geelark cloud phone.
Uses AI-driven navigation to navigate the follow flow.

Mirrors post_reel_smart.py for posting.

Usage:
    python follow_single.py <phone_name> <target_username>
"""
import sys
import os

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Import centralized config and set up environment FIRST
from config import Config, setup_environment
setup_environment()

import re
import time
import json
import hashlib
import xml.etree.ElementTree as ET
from collections import deque
from typing import Optional, List, Dict, Any, Tuple

import anthropic

# Appium imports
from appium import webdriver
from appium.options.android import UiAutomator2Options

# Device connection management - IMPORT, don't modify
from device_connection import DeviceConnectionManager
# AI analysis - IMPORT, don't modify
from claude_analyzer import ClaudeUIAnalyzer
# UI interactions - IMPORT, don't modify
from appium_ui_controller import AppiumUIController
# Geelark client - IMPORT, don't modify
from geelark_client import GeelarkClient
# Flow logger for step-by-step analysis - IMPORT, don't modify
from flow_logger import FlowLogger
# Hybrid follow navigator - IMPORT, don't modify
from hybrid_follow_navigator import HybridFollowNavigator
from follow_screen_detector import FollowScreenDetector, FollowScreenType

# Use centralized paths
APPIUM_SERVER = Config.DEFAULT_APPIUM_URL

# Screen coordinates from centralized config
SCREEN_CENTER_X = Config.SCREEN_CENTER_X
SCREEN_CENTER_Y = Config.SCREEN_CENTER_Y


class SmartInstagramFollower:
    """Follow a target account using AI-driven navigation.

    Mirrors SmartInstagramPoster from post_reel_smart.py.
    """

    def __init__(
        self,
        phone_name: str,
        system_port: int = 8200,
        appium_url: Optional[str] = None,
        use_hybrid: bool = True
    ):
        """
        Initialize the follower.

        Args:
            phone_name: Name of the Geelark phone
            system_port: Port for UiAutomator2 server
            appium_url: Appium server URL
            use_hybrid: Use hybrid navigator (rule-based with AI fallback)
        """
        self.use_hybrid = use_hybrid
        # Use DeviceConnectionManager for all connection lifecycle
        self._conn = DeviceConnectionManager(
            phone_name=phone_name,
            system_port=system_port,
            appium_url=appium_url or APPIUM_SERVER
        )

        # Expose client for compatibility
        self.client = self._conn.client

        # AI analyzer for UI analysis
        self._analyzer = ClaudeUIAnalyzer()
        self.anthropic = self._analyzer.client  # For backwards compatibility

        self.phone_name = phone_name

        # UI controller (created lazily when Appium is connected)
        self._ui_controller = None

        # State tracking for follow flow
        self.search_opened = False
        self.username_typed = False
        self.profile_opened = False
        self.follow_clicked = False

        # Screen history for stuck detection
        self.screen_history = deque(maxlen=3)

        # Error tracking
        self.last_error_type: Optional[str] = None
        self.last_error_message: Optional[str] = None

        # Stats
        self.ai_calls = 0
        self.total_steps = 0

    # Properties to expose connection state for compatibility
    @property
    def phone_id(self) -> Optional[str]:
        return self._conn.phone_id

    @property
    def device(self) -> Optional[str]:
        return self._conn.device

    @property
    def appium_driver(self) -> Optional[webdriver.Remote]:
        return self._conn.appium_driver

    @property
    def system_port(self) -> int:
        return self._conn.system_port

    @property
    def appium_url(self) -> str:
        return self._conn.appium_url

    @property
    def ui_controller(self) -> Optional[AppiumUIController]:
        """Get or create the UI controller (requires Appium to be connected)."""
        if self._ui_controller is None and self.appium_driver is not None:
            self._ui_controller = AppiumUIController(self.appium_driver)
        return self._ui_controller

    def adb(self, cmd: str, timeout: int = 30) -> str:
        """Run ADB shell command - delegates to DeviceConnectionManager."""
        return self._conn.adb_command(cmd, timeout=timeout)

    def connect(self) -> bool:
        """Find phone and connect via ADB - delegates to DeviceConnectionManager."""
        return self._conn.connect()

    def tap(self, x: int, y: int) -> None:
        """Tap at coordinates using Appium."""
        if self.ui_controller:
            self.ui_controller.tap(x, y)
        elif self.appium_driver:
            self.appium_driver.tap([(x, y)])
        else:
            raise Exception("Appium driver not connected - cannot tap")

    def press_key(self, keycode: str) -> None:
        """Press a key using Appium."""
        if self.ui_controller:
            self.ui_controller.press_key(keycode)
        elif self.appium_driver:
            key_map = {
                'KEYCODE_BACK': 4,
                'KEYCODE_HOME': 3,
                'KEYCODE_ENTER': 66,
            }
            key = key_map.get(keycode, keycode)
            if isinstance(key, int):
                self.appium_driver.press_keycode(key)
        else:
            raise Exception("Appium driver not connected - cannot press key")

    def type_text(self, text: str) -> bool:
        """Type text using Appium."""
        if self.ui_controller:
            return self.ui_controller.type_text(text)
        return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        """Swipe from one point to another."""
        if self.ui_controller:
            self.ui_controller.swipe(x1, y1, x2, y2, duration_ms)
        elif self.appium_driver:
            self.appium_driver.swipe(x1, y1, x2, y2, duration_ms)
        else:
            raise Exception("Appium driver not connected - cannot swipe")

    def dump_ui(self) -> Tuple[List[Dict[str, Any]], str]:
        """Dump UI hierarchy and return parsed elements.

        Returns:
            Tuple of (elements list, raw XML string)
        """
        elements = []
        xml_str = ""

        if not self.appium_driver:
            raise Exception("Appium driver not connected - cannot dump UI")

        try:
            xml_str = self.appium_driver.page_source
        except Exception as e:
            error_str = str(e)
            raise Exception(f"UI dump failed: {error_str[:100]}")

        if '<?xml' not in xml_str:
            return elements, xml_str

        xml_clean = xml_str[xml_str.find('<?xml'):]

        try:
            root = ET.fromstring(xml_clean)

            # Appium uses class names as tags, not <node>
            for elem in root.iter():
                text = elem.get('text', '') or ''
                desc = elem.get('content-desc', '') or ''
                res_id = elem.get('resource-id', '') or ''
                bounds = elem.get('bounds', '')
                clickable = elem.get('clickable', 'false')

                if bounds and (text or desc or clickable == 'true'):
                    # Parse bounds [x1,y1][x2,y2]
                    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if m:
                        x1, y1, x2, y2 = map(int, m.groups())
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        elements.append({
                            'text': text,
                            'desc': desc,
                            'id': res_id.split('/')[-1] if '/' in res_id else res_id,
                            'bounds': bounds,
                            'center': (cx, cy),
                            'clickable': clickable == 'true',
                            'class': elem.tag,
                        })

        except ET.ParseError as e:
            print(f"  XML parse error: {e}")

        return elements, xml_str

    def _compute_screen_signature(self, elements: List[Dict]) -> str:
        """Compute hash signature for stuck detection."""
        key_parts = []
        for elem in elements[:20]:
            text = elem.get('text', '')[:30]
            desc = elem.get('desc', '')[:30]
            bounds = elem.get('bounds', '')
            if text or desc:
                key_parts.append(f"{text}|{desc}|{bounds}")

        signature_str = "::".join(sorted(key_parts))
        return hashlib.md5(signature_str.encode()).hexdigest()[:16]

    def is_stuck(self, elements: List[Dict]) -> bool:
        """Check if stuck on same screen 3 times."""
        current_signature = self._compute_screen_signature(elements)
        self.screen_history.append(current_signature)

        if len(self.screen_history) < 3:
            return False

        return len(set(self.screen_history)) == 1

    def detect_error_state(self, elements: List[Dict]) -> Tuple[Optional[str], Optional[str]]:
        """Detect account/app error states from UI.

        Returns:
            Tuple of (error_type, error_message) or (None, None) if no error.
        """
        all_text = ' '.join([
            (e.get('text', '') + ' ' + e.get('desc', '')).lower()
            for e in elements
        ])

        # Error patterns to detect
        error_patterns = {
            'terminated': [
                'we disabled your account',
                'your account has been permanently disabled',
                'you no longer have access to',
            ],
            'suspended': [
                'account has been suspended',
                'account has been disabled',
                'your account was disabled',
                'account is disabled',
            ],
            'verification': [
                'confirm your identity',
                'upload a photo of your id',
                'verify your identity',
                'identity verification',
            ],
            'captcha': [
                'confirm it\'s you',
                'we detected unusual activity',
                'security check',
                'enter the code',
            ],
            'action_blocked': [
                'action blocked',
                'try again later',
                'we limit how often',
                'you\'re temporarily blocked',
            ],
            'logged_out': [
                'log in to instagram',
                'create new account',
                'don\'t have an account',
            ],
        }

        for error_type, patterns in error_patterns.items():
            for pattern in patterns:
                if pattern in all_text:
                    return (error_type, pattern)

        return (None, None)

    def detect_already_following(self, elements: List[Dict]) -> bool:
        """Check if we're already following this account."""
        for elem in elements:
            text = elem.get('text', '').lower()
            desc = elem.get('desc', '').lower()
            if text == 'following' or 'following' in desc:
                # Check if it's a button (not just text)
                if elem.get('clickable'):
                    return True
        return False

    def detect_follow_success(self, elements: List[Dict]) -> bool:
        """Check if follow was successful (button changed to Following/Requested)."""
        for elem in elements:
            text = elem.get('text', '').lower()
            if text in ['following', 'requested']:
                return True
        return False

    def _build_follow_prompt(
        self,
        elements: List[Dict],
        target_username: str
    ) -> str:
        """Build AI prompt for follow navigation."""
        # Build element descriptions for Claude
        elements_text = []
        for i, elem in enumerate(elements):
            parts = [f"[{i}]"]
            if elem['text']:
                parts.append(f"text='{elem['text']}'")
            if elem['desc']:
                parts.append(f"desc='{elem['desc']}'")
            parts.append(f"bounds={elem['bounds']}")
            if elem['clickable']:
                parts.append("(clickable)")
            elements_text.append(" ".join(parts))

        elements_str = "\n".join(elements_text)

        prompt = f"""You are automating Instagram to follow a target account.

TARGET USERNAME TO FOLLOW: {target_username}

CURRENT STATE:
- Search opened: {self.search_opened}
- Username typed: {self.username_typed}
- Profile opened: {self.profile_opened}
- Follow clicked: {self.follow_clicked}

UI ELEMENTS:
{elements_str}

FOLLOW FLOW:
1. From home feed (has stories at top), tap Search icon (magnifying glass in bottom nav)
2. You'll land on EXPLORE page (grid of photos/videos). Tap "Search" text/bar at TOP of screen
3. Search input opens. Type the target username (without @)
4. Press ENTER to submit the search (action: "enter")
5. Results page may show tabs like "Accounts", "Tags", "Places" - tap "Accounts" tab
6. Find and tap the matching account name in results
7. On profile page, tap the "Follow" button
8. Verify: button changes to "Following" or "Requested" = done!

SCREEN IDENTIFICATION:
- HOME FEED: Has stories row at top (Your story, friend stories), posts below
- EXPLORE PAGE: Grid of photos/videos filling most of screen, "Search" at top
- SEARCH INPUT: Shows "Recent" searches, previous search terms visible. Just TYPE the username!
- SEARCH RESULTS: List of accounts/hashtags/places, usually shows "Accounts" tab
- PROFILE PAGE: Profile picture, username, bio, Follow/Following button, post count

YOUR TASK:
Analyze the current screen and decide the next action.

RESPOND IN THIS JSON FORMAT ONLY:
{{
    "screen": "home_feed" | "explore_page" | "search_input" | "search_results" | "profile_page" | "other",
    "action": "tap" | "type" | "enter" | "back" | "scroll_down" | "wait" | "done" | "error",
    "element_index": <index if tapping>,
    "text": "<text if typing>",
    "reason": "why this action",
    "search_opened": true/false,
    "username_typed": true/false,
    "profile_opened": true/false,
    "follow_clicked": true/false
}}

CRITICAL RULES:
- On EXPLORE PAGE (photo grid): Look for "Search" element at TOP and tap it
- On SEARCH INPUT (see "Recent" header, recent searches): Just use "type" action with the username - search is already focused!
- AFTER typing username, MUST use "enter" action to submit search
- On SEARCH RESULTS: Look for "Accounts" tab and tap it, then tap the matching username
- Use "done" when you see "Following" or "Requested" button
- Use "error" if action blocked, logged out, or "No results found"
"""
        return prompt

    def analyze_and_decide(
        self,
        elements: List[Dict],
        target_username: str
    ) -> Dict[str, Any]:
        """Use Claude to analyze UI and decide next action."""
        self.ai_calls += 1

        prompt = self._build_follow_prompt(elements, target_username)

        try:
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                action = json.loads(json_match.group())
                return action
            else:
                return {"action": "wait", "reason": "Could not parse response"}

        except Exception as e:
            print(f"    AI error: {e}")
            return {"action": "wait", "reason": f"AI error: {e}"}

    def follow_account_hybrid(self, target_username: str, max_steps: int = 30) -> bool:
        """Hybrid follow loop - uses rule-based navigation with AI fallback.

        NOTE: connect() must be called before this method.

        Args:
            target_username: Username to follow (without @)
            max_steps: Maximum navigation steps

        Returns:
            True on success, False on failure
        """
        target_username = target_username.lstrip('@')
        print(f"\n=== Following @{target_username} (HYBRID MODE) ===")

        # Initialize flow logger
        flow_logger = FlowLogger(self.phone_name, log_dir="flow_analysis")

        # Initialize hybrid navigator WITHOUT AI fallback (testing pure rule-based)
        # Set ai_analyzer=self._analyzer to enable AI fallback if needed
        navigator = HybridFollowNavigator(
            driver=self.appium_driver,
            target_username=target_username,
            ai_analyzer=None,  # NO AI FALLBACK - pure hybrid rules testing
            logger=None
        )

        # Open Instagram
        print("\nOpening Instagram...")
        self.adb("am force-stop com.instagram.android")
        time.sleep(2)
        self.adb("monkey -p com.instagram.android 1")
        time.sleep(5)

        # Vision-action loop
        for step in range(max_steps):
            self.total_steps += 1
            print(f"\n--- Step {step + 1} ---")

            # Dump UI
            try:
                elements, raw_xml = self.dump_ui()
            except Exception as e:
                print(f"  UI dump error: {e}")
                time.sleep(2)
                continue

            if not elements:
                print("  No UI elements found, waiting...")
                time.sleep(2)
                continue

            # Stuck detection
            if self.is_stuck(elements):
                print("  [STUCK] Same screen 3 times, pressing back...")
                self.press_key('KEYCODE_BACK')
                time.sleep(1)
                self.screen_history.clear()
                continue

            # Check for errors
            error_type, error_msg = self.detect_error_state(elements)
            if error_type:
                print(f"  [ERROR] {error_type}: {error_msg}")
                self.last_error_type = error_type
                self.last_error_message = error_msg
                flow_logger.log_failure(f"{error_type}: {error_msg}")
                flow_logger.close()
                return False

            print(f"  Found {len(elements)} elements")

            # Use hybrid navigator
            nav_result = navigator.navigate(elements)

            # Log the step
            flow_logger.log_step(
                elements=elements,
                action=nav_result.action,
                ai_called=nav_result.used_ai,
                state={
                    'search_opened': navigator.search_opened,
                    'username_typed': navigator.username_typed,
                    'profile_opened': navigator.profile_opened,
                    'follow_clicked': navigator.follow_clicked,
                    'target': target_username
                }
            )

            # Update our state from navigator
            self.search_opened = navigator.search_opened
            self.username_typed = navigator.username_typed
            self.profile_opened = navigator.profile_opened
            self.follow_clicked = navigator.follow_clicked

            mode_str = "AI" if nav_result.used_ai else "RULES"
            print(f"  [{mode_str}] Screen: {nav_result.screen_type.name}")
            print(f"  [{mode_str}] Action: {nav_result.action_taken} - {nav_result.reason}")

            # Check for terminal states
            if nav_result.is_terminal:
                if nav_result.screen_type == FollowScreenType.FOLLOW_SUCCESS:
                    stats = navigator.get_stats()
                    print(f"\n[SUCCESS] Follow completed!")
                    print(f"  Total steps: {self.total_steps}")
                    print(f"  Rule-based: {stats['rule_rate_percent']:.1f}%")
                    print(f"  AI calls: {stats['ai_calls']}")
                    flow_logger.log_success()
                    flow_logger.close()
                    return True
                else:
                    # Terminal error
                    error = nav_result.action.get('error', 'Unknown error')
                    print(f"\n[ERROR] {error}")
                    self.last_error_type = nav_result.screen_type.name.lower()
                    self.last_error_message = error
                    flow_logger.log_failure(error)
                    flow_logger.close()
                    return False

            # Action was successful but not terminal - continue
            time.sleep(1)

        # Max steps reached
        stats = navigator.get_stats()
        print(f"\n[FAILED] Max steps ({max_steps}) reached")
        print(f"  Rule-based: {stats['rule_rate_percent']:.1f}%, AI calls: {stats['ai_calls']}")
        self.last_error_type = 'max_steps'
        self.last_error_message = f"Max steps ({max_steps}) reached"
        flow_logger.log_failure(f"max_steps: {self.last_error_message}")
        flow_logger.close()
        return False

    def follow_account(self, target_username: str, max_steps: int = 30) -> bool:
        """Main follow loop - navigate to target and follow them.

        NOTE: connect() must be called before this method.

        Args:
            target_username: Username to follow (without @)
            max_steps: Maximum navigation steps

        Returns:
            True on success, False on failure
        """
        # Use hybrid mode if enabled (default)
        if self.use_hybrid:
            return self.follow_account_hybrid(target_username, max_steps)

        # AI-only mode (legacy)
        target_username = target_username.lstrip('@')
        print(f"\n=== Following @{target_username} (AI-ONLY MODE) ===")

        # Initialize flow logger for step-by-step analysis
        flow_logger = FlowLogger(self.phone_name, log_dir="flow_analysis")

        # Open Instagram
        print("\nOpening Instagram...")
        self.adb("am force-stop com.instagram.android")
        time.sleep(2)
        self.adb("monkey -p com.instagram.android 1")
        time.sleep(5)

        # Vision-action loop
        for step in range(max_steps):
            self.total_steps += 1
            print(f"\n--- Step {step + 1} ---")

            # Dump UI
            try:
                elements, raw_xml = self.dump_ui()
            except Exception as e:
                print(f"  UI dump error: {e}")
                time.sleep(2)
                continue

            if not elements:
                print("  No UI elements found, waiting...")
                time.sleep(2)
                continue

            # Stuck detection
            if self.is_stuck(elements):
                print("  [STUCK] Same screen 3 times, pressing back...")
                flow_logger.log_step(
                    elements=elements,
                    action={'action': 'back', 'reason': 'stuck_detection'},
                    state={'search_opened': self.search_opened, 'username_typed': self.username_typed,
                           'profile_opened': self.profile_opened, 'follow_clicked': self.follow_clicked}
                )
                self.press_key('KEYCODE_BACK')
                time.sleep(1)
                self.screen_history.clear()
                continue

            # Check for errors
            error_type, error_msg = self.detect_error_state(elements)
            if error_type:
                print(f"  [ERROR] {error_type}: {error_msg}")
                self.last_error_type = error_type
                self.last_error_message = error_msg
                flow_logger.log_error(error_type, error_msg, elements)
                flow_logger.log_failure(f"{error_type}: {error_msg}")
                flow_logger.close()
                return False

            # Show elements
            print(f"  Found {len(elements)} elements")
            for elem in elements[:15]:
                parts = []
                if elem['text']:
                    parts.append(f"'{elem['text']}'")
                if elem['desc']:
                    parts.append(f"desc='{elem['desc']}'")
                if parts:
                    print(f"    {elem['bounds']} {' | '.join(parts)}")

            # Quick check: already following?
            if self.profile_opened and self.detect_already_following(elements):
                print("  [ALREADY FOLLOWING] Target is already followed")
                flow_logger.log_success()
                flow_logger.close()
                return True  # Consider this a success

            # Quick check: follow success?
            if self.follow_clicked and self.detect_follow_success(elements):
                print("\n[SUCCESS] Follow completed!")
                print(f"  AI calls: {self.ai_calls}, Total steps: {self.total_steps}")
                flow_logger.log_success()
                flow_logger.close()
                return True

            # Use AI to decide action
            print("  Analyzing with AI...")
            action = self.analyze_and_decide(elements, target_username)

            print(f"  Screen: {action.get('screen', 'unknown')}")
            print(f"  Action: {action['action']} - {action.get('reason', '')}")

            # Log the step
            flow_logger.log_step(
                elements=elements,
                action=action,
                ai_called=True,
                state={'search_opened': self.search_opened, 'username_typed': self.username_typed,
                       'profile_opened': self.profile_opened, 'follow_clicked': self.follow_clicked,
                       'target': target_username}
            )

            # Update state from AI response
            if action.get('search_opened'):
                self.search_opened = True
            if action.get('username_typed'):
                self.username_typed = True
            if action.get('profile_opened'):
                self.profile_opened = True
            if action.get('follow_clicked'):
                self.follow_clicked = True

            # Execute action
            action_type = action['action']

            if action_type == 'done':
                print("\n[SUCCESS] Follow completed!")
                print(f"  AI calls: {self.ai_calls}, Total steps: {self.total_steps}")
                flow_logger.log_success()
                flow_logger.close()
                return True

            elif action_type == 'error':
                error_reason = action.get('reason', 'Unknown error')
                print(f"\n[ERROR] {error_reason}")
                self.last_error_type = 'ai_detected_error'
                self.last_error_message = error_reason
                flow_logger.log_failure(f"ai_error: {error_reason}")
                flow_logger.close()
                return False

            elif action_type == 'tap':
                idx = action.get('element_index', 0)
                if 0 <= idx < len(elements):
                    x, y = elements[idx]['center']
                    print(f"  Tapping element {idx} at ({x}, {y})")
                    self.tap(x, y)
                else:
                    print(f"  Invalid element index: {idx}")

            elif action_type == 'type':
                text = action.get('text', target_username)
                print(f"  Typing: {text}")
                self.type_text(text)
                time.sleep(1)

            elif action_type == 'enter':
                print("  Pressing ENTER to search")
                self.press_key('KEYCODE_ENTER')

            elif action_type == 'back':
                print("  Pressing BACK")
                self.press_key('KEYCODE_BACK')

            elif action_type == 'scroll_down':
                print("  Scrolling down")
                self.swipe(SCREEN_CENTER_X, 1500, SCREEN_CENTER_X, 500, 300)

            elif action_type == 'wait':
                print("  Waiting...")
                time.sleep(2)

            time.sleep(1)

        # Max steps reached
        print(f"\n[FAILED] Max steps ({max_steps}) reached")
        self.last_error_type = 'max_steps'
        self.last_error_message = f"Max steps ({max_steps}) reached without completing follow"
        flow_logger.log_failure(f"max_steps: {self.last_error_message}")
        flow_logger.close()
        return False

    def cleanup(self) -> None:
        """Cleanup after follow attempt - delegates to DeviceConnectionManager."""
        print("\nCleaning up...")
        self._conn.disconnect()


def main():
    if len(sys.argv) < 3:
        print("Usage: python follow_single.py <phone_name> <target_username> [--ai-only]")
        print('Example: python follow_single.py talktrackhub someuser123')
        print('  --ai-only: Use AI-only mode (no rule-based navigation)')
        sys.exit(1)

    phone_name = sys.argv[1]
    target_username = sys.argv[2].lstrip('@')  # Remove @ if present

    # Check for --ai-only flag
    use_hybrid = '--ai-only' not in sys.argv

    follower = SmartInstagramFollower(phone_name, use_hybrid=use_hybrid)

    try:
        # Connect first (same pattern as posting)
        follower.connect()
        success = follower.follow_account(target_username)

        if success:
            print("\n=== FOLLOW SUCCESSFUL ===")
            sys.exit(0)
        else:
            print(f"\n=== FOLLOW FAILED: {follower.last_error_message} ===")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        follower.cleanup()


if __name__ == "__main__":
    main()
