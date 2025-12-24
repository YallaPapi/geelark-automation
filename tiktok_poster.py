"""
TikTok Video Poster - Hybrid Mode

Posts videos to TikTok using rule-based navigation with optional AI fallback.
Based on screen detection patterns from AI-only data collection.

Usage:
    python tiktok_poster.py <phone_name> <video_path> <caption>

Modes:
    --hybrid (default): Rule-based navigation with AI fallback
    --rules-only: Strict rule-based navigation (no AI fallback)
    --ai-only: Use AI for every decision (for flow mapping)

Example:
    python tiktok_poster.py themotivationmischief video.mp4 "Check this out! #fyp"
"""
import sys
import os
import argparse

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Import centralized config and set up environment FIRST
from config import Config, setup_environment
setup_environment()

import time
import json
import anthropic
from geelark_client import GeelarkClient

# Appium imports
from appium import webdriver
from appium.options.android import UiAutomator2Options

# Device connection management
from device_connection import DeviceConnectionManager
# UI interactions
from appium_ui_controller import AppiumUIController
# Flow logging for pattern analysis
from flow_logger import FlowLogger
# Hybrid Navigator - rule-based + AI fallback
from tiktok_hybrid_navigator import TikTokHybridNavigator
from tiktok_screen_detector import TikTokScreenType

# Screen coordinates from centralized config
SCREEN_CENTER_X = Config.SCREEN_CENTER_X
SCREEN_CENTER_Y = Config.SCREEN_CENTER_Y

# TikTok package name
TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


class TikTokPoster:
    """TikTok poster using hybrid navigation (rule-based + AI fallback)."""

    def __init__(self, phone_name, system_port=8200, appium_url=None):
        self._conn = DeviceConnectionManager(
            phone_name=phone_name,
            system_port=system_port,
            appium_url=appium_url or Config.DEFAULT_APPIUM_URL
        )
        self.client = self._conn.client
        self.phone_name = phone_name
        self._ui_controller = None

        # Claude client for AI analysis (fallback)
        self.anthropic = anthropic.Anthropic()

        # Hybrid navigator (initialized lazily with caption)
        self._hybrid_navigator = None

        # State tracking
        self.video_uploaded = False
        self.video_selected = False
        self.caption_entered = False

        # Error tracking
        self.last_error_type = None
        self.last_error_message = None

    @property
    def phone_id(self):
        return self._conn.phone_id

    @property
    def device(self):
        return self._conn.device

    @property
    def appium_driver(self):
        return self._conn.appium_driver

    @property
    def ui_controller(self):
        if self._ui_controller is None and self.appium_driver is not None:
            self._ui_controller = AppiumUIController(self.appium_driver)
        return self._ui_controller

    def adb(self, cmd, timeout=30):
        """Run ADB shell command."""
        return self._conn.adb_command(cmd, timeout=timeout)

    def tap(self, x, y):
        """Tap at coordinates using Appium."""
        if self.ui_controller:
            print(f"  [TAP] ({x}, {y})")
            self.ui_controller.tap(x, y)
        else:
            raise Exception("UI controller not initialized")

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        """Swipe gesture using Appium."""
        if self.ui_controller:
            print(f"  [SWIPE] ({x1},{y1}) -> ({x2},{y2})")
            self.ui_controller.swipe(x1, y1, x2, y2, duration_ms)
        else:
            raise Exception("UI controller not initialized")

    def type_text(self, text):
        """Type text using Appium."""
        if self.ui_controller:
            self.ui_controller.type_text(text)
        else:
            raise Exception("UI controller not initialized")

    def press_back(self):
        """Press back button."""
        if self.ui_controller:
            self.ui_controller.press_back()
        else:
            raise Exception("UI controller not initialized")

    def connect(self):
        """Connect to phone and Appium."""
        return self._conn.connect()

    def disconnect(self):
        """Disconnect and stop phone."""
        return self._conn.disconnect()

    def dump_ui(self):
        """Dump UI elements using Appium."""
        if not self.appium_driver:
            return [], ""

        try:
            page_source = self.appium_driver.page_source
            if not page_source:
                return [], ""

            import xml.etree.ElementTree as ET
            root = ET.fromstring(page_source)

            elements = []
            for elem in root.iter():
                bounds_str = elem.get('bounds', '')
                if not bounds_str:
                    continue

                import re
                match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
                if not match:
                    continue

                x1, y1, x2, y2 = map(int, match.groups())
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2

                element = {
                    'bounds': bounds_str,
                    'center': (center_x, center_y),
                    'text': elem.get('text', ''),
                    'desc': elem.get('content-desc', ''),
                    'id': elem.get('resource-id', '').split('/')[-1] if elem.get('resource-id') else '',
                    'class': elem.tag,
                    'clickable': elem.get('clickable', 'false') == 'true',
                    'enabled': elem.get('enabled', 'false') == 'true',
                }
                elements.append(element)

            return elements, page_source

        except Exception as e:
            print(f"  dump_ui error: {e}")
            return [], ""

    def upload_video(self, video_path):
        """Upload video to phone via Geelark API."""
        if self.video_uploaded:
            print("  Video already uploaded")
            return

        print(f"\nUploading video: {video_path}")

        # Upload to Geelark cloud first
        resource_url = self.client.upload_file_to_geelark(video_path)
        print(f"  Cloud: {resource_url}")

        # Then push to phone
        upload_result = self.client.upload_file_to_phone(self.phone_id, resource_url)
        task_id = upload_result.get("taskId")
        self.client.wait_for_upload(task_id)
        print("  Video on phone!")
        self.video_uploaded = True

    def detect_error_state(self, elements=None):
        """Detect account/app error states from UI."""
        if elements is None:
            elements, _ = self.dump_ui()

        all_text = ' '.join([
            (e.get('text', '') + ' ' + e.get('desc', '')).lower()
            for e in elements
        ])

        error_patterns = {
            'banned': [
                'your account was permanently banned',
                'account has been banned',
                'this account was banned',
            ],
            'suspended': [
                'account suspended',
                'temporarily suspended',
                'account has been suspended',
            ],
            'logged_out': [
                'log in to tiktok',
                'sign up for tiktok',
            ],
            'captcha': [
                'verify you are human',
                'security verification',
                'slide to verify',
            ],
            'restriction': [
                'you cannot post',
                'posting is restricted',
            ],
        }

        for error_type, patterns in error_patterns.items():
            for pattern in patterns:
                if pattern in all_text:
                    return (error_type, pattern)

        return (None, None)

    def ai_analyze(self, elements, caption, video_selected, caption_entered):
        """AI fallback analysis using Claude."""
        element_descriptions = []
        for i, elem in enumerate(elements[:50]):
            parts = [f"[{i}]"]
            if elem['text']:
                parts.append(f"text='{elem['text'][:50]}'")
            if elem['desc']:
                parts.append(f"desc='{elem['desc'][:50]}'")
            if elem['id']:
                parts.append(f"id='{elem['id']}'")
            parts.append(f"bounds={elem['bounds']}")
            parts.append(f"center={elem['center']}")
            element_descriptions.append(' '.join(parts))

        elements_text = '\n'.join(element_descriptions)

        prompt = f"""You are controlling TikTok Android app to post a video.

CURRENT STATE:
- Video uploaded to phone: True
- Video selected in gallery: {video_selected}
- Caption entered: {caption_entered}

CAPTION TO POST:
{caption}

UI ELEMENTS ({len(elements)} total, showing first 50):
{elements_text}

YOUR TASK:
1. Analyze the current TikTok screen
2. Decide the SINGLE next action to progress toward posting

ACTIONS:
- tap: Click an element (specify element_index)
- tap_and_type: Tap field and type text (for caption entry)
- scroll_down: Scroll down to see more content
- scroll_up: Scroll up
- back: Press back button
- wait: Wait for something to load
- done: Video has been successfully posted
- error: Unrecoverable error (explain in reason)

RESPONSE (JSON only):
{{"action": "<action>", "element_index": <num or null>, "text_to_type": "<text or null>", "reason": "<brief explanation>", "confidence": <0.0-1.0>}}"""

        try:
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.content[0].text.strip()

            # Clean JSON if wrapped in markdown
            if content.startswith('```'):
                content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()

            return json.loads(content)
        except Exception as e:
            print(f"  AI analysis error: {e}")
            return {'action': 'wait', 'reason': f'AI error: {e}', 'confidence': 0.3}

    def post(self, video_path, caption, max_steps=30, use_hybrid=True, ai_fallback=True):
        """Main posting flow with hybrid navigation.

        Args:
            video_path: Path to video file
            caption: Caption text for the post
            max_steps: Maximum navigation steps
            use_hybrid: If True (default), use rule-based navigation
            ai_fallback: If True (default), AI rescues when rules fail
        """
        # Initialize flow logger
        flow_logger = FlowLogger(self.phone_name, log_dir="tiktok_flow_analysis")

        # Navigation mode setup
        if use_hybrid:
            # Initialize Hybrid Navigator - rule-based detection
            ai_analyzer = None
            if ai_fallback:
                ai_analyzer = lambda elements, **kwargs: self.ai_analyze(
                    elements, caption,
                    kwargs.get('video_selected', self.video_selected),
                    kwargs.get('caption_entered', self.caption_entered)
                )
            self._hybrid_navigator = TikTokHybridNavigator(
                ai_analyzer=ai_analyzer,
                caption=caption
            )
            if ai_fallback:
                print(f"[HYBRID MODE] Rule-based navigation with AI fallback")
            else:
                print(f"[HYBRID MODE] RULES-ONLY - NO AI fallback (testing mode)")
        else:
            self._hybrid_navigator = None
            print(f"[AI-ONLY MODE] Using Claude for every navigation decision")

        # Upload video first
        self.upload_video(video_path)

        # Open TikTok
        print("\nOpening TikTok...")
        self.adb(f"am force-stop {TIKTOK_PACKAGE}")
        time.sleep(2)
        self.adb(f"monkey -p {TIKTOK_PACKAGE} 1")
        time.sleep(5)

        # Scroll down to reset feed position
        print("Resetting feed position...")
        self.swipe(SCREEN_CENTER_X, 1000, SCREEN_CENTER_X, 400, 300)
        time.sleep(1)

        # Vision-action loop
        for step in range(max_steps):
            print(f"\n--- Step {step + 1} ---")

            # Dump UI
            elements, raw_xml = self.dump_ui()
            if not elements:
                print("  No UI elements found, waiting...")
                time.sleep(2)
                continue

            # Check for account/app errors
            error_type, error_msg = self.detect_error_state(elements)
            if error_type:
                print(f"  [ERROR DETECTED] {error_type}: {error_msg}")
                self.last_error_type = error_type
                self.last_error_message = f"{error_type}: {error_msg}"
                flow_logger.log_error(error_type, error_msg, elements)
                flow_logger.close()
                return False

            # Show elements summary
            print(f"  Found {len(elements)} elements")
            for elem in elements[:20]:
                parts = []
                if elem['text']:
                    parts.append(f"'{elem['text'][:40]}'")
                if elem['desc']:
                    parts.append(f"desc='{elem['desc'][:40]}'")
                if elem['id']:
                    parts.append(f"id='{elem['id']}'")
                if parts:
                    print(f"    {elem['bounds']} {' | '.join(parts)}")
            if len(elements) > 20:
                print(f"    ... and {len(elements) - 20} more elements")

            # Navigation: Hybrid (rule-based + AI fallback) or AI-only
            ai_called = False
            try:
                if self._hybrid_navigator is not None:
                    # HYBRID MODE: Rule-based detection with AI fallback
                    print("  Analyzing (hybrid)...")

                    # Sync state with hybrid navigator
                    self._hybrid_navigator.update_state(
                        video_selected=self.video_selected,
                        caption_entered=self.caption_entered
                    )

                    # Get navigation decision
                    nav_result = self._hybrid_navigator.navigate(elements)
                    action = nav_result.action
                    ai_called = nav_result.used_ai

                    # Log whether rule-based or AI was used
                    if nav_result.used_ai:
                        print(f"  [AI FALLBACK] {nav_result.screen_type.name} -> {action['action']}")
                    else:
                        print(f"  [RULE] {nav_result.screen_type.name} -> {action['action']} (conf={nav_result.action_confidence:.2f})")

                else:
                    # AI-ONLY MODE: Use Claude for every decision
                    print("  Analyzing (AI-only)...")
                    action = self.ai_analyze(elements, caption, self.video_selected, self.caption_entered)
                    ai_called = True
                    print(f"  [AI] -> {action['action']}")

            except Exception as e:
                print(f"  Analysis error: {e}")
                flow_logger.log_error("analysis_error", str(e), elements)
                time.sleep(2)
                continue

            print(f"  Action: {action['action']} - {action.get('reason', '')}")

            # Log the step for pattern analysis
            flow_logger.log_step(
                elements=elements,
                action=action,
                ai_called=ai_called,
                ai_tokens=0,
                state={
                    'video_uploaded': self.video_uploaded,
                    'video_selected': self.video_selected,
                    'caption_entered': self.caption_entered,
                },
                result="pending"
            )

            # Update state from action engine (video_selected is set when video thumbnail is tapped)
            if self._hybrid_navigator is not None:
                # Sync state back from action engine
                if self._hybrid_navigator.engine.video_selected and not self.video_selected:
                    self.video_selected = True
                    print("  [STATE] video_selected = True (synced from action engine)")
                if self._hybrid_navigator.engine.caption_entered and not self.caption_entered:
                    self.caption_entered = True
                    print("  [STATE] caption_entered = True (synced from action engine)")

            # Also detect caption screen directly from UI
            post_gallery_indicators = ['fpj', 'd1k', 'auj', 'pvl', 'pwo']  # Caption screen IDs
            element_ids = [e.get('id', '') for e in elements]

            if not self.video_selected:
                if any(pid in element_ids for pid in post_gallery_indicators):
                    self.video_selected = True
                    print("  [STATE] video_selected = True (detected caption screen)")

            # Execute action
            action_name = action['action']

            # Special case: 'done' - success
            if action_name == 'done':
                print("\n[SUCCESS] Video posted!")
                if self._hybrid_navigator is not None:
                    stats = self._hybrid_navigator.get_stats()
                    print(f"\n[SUCCESS] Post completed in {step + 1} steps (HYBRID MODE)")
                    print(f"  Rule-based: {stats['rule_based_steps']} steps ({stats['rule_percentage']:.1f}%)")
                    print(f"  AI calls: {stats['ai_calls']} ({stats['ai_percentage']:.1f}%)")
                else:
                    print(f"\n[SUCCESS] Post completed in {step + 1} steps (AI-only mode)")
                flow_logger.log_success()
                flow_logger.close()
                return True

            # Special case: 'error' - abort
            if action_name == 'error':
                error_reason = action.get('reason', 'Unknown error')
                print(f"\n[ERROR] {error_reason}")
                self.last_error_type = action.get('error_type', 'posting_error')
                self.last_error_message = error_reason
                flow_logger.log_failure(f"error: {error_reason}")
                flow_logger.close()
                return False

            # Execute standard actions
            try:
                if action_name == 'tap':
                    elem_idx = action.get('element_index')
                    if elem_idx is not None and 0 <= elem_idx < len(elements):
                        elem = elements[elem_idx]
                        print(f"  Tapping element {elem_idx} at {elem['center']}")
                        self.tap(elem['center'][0], elem['center'][1])
                    elif action.get('coordinates'):
                        x, y = action['coordinates']
                        print(f"  Tapping coordinates ({x}, {y})")
                        self.tap(x, y)

                elif action_name == 'tap_and_type':
                    elem_idx = action.get('element_index')
                    text_to_type = action.get('text_to_type', caption)
                    if elem_idx is not None and 0 <= elem_idx < len(elements):
                        elem = elements[elem_idx]
                        print(f"  Tapping element {elem_idx} and typing caption...")
                        self.tap(elem['center'][0], elem['center'][1])
                        time.sleep(0.5)
                        print(f"    Typing via Appium ({len(text_to_type)} chars)...")
                        self.type_text(text_to_type)
                        self.caption_entered = True
                        self._hybrid_navigator.update_state(caption_entered=True) if self._hybrid_navigator else None
                        print(f"    Caption entered!")

                elif action_name in ('scroll_down', 'swipe_up'):
                    print("  Scrolling down")
                    self.swipe(SCREEN_CENTER_X, 1000, SCREEN_CENTER_X, 400, 300)

                elif action_name in ('scroll_up', 'swipe_down'):
                    print("  Scrolling up")
                    self.swipe(SCREEN_CENTER_X, 400, SCREEN_CENTER_X, 1000, 300)

                elif action_name == 'back':
                    print("  Pressing back")
                    self.press_back()

                elif action_name == 'wait':
                    wait_time = action.get('wait_seconds', 2)
                    print(f"  Waiting {wait_time}s")
                    time.sleep(wait_time)

            except Exception as e:
                print(f"  Action execution error: {e}")
                flow_logger.log_error("action_error", str(e), elements)
                # Check if UiAutomator2 crashed
                if 'instrumentation process is not running' in str(e):
                    print("  [ERROR] UiAutomator2 crashed!")
                    self.last_error_type = "uiautomator2_crash"
                    self.last_error_message = str(e)
                    flow_logger.close()
                    return False

            time.sleep(1)

        print(f"\n[FAILED] Max steps ({max_steps}) reached")
        self.last_error_type = "max_steps"
        self.last_error_message = f"Max steps ({max_steps}) reached without completing post"
        flow_logger.log_failure("max_steps_reached")
        flow_logger.close()
        return False


def main():
    parser = argparse.ArgumentParser(description='Post video to TikTok')
    parser.add_argument('phone_name', help='Geelark phone name')
    parser.add_argument('video_path', help='Path to video file')
    parser.add_argument('caption', help='Caption for the video')
    parser.add_argument('--hybrid', action='store_true', default=True,
                        help='Use hybrid navigation (default)')
    parser.add_argument('--rules-only', action='store_true',
                        help='Use rules-only mode (no AI fallback)')
    parser.add_argument('--ai-only', action='store_true',
                        help='Use AI-only mode (for flow mapping)')
    parser.add_argument('--max-steps', type=int, default=30,
                        help='Maximum navigation steps (default: 30)')

    args = parser.parse_args()

    # Validate video path
    if not os.path.exists(args.video_path):
        print(f"ERROR: Video not found: {args.video_path}")
        sys.exit(1)

    # Determine mode
    use_hybrid = True
    ai_fallback = True

    if args.ai_only:
        use_hybrid = False
        ai_fallback = False
    elif args.rules_only:
        use_hybrid = True
        ai_fallback = False

    poster = TikTokPoster(args.phone_name)
    try:
        print(f"Looking for phone: {args.phone_name}")
        poster.connect()
        print("Connected successfully!\n")

        success = poster.post(
            args.video_path,
            args.caption,
            max_steps=args.max_steps,
            use_hybrid=use_hybrid,
            ai_fallback=ai_fallback
        )

        if success:
            print("\n[COMPLETE] Video posted successfully!")
            sys.exit(0)
        else:
            print(f"\n[FAILED] {poster.last_error_type}: {poster.last_error_message}")
            sys.exit(1)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("\nCleaning up...")
        poster.disconnect()


if __name__ == "__main__":
    main()
