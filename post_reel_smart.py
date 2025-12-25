"""
Post a video to Instagram Reels via Geelark cloud phone.
Uses uiautomator dump + Claude analysis for flexible navigation.

Usage:
    python post_reel_smart.py <phone_name> <video_path> <caption>
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

import time
import re
import json
import random
import subprocess
import xml.etree.ElementTree as ET
import anthropic
from geelark_client import GeelarkClient

# Appium imports
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy

# Device connection management (extracted for better separation)
from device_connection import DeviceConnectionManager
# AI analysis (extracted for better separation)
from claude_analyzer import ClaudeUIAnalyzer
# UI interactions (extracted for better separation)
from appium_ui_controller import AppiumUIController
# Flow logging for pattern analysis
from flow_logger import FlowLogger
# Comprehensive error debugging with screenshots
from error_debugger import ErrorDebugger
# Hybrid Navigator - rule-based + AI fallback
from hybrid_navigator import HybridNavigator

# Use centralized paths and screen coordinates
APPIUM_SERVER = Config.DEFAULT_APPIUM_URL

# Screen coordinates from centralized config
SCREEN_CENTER_X = Config.SCREEN_CENTER_X
SCREEN_CENTER_Y = Config.SCREEN_CENTER_Y
FEED_TOP_Y = Config.FEED_TOP_Y
FEED_BOTTOM_Y = Config.FEED_BOTTOM_Y
REELS_TOP_Y = Config.REELS_TOP_Y
REELS_BOTTOM_Y = Config.REELS_BOTTOM_Y
NOTIFICATIONS_TOP_Y = Config.NOTIFICATIONS_TOP_Y
STORY_NEXT_TAP_X = Config.STORY_NEXT_TAP_X
SWIPE_DURATION_FAST = Config.SWIPE_DURATION_FAST
SWIPE_DURATION_SLOW = Config.SWIPE_DURATION_SLOW
SWIPE_DURATION_MAX = Config.SWIPE_DURATION_MAX


class SmartInstagramPoster:
    def __init__(self, phone_name, system_port=8200, appium_url=None):
        # Use DeviceConnectionManager for all connection lifecycle
        self._conn = DeviceConnectionManager(
            phone_name=phone_name,
            system_port=system_port,
            appium_url=appium_url or APPIUM_SERVER
        )
        # Expose client for compatibility
        self.client = self._conn.client
        # AI analyzer for UI analysis (extracted for better separation)
        self._analyzer = ClaudeUIAnalyzer()
        self.anthropic = self._analyzer.client  # For backwards compatibility
        # Hybrid Navigator - uses rules first, falls back to AI
        self._hybrid_navigator = None  # Initialized lazily with caption
        self.phone_name = phone_name
        # UI controller (created lazily when Appium is connected)
        self._ui_controller = None
        # State tracking
        self.video_uploaded = False  # File has been ADB-pushed to device storage
        self.video_selected = False  # User has selected video in gallery UI (past GALLERY_PICKER)
        self.caption_entered = False
        self.share_clicked = False
        # Error tracking
        self.last_error_type = None
        self.last_error_message = None
        self.last_screenshot_path = None

    # Properties to expose connection state for compatibility
    @property
    def phone_id(self):
        return self._conn.phone_id

    @phone_id.setter
    def phone_id(self, value):
        self._conn.phone_id = value

    @property
    def device(self):
        return self._conn.device

    @device.setter
    def device(self, value):
        self._conn.device = value

    @property
    def appium_driver(self):
        return self._conn.appium_driver

    @appium_driver.setter
    def appium_driver(self, value):
        self._conn.appium_driver = value

    @property
    def system_port(self):
        return self._conn.system_port

    @property
    def appium_url(self):
        return self._conn.appium_url

    @property
    def ui_controller(self):
        """Get or create the UI controller (requires Appium to be connected)."""
        if self._ui_controller is None and self.appium_driver is not None:
            self._ui_controller = AppiumUIController(self.appium_driver)
        return self._ui_controller

    def adb(self, cmd, timeout=30):
        """Run ADB shell command - delegates to DeviceConnectionManager"""
        return self._conn.adb_command(cmd, timeout=timeout)

    def is_uiautomator2_crash(self, exception):
        """Check if exception indicates UiAutomator2 crashed on device"""
        return self._conn.is_uiautomator2_crash(exception)

    def reconnect_appium(self):
        """Reconnect Appium driver after UiAutomator2 crash"""
        # Reset UI controller since driver is being replaced
        self._ui_controller = None
        return self._conn.reconnect_appium()

    def tap(self, x, y):
        """Tap at coordinates using Appium - delegates to AppiumUIController"""
        if self.ui_controller:
            self.ui_controller.tap(x, y)
        else:
            raise Exception("Appium driver not connected - cannot tap")

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        """Swipe from one point to another - delegates to AppiumUIController"""
        if self.ui_controller:
            self.ui_controller.swipe(x1, y1, x2, y2, duration_ms)
        else:
            raise Exception("Appium driver not connected - cannot swipe")

    def press_key(self, keycode):
        """Press a key - delegates to AppiumUIController"""
        if self.ui_controller:
            self.ui_controller.press_key(keycode)
        else:
            raise Exception("Appium driver not connected - cannot press key")

    def random_delay(self, min_sec=0.5, max_sec=2.0):
        """Random delay between actions to appear more human"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def _humanize_scroll_feed(self):
        """Scroll through the feed randomly. Returns True if action performed."""
        print("  - Scrolling feed...")
        scroll_count = random.randint(1, 3)
        for _ in range(scroll_count):
            self.swipe(SCREEN_CENTER_X, FEED_BOTTOM_Y, SCREEN_CENTER_X, FEED_TOP_Y, random.randint(SWIPE_DURATION_SLOW, SWIPE_DURATION_MAX))
            self.random_delay(1.0, 3.0)
        # Scroll back up sometimes
        if random.random() < 0.3:
            self.swipe(SCREEN_CENTER_X, FEED_TOP_Y, SCREEN_CENTER_X, FEED_BOTTOM_Y, SWIPE_DURATION_FAST)
            self.random_delay(0.5, 1.5)
        return True

    def _humanize_view_story(self):
        """View stories randomly. Returns True if action performed."""
        print("  - Viewing a story...")
        elements, _ = self.dump_ui()
        story_elements = [e for e in elements if 'story' in e.get('desc', '').lower() and 'unseen' in e.get('desc', '').lower()]
        if not story_elements:
            return False

        story = random.choice(story_elements)
        self.tap(story['center'][0], story['center'][1])
        view_time = random.uniform(3, 8)
        print(f"    Watching for {view_time:.1f}s...")
        time.sleep(view_time)
        # Tap through a few more stories sometimes
        if random.random() < 0.5:
            for _ in range(random.randint(1, 3)):
                self.tap(STORY_NEXT_TAP_X, SCREEN_CENTER_Y)  # Tap right side to skip to next story
                time.sleep(random.uniform(2, 5))
        # Go back
        self.press_key('KEYCODE_BACK')
        self.random_delay(1.0, 2.0)
        return True

    def _humanize_scroll_reels(self):
        """Browse reels randomly. Returns True if action performed."""
        print("  - Browsing reels...")
        elements, _ = self.dump_ui()
        reels_tab = [e for e in elements if 'reels' in e.get('desc', '').lower() and e['clickable']]
        if not reels_tab:
            return False

        self.tap(reels_tab[0]['center'][0], reels_tab[0]['center'][1])
        self.random_delay(2.0, 4.0)
        # Watch a few reels
        for _ in range(random.randint(1, 3)):
            watch_time = random.uniform(3, 10)
            print(f"    Watching reel for {watch_time:.1f}s...")
            time.sleep(watch_time)
            # Sometimes double-tap to like
            if random.random() < 0.15:
                print("    Double-tap like!")
                self.tap(SCREEN_CENTER_X, SCREEN_CENTER_Y)
                time.sleep(0.1)
                self.tap(SCREEN_CENTER_X, SCREEN_CENTER_Y)
                self.random_delay(0.5, 1.0)
            # Swipe to next reel
            self.swipe(SCREEN_CENTER_X, REELS_BOTTOM_Y, SCREEN_CENTER_X, REELS_TOP_Y, SWIPE_DURATION_SLOW)
            self.random_delay(0.5, 1.5)
        # Go back to home
        elements, _ = self.dump_ui()
        home_tab = [e for e in elements if 'home' in e.get('desc', '').lower() and e['clickable']]
        if home_tab:
            self.tap(home_tab[0]['center'][0], home_tab[0]['center'][1])
        self.random_delay(1.0, 2.0)
        return True

    def _humanize_check_notifications(self):
        """Check notifications randomly. Returns True if action performed."""
        print("  - Checking notifications...")
        elements, _ = self.dump_ui()
        notif_btn = [e for e in elements if ('notification' in e.get('desc', '').lower() or 'activity' in e.get('desc', '').lower()) and e['clickable']]
        if not notif_btn:
            return False

        self.tap(notif_btn[0]['center'][0], notif_btn[0]['center'][1])
        self.random_delay(2.0, 4.0)
        # Scroll through notifications
        if random.random() < 0.5:
            self.swipe(SCREEN_CENTER_X, NOTIFICATIONS_TOP_Y, SCREEN_CENTER_X, FEED_TOP_Y, SWIPE_DURATION_FAST)
            self.random_delay(1.0, 2.0)
        # Go back
        self.press_key('KEYCODE_BACK')
        self.random_delay(1.0, 2.0)
        return True

    def humanize_before_post(self):
        """Perform random human-like actions before posting"""
        print("\n[HUMANIZE] Performing random actions before posting...")
        actions_done = 0
        max_actions = random.randint(2, 4)

        # Dispatch table for humanize actions
        action_handlers = {
            'scroll_feed': self._humanize_scroll_feed,
            'view_story': self._humanize_view_story,
            'scroll_reels': self._humanize_scroll_reels,
            'check_notifications': self._humanize_check_notifications,
        }

        for _ in range(max_actions):
            action = random.choice(list(action_handlers.keys()))
            if action_handlers[action]():
                actions_done += 1
            if actions_done >= max_actions:
                break

        print(f"[HUMANIZE] Completed {actions_done} random actions")
        # Small delay before proceeding
        self.random_delay(1.0, 3.0)

    def humanize_after_post(self):
        """Perform random human-like actions after posting"""
        print("\n[HUMANIZE] Performing random actions after posting...")

        # Wait a bit to see the "Sharing" confirmation
        self.random_delay(2.0, 4.0)

        actions = []
        if random.random() < 0.4:
            actions.append('scroll_feed')
        if random.random() < 0.3:
            actions.append('check_profile')
        if random.random() < 0.2:
            actions.append('view_story')

        for action in actions:
            if action == 'scroll_feed':
                print("  - Scrolling feed after post...")
                for _ in range(random.randint(1, 2)):
                    self.swipe(SCREEN_CENTER_X, FEED_BOTTOM_Y, SCREEN_CENTER_X, FEED_TOP_Y, random.randint(SWIPE_DURATION_SLOW, SWIPE_DURATION_MAX))
                    self.random_delay(1.5, 3.0)

            elif action == 'check_profile':
                print("  - Checking profile...")
                elements, _ = self.dump_ui()
                profile_tab = [e for e in elements if 'profile' in e.get('desc', '').lower() and e['clickable']]
                if profile_tab:
                    self.tap(profile_tab[0]['center'][0], profile_tab[0]['center'][1])
                    self.random_delay(2.0, 4.0)
                    # Go back to home
                    elements, _ = self.dump_ui()
                    home_tab = [e for e in elements if 'home' in e.get('desc', '').lower() and e['clickable']]
                    if home_tab:
                        self.tap(home_tab[0]['center'][0], home_tab[0]['center'][1])
                    self.random_delay(1.0, 2.0)

            elif action == 'view_story':
                print("  - Viewing a story after post...")
                elements, _ = self.dump_ui()
                story_elements = [e for e in elements if 'story' in e.get('desc', '').lower() and 'unseen' in e.get('desc', '').lower()]
                if story_elements:
                    story = random.choice(story_elements)
                    self.tap(story['center'][0], story['center'][1])
                    time.sleep(random.uniform(3, 6))
                    self.press_key('KEYCODE_BACK')
                    self.random_delay(1.0, 2.0)

        print("[HUMANIZE] Post-posting actions completed")

    def wait_for_upload_complete(self, timeout=60):
        """Wait for Instagram upload to complete by polling UI.

        Returns True if upload confirmed complete, False if timeout.
        """
        print(f"  Waiting for upload to complete (max {timeout}s)...")
        start_time = time.time()
        last_progress = None
        stuck_count = 0

        while time.time() - start_time < timeout:
            elements, xml = self.dump_ui()

            # Convert all text/desc to lowercase for searching
            all_text = ' '.join([
                (e.get('text', '') + ' ' + e.get('desc', '')).lower()
                for e in elements
            ])

            # Check for success indicators
            success_indicators = [
                'your reel has been shared',
                'reel shared',
                'shared to reels',
                'post shared',
            ]
            for indicator in success_indicators:
                if indicator in all_text:
                    print(f"    Upload complete: found '{indicator}'")
                    return True

            # Check if we're back on feed/profile (upload finished)
            if 'home' in all_text and 'reels' in all_text and 'profile' in all_text:
                # We're on the main Instagram screen with bottom nav
                if 'sharing to reels' not in all_text and 'uploading' not in all_text:
                    print("    Upload complete: back on main screen")
                    return True

            # Check for still uploading
            if 'sharing to reels' in all_text or 'uploading' in all_text:
                # Try to get progress
                for e in elements:
                    text = e.get('text', '') + e.get('desc', '')
                    if '%' in text or any(c.isdigit() for c in text):
                        # Found progress indicator
                        if text != last_progress:
                            print(f"    Upload in progress: {text[:50]}")
                            last_progress = text
                            stuck_count = 0
                        else:
                            stuck_count += 1
                        break
                else:
                    print("    Upload in progress...")

            # If stuck for too long, might be done
            if stuck_count > 5:
                print("    Progress unchanged, checking if done...")

            time.sleep(2)

        print(f"    Upload wait timeout after {timeout}s")
        return False

    def detect_error_state(self, elements=None):
        """Detect account/app error states from UI.

        Returns tuple: (error_type, error_message) or (None, None) if no error.
        """
        if elements is None:
            elements, _ = self.dump_ui()

        # Combine all text for searching
        all_text = ' '.join([
            (e.get('text', '') + ' ' + e.get('desc', '')).lower()
            for e in elements
        ])

        # FIRST: Check for dismissible popups that should NOT be treated as errors
        # Meta Verified popup - has "meta verified" and subscription language
        # This is NOT an error - it's just an upsell popup that can be dismissed
        meta_verified_indicators = [
            'meta verified',
            'try meta verified',
            'get verified',
            'verification badge',
            'subscribe for',
            '$1',  # Common pricing shown
        ]
        if any(indicator in all_text for indicator in meta_verified_indicators):
            # This is Meta Verified popup - NOT an error, return None
            # The AI will dismiss this popup
            return (None, None)

        # Error patterns to detect
        error_patterns = {
            'terminated': [
                'we disabled your account',
                'your account has been permanently disabled',
                'you no longer have access to',
                'all your information will be permanently deleted',
            ],
            'suspended': [
                'account has been suspended',
                'account has been disabled',
                'your account was disabled',
                'we suspended your account',
                'account is disabled',
            ],
            'id_verification': [
                'confirm your identity',
                'upload a photo of your id',
                'verify your identity',
                'upload id',
                'government-issued id',
                'photo of your id',
                'we need to verify',
                'identity verification',
            ],
            'captcha': [
                'confirm it\'s you',
                'we detected unusual activity',
                'security check',
                'enter the code',
                'we noticed suspicious',
                'confirm your account',
            ],
            'action_blocked': [
                'action blocked',
                'try again later',
                'we limit how often',
                'you\'re temporarily blocked',
                'please wait',
            ],
            'logged_out': [
                'log in to instagram',
                'create new account',
                'don\'t have an account',
            ],
            'app_update': [
                'update instagram',
                'update required',
                'new version available',
            ],
        }

        # NOTE: 'sign up' removed from logged_out - it triggers false positives
        # on Meta Verified popup which shows "Sign up" for subscription

        for error_type, patterns in error_patterns.items():
            for pattern in patterns:
                if pattern in all_text:
                    return (error_type, pattern)

        return (None, None)

    def take_error_screenshot(self, account_name, error_type):
        """Take screenshot for error documentation.

        Returns screenshot path or None if failed.
        """
        import os
        from datetime import datetime

        # Create screenshots directory
        screenshot_dir = os.path.join(os.path.dirname(__file__), 'error_screenshots')
        os.makedirs(screenshot_dir, exist_ok=True)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{account_name}_{error_type}_{timestamp}.png"
        filepath = os.path.join(screenshot_dir, filename)

        try:
            if self.appium_driver:
                self.appium_driver.save_screenshot(filepath)
                print(f"    Screenshot saved: {filename}")
                return filepath
        except Exception as e:
            print(f"    Failed to save screenshot: {e}")

        return None

    def analyze_failure_screenshot(self, context="post failed"):
        """Capture screenshot and analyze with Claude Vision to understand failure.

        Args:
            context: Description of what was happening when failure occurred

        Returns:
            tuple: (screenshot_path, analysis_text) or (None, None) if failed
        """
        import os
        import base64
        from datetime import datetime

        # Take screenshot
        screenshot_dir = os.path.join(os.path.dirname(__file__), 'error_screenshots')
        os.makedirs(screenshot_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.phone_name}_failure_{timestamp}.png"
        filepath = os.path.join(screenshot_dir, filename)

        try:
            if not self.appium_driver:
                print("    Cannot capture screenshot - no Appium driver")
                return None, None

            self.appium_driver.save_screenshot(filepath)
            print(f"    Screenshot saved: {filename}")

            # Read and encode screenshot
            with open(filepath, 'rb') as f:
                image_data = base64.standard_b64encode(f.read()).decode('utf-8')

            # Send to Claude Vision for analysis
            print("    Analyzing screenshot with Claude Vision...")

            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": f"""Analyze this Instagram app screenshot. Context: {context}

What do you see on the screen? Look for:
1. Any error messages, popups, or warnings
2. Login/signup screens (account logged out)
3. Verification or captcha requests
4. "Action blocked" messages
5. The current screen state (feed, profile, posting flow, etc.)
6. Any buttons or text that indicate what went wrong

Provide a brief (2-3 sentence) analysis of:
- What screen is showing
- Why the post might have failed
- What action might fix it (if obvious)

Be concise and direct."""
                            }
                        ]
                    }
                ]
            )

            analysis = response.content[0].text
            print(f"    Vision analysis: {analysis[:100]}...")

            return filepath, analysis

        except Exception as e:
            print(f"    Failed to analyze screenshot: {e}")
            return filepath if os.path.exists(filepath) else None, None

    def _handle_tap_and_type(self, action, elements, caption):
        """Handle tap_and_type action - keyboard management and caption typing.

        Returns True if caller should `continue` to next loop iteration.
        """
        # Prevent re-typing if caption already entered - just tap Share instead
        if self.caption_entered:
            print("  [SKIP] Caption already entered! Tapping Share instead.")
            share_elements = [e for e in elements if e.get('text', '').lower() == 'share' or e.get('desc', '').lower() == 'share']
            if share_elements:
                self.tap(share_elements[0]['center'][0], share_elements[0]['center'][1])
                self.share_clicked = True
            return True  # continue to next step

        idx = action.get('element_index', 0)
        text = action.get('text', caption)

        # Step 1: Check if keyboard is already up
        print("  Checking if keyboard is up...")
        keyboard_up = self.is_keyboard_visible()

        if not keyboard_up:
            # Step 2: Tap the caption field
            if 0 <= idx < len(elements):
                elem = elements[idx]
                print(f"  Keyboard not up. Tapping caption field at ({elem['center'][0]}, {elem['center'][1]})")
                self.tap(elem['center'][0], elem['center'][1])
                time.sleep(1.5)

            # Step 3: Check again if keyboard is up
            print("  Checking keyboard again...")
            keyboard_up = self.is_keyboard_visible()

            if not keyboard_up:
                # Step 4: Try tapping again
                print("  Keyboard still not up. Tapping again...")
                if 0 <= idx < len(elements):
                    elem = elements[idx]
                    self.tap(elem['center'][0], elem['center'][1])
                    time.sleep(1.5)
                keyboard_up = self.is_keyboard_visible()

        if keyboard_up:
            print(f"  Keyboard is up. Typing: {text[:50]}...")
            self.type_text(text)
            time.sleep(1)

            # Step 5: Best-effort verification (uiautomator often hides caption text)
            print("  Verifying caption was typed...")
            verify_elements, _ = self.dump_ui()
            caption_found = any(text[:20] in elem.get('text', '') for elem in verify_elements)
            if caption_found:
                print("  Caption appears in UI dump.")
            else:
                print("  Caption not visible in UI dump (normal for IG caption field); assuming entered.")
            self.caption_entered = True

            # Hide keyboard
            self.press_key('KEYCODE_BACK')
            time.sleep(0.5)
        else:
            print("  ERROR: Could not get keyboard to appear. Will retry on next step.")

        return False  # don't skip, continue normally

    # --- Action handlers for dispatch table (Command pattern) ---

    def _action_home(self, action, elements):
        """Handle 'home' action - go to home screen."""
        print("  [HOME] Going to home screen...")
        self.press_key('KEYCODE_HOME')
        time.sleep(2)

    def _action_open_instagram(self, action, elements):
        """Handle 'open_instagram' action - restart Instagram app.

        Uses multiple methods with fallbacks:
        1. Appium activate_app() - most reliable on Android 15+
        2. ADB am start with explicit activity - more reliable than monkey
        3. ADB monkey command - last resort fallback
        """
        print("  [OPEN] Opening Instagram...")
        self.adb("am force-stop com.instagram.android")
        time.sleep(1)

        # Method 1: Try Appium activate_app() (most reliable)
        if self.appium_driver:
            try:
                self.appium_driver.activate_app('com.instagram.android')
                print("  [OPEN] Launched via Appium activate_app()")
                time.sleep(4)
                return
            except Exception as e:
                print(f"  [OPEN] Appium activate_app failed: {e}")

        # Method 2: Try ADB am start with explicit activity (more reliable than monkey)
        try:
            result = self.adb("am start -n com.instagram.android/com.instagram.mainactivity.LauncherActivity")
            if result and 'Error' not in result:
                print("  [OPEN] Launched via ADB am start")
                time.sleep(4)
                return
        except Exception as e:
            print(f"  [OPEN] ADB am start failed: {e}")

        # Method 3: Fallback to monkey command (least reliable)
        print("  [OPEN] Falling back to monkey command...")
        self.adb("monkey -p com.instagram.android 1")
        time.sleep(4)

    def _action_tap(self, action, elements):
        """Handle 'tap' action - tap an element by index."""
        idx = action.get('element_index', 0)
        if 0 <= idx < len(elements):
            elem = elements[idx]
            self.tap(elem['center'][0], elem['center'][1])
        else:
            print(f"  Invalid element index: {idx}")

    def _action_back(self, action, elements):
        """Handle 'back' action - press back key."""
        self.press_key('KEYCODE_BACK')

    def _action_scroll_down(self, action, elements):
        """Handle 'scroll_down' action - swipe down."""
        self.adb(f"input swipe {SCREEN_CENTER_X} {FEED_BOTTOM_Y} {SCREEN_CENTER_X} {FEED_TOP_Y} {SWIPE_DURATION_FAST}")

    def _action_scroll_up(self, action, elements):
        """Handle 'scroll_up' action - swipe up."""
        self.adb(f"input swipe {SCREEN_CENTER_X} {FEED_TOP_Y} {SCREEN_CENTER_X} {FEED_BOTTOM_Y} {SWIPE_DURATION_FAST}")

    def _action_tap_coordinate(self, action, elements):
        """Handle 'tap_coordinate' action - tap at specific x,y."""
        x = action.get('x', SCREEN_CENTER_X)
        y = action.get('y', SCREEN_CENTER_Y)
        print(f"  Tapping at coordinates ({x}, {y})")
        self.tap(x, y)

    def _action_wait(self, action, elements):
        """Handle 'wait' action - wait for specified seconds."""
        seconds = action.get('seconds', 1)
        print(f"  Waiting {seconds}s...")
        time.sleep(seconds)

    def _get_action_handlers(self):
        """Return dispatch table mapping action names to handler methods.

        Note: 'done' and 'tap_and_type' have special handling in post() and are not included.
        """
        return {
            'home': self._action_home,
            'open_instagram': self._action_open_instagram,
            'tap': self._action_tap,
            'back': self._action_back,
            'scroll_down': self._action_scroll_down,
            'scroll_up': self._action_scroll_up,
            'tap_coordinate': self._action_tap_coordinate,
            'wait': self._action_wait,
        }

    def _track_action_for_loop_detection(self, action, elements, recent_actions, loop_threshold):
        """Track action signature for loop detection.

        Modifies recent_actions in place.
        """
        action_signature = action['action']

        # Don't count 'wait' toward loop detection ONLY when we're in a legitimate upload state
        # Check for specific upload progress indicators to avoid false loop detection
        if action_signature == 'wait':
            # Check for upload progress indicators by element ID
            upload_indicators = [
                'upload_snackbar_container',      # Sharing to Reels snackbar
                'row_pending_media_progress_bar', # Progress bar in feed banner
                'progress_bar',                   # Generic progress bar
                'status_text',                    # "Sharing to Reels" text
                'row_pending_container',          # Pending upload container
            ]
            element_ids = [el.get('id', '') for el in elements]
            has_upload_progress = any(uid in element_ids for uid in upload_indicators)

            # Also check for upload-related text
            all_text = ' '.join([el.get('text', '').lower() for el in elements])
            has_upload_text = any(t in all_text for t in [
                'sharing to reels', 'posting to', 'keep instagram open', 'uploading'
            ])

            if has_upload_progress or has_upload_text:
                # Legitimate upload in progress - don't count toward loop detection
                return

        if action['action'] == 'tap' and 'element_index' in action:
            idx = action.get('element_index', 0)
            if 0 <= idx < len(elements):
                x, y = elements[idx]['center']
                action_signature = f"tap_{x}_{y}"
        recent_actions.append(action_signature)
        if len(recent_actions) > loop_threshold:
            recent_actions.pop(0)

    def _check_and_recover_from_loop(self, recent_actions, loop_recovery_count, loop_threshold, max_recoveries):
        """Check for stuck loop and attempt recovery.

        Returns tuple: (should_abort: bool, new_recovery_count: int, should_clear_actions: bool)
        """
        # Check for loop - if last N actions are all identical, we're stuck
        if len(recent_actions) < loop_threshold or len(set(recent_actions)) != 1:
            return (False, loop_recovery_count, False)  # No loop detected

        # Loop detected!
        loop_recovery_count += 1
        print(f"\n  [LOOP DETECTED] Same action '{recent_actions[0]}' repeated {loop_threshold} times!")
        print(f"  [RECOVERY] Attempt {loop_recovery_count}/{max_recoveries}")

        if loop_recovery_count > max_recoveries:
            print("  [ABORT] Too many loop recoveries, giving up")
            return (True, loop_recovery_count, False)  # Should abort

        # Recovery: press back 5 times and restart Instagram
        print("  Pressing BACK 5 times to escape stuck state...")
        for _ in range(5):
            self.press_key('KEYCODE_BACK')
            time.sleep(0.5)

        print("  Reopening Instagram...")
        self.adb("am force-stop com.instagram.android")
        time.sleep(2)
        self.adb("monkey -p com.instagram.android 1")
        time.sleep(5)

        print("  [RECOVERY] Restarted - continuing")
        return (False, loop_recovery_count, True)  # Continue, but clear actions

    def is_keyboard_visible(self):
        """Check if the keyboard is currently visible on screen"""
        # Method 1: Check dumpsys for keyboard visibility
        result = self.adb("dumpsys input_method | grep mInputShown")
        if "mInputShown=true" in result:
            return True

        # Method 2: Check window visibility
        result = self.adb("dumpsys window | grep -i keyboard")
        if "isVisible=true" in result.lower() or "mhasfocus=true" in result.lower():
            return True

        # Method 3: Check if InputMethod window is visible
        result = self.adb("dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'")
        if "InputMethod" in result:
            return True

        return False

    def type_text(self, text):
        """Type text - delegates to AppiumUIController"""
        if self.ui_controller:
            return self.ui_controller.type_text(text)
        else:
            print("    ERROR: Appium driver not connected!")
            return False

    def dump_ui(self):
        """Dump UI hierarchy and return parsed elements using Appium (required)"""
        elements = []
        xml_str = ""

        if not self.appium_driver:
            raise Exception("Appium driver not connected - cannot dump UI")

        try:
            xml_str = self.appium_driver.page_source
        except Exception as e:
            error_str = str(e)
            error_type = type(e).__name__
            print(f"  [UI DUMP ERROR] {error_type}: {error_str[:200]}")

            if self.is_uiautomator2_crash(e):
                print(f"  [RECOVERY] UiAutomator2 crashed, reconnecting...")
                if self.reconnect_appium():
                    try:
                        xml_str = self.appium_driver.page_source
                    except Exception as e2:
                        raise Exception(f"Appium reconnect failed: {type(e2).__name__}: {e2}")
                else:
                    raise Exception("Appium reconnect failed")
            else:
                # Capture full error details for debugging (safely for Windows console)
                import traceback
                try:
                    tb_str = traceback.format_exc()
                    safe_tb = tb_str.encode('ascii', 'replace').decode('ascii')
                    print(f"  [FULL ERROR]\n{safe_tb}")
                except (OSError, UnicodeEncodeError):
                    pass  # Can't print - just continue with the exception
                raise Exception(f"UI dump failed ({error_type}): {error_str[:100]}")

        if '<?xml' not in xml_str:
            return elements, xml_str

        xml_clean = xml_str[xml_str.find('<?xml'):]
        try:
            root = ET.fromstring(xml_clean)
            # Appium uses class names as tags (android.widget.TextView), not <node>
            # So iterate over ALL elements
            for elem in root.iter():
                text = elem.get('text', '')
                desc = elem.get('content-desc', '')
                res_id = elem.get('resource-id', '')
                bounds = elem.get('bounds', '')
                clickable = elem.get('clickable', 'false')

                if bounds and (text or desc or clickable == 'true'):
                    # Parse bounds [x1,y1][x2,y2]
                    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if m:
                        x1, y1, x2, y2 = map(int, m.groups())
                        cx, cy = (x1+x2)//2, (y1+y2)//2
                        elements.append({
                            'text': text,
                            'desc': desc,
                            'id': res_id.split('/')[-1] if '/' in res_id else res_id,
                            'bounds': bounds,
                            'center': (cx, cy),
                            'clickable': clickable == 'true'
                        })
        except ET.ParseError as e:
            print(f"  XML parse error: {e}")

        return elements, xml_str

    def analyze_ui(self, elements, caption):
        """Use Claude to analyze UI and decide next action - delegates to ClaudeUIAnalyzer"""
        return self._analyzer.analyze(
            elements=elements,
            caption=caption,
            video_uploaded=self.video_uploaded,
            caption_entered=self.caption_entered,
            share_clicked=self.share_clicked
        )

    def connect(self):
        """Find phone and connect via ADB - delegates to DeviceConnectionManager"""
        return self._conn.connect()

    def verify_adb_connection(self):
        """Verify device is still connected via ADB. Returns True if connected."""
        return self._conn.verify_adb_connection()

    def reconnect_adb(self):
        """Re-establish ADB connection if it dropped. Returns True on success."""
        return self._conn.reconnect_adb()

    def connect_appium(self, retries=3):
        """Connect Appium driver - REQUIRED for automation to work"""
        return self._conn.connect_appium(retries=retries)

    def validate_video(self, video_path):
        """Check if video file is valid (not corrupted).

        Returns:
            tuple: (is_valid, duration_or_error_message)
        """
        if not os.path.exists(video_path):
            return False, f"File not found: {video_path}"

        try:
            # Use ffprobe to check video metadata
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                if 'moov atom not found' in error_msg:
                    return False, "Video corrupted: missing moov atom (metadata)"
                elif 'Invalid data' in error_msg:
                    return False, "Video corrupted: invalid data"
                else:
                    return False, f"Video error: {error_msg[:100]}"

            # Parse duration
            duration_str = result.stdout.strip()
            if not duration_str:
                return False, "Video has no duration metadata"

            duration = float(duration_str)
            if duration <= 0:
                return False, "Video has zero or negative duration"

            return True, duration

        except subprocess.TimeoutExpired:
            return False, "Video validation timed out"
        except FileNotFoundError:
            # ffprobe not installed - skip validation
            print("  [WARN] ffprobe not found, skipping video validation")
            return True, "skipped"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def upload_video(self, video_path):
        """Upload video to phone"""
        print(f"\nUploading video: {video_path}")

        resource_url = self.client.upload_file_to_geelark(video_path)
        print(f"  Cloud: {resource_url}")

        upload_result = self.client.upload_file_to_phone(self.phone_id, resource_url)
        task_id = upload_result.get("taskId")
        self.client.wait_for_upload(task_id)
        print("  Video on phone!")

        # Trigger media scanner
        self.adb("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Download/")
        time.sleep(3)

        # Clean up old screenshots
        print("  Cleaning screenshots...")
        self.adb("rm -f /sdcard/DCIM/Camera/IMG_*.png")
        self.adb("rm -f /sdcard/Pictures/Screenshots/*.png")

        self.video_uploaded = True
        return True

    def post(self, video_path, caption, max_steps=30, humanize=False, job_id=None,
             use_hybrid=True, ai_fallback=True):
        """Main posting flow with smart navigation

        Args:
            video_path: Path to video file
            caption: Caption text for the post
            max_steps: Maximum navigation steps
            humanize: If True, perform random human-like actions before/after posting
            job_id: Optional job ID for error tracking
            use_hybrid: If True (default), use rule-based navigation
                        If False, use AI-only mode (for mapping NEW flows)
            ai_fallback: Only applies when use_hybrid=True
                         If True (default), AI rescues when rules fail (production mode)
                         If False, STRICT rules-only - failures expose broken rules
                         Use ai_fallback=False to TEST which rules work/fail
        """

        # Initialize flow logger for pattern analysis
        flow_logger = FlowLogger(self.phone_name, log_dir="flow_analysis")

        # Initialize error debugger for comprehensive error capture
        job_id = job_id or os.path.basename(video_path)
        self._debugger = ErrorDebugger(
            account=self.phone_name,
            job_id=job_id,
            output_dir="error_logs"
        )

        # Navigation mode setup
        if use_hybrid:
            # Initialize Hybrid Navigator - rule-based detection
            # Pass ai_analyzer only if ai_fallback is enabled
            self._hybrid_navigator = HybridNavigator(
                ai_analyzer=self._analyzer if ai_fallback else None,
                caption=caption
            )
            if ai_fallback:
                print(f"[HYBRID MODE] Enabled - rule-based navigation with AI fallback")
            else:
                print(f"[HYBRID MODE] RULES-ONLY - NO AI fallback (testing mode)")
                print(f"  WARNING: Failures will expose broken rules - this is intentional!")
        else:
            self._hybrid_navigator = None
            print(f"[AI-ONLY MODE] Using Claude for every navigation decision (flow mapping)")

        # Validate video before upload (detect corrupted files)
        print(f"\nValidating video: {video_path}")
        is_valid, result = self.validate_video(video_path)
        if not is_valid:
            self.last_error_type = "corrupted_video"
            self.last_error_message = result
            print(f"  [ERROR] {result}")
            print(f"  Skipping this video - file is corrupted or invalid")
            flow_logger.log_error(error_type="corrupted_video", error_message=result)
            return False
        else:
            if result != "skipped":
                print(f"  Video valid: {result:.1f}s duration")

        # Upload video first
        self.upload_video(video_path)

        # Open Instagram
        print("\nOpening Instagram...")
        self.adb("am force-stop com.instagram.android")
        time.sleep(2)
        self.adb("monkey -p com.instagram.android 1")
        time.sleep(5)

        # Humanize before posting
        if humanize:
            self.humanize_before_post()

        # Loop detection - track recent actions to detect stuck states
        recent_actions = []  # List of (action_type, x, y) tuples
        LOOP_THRESHOLD = 5  # If 5 consecutive same actions, we're stuck
        loop_recovery_count = 0  # How many times we've tried to recover
        MAX_LOOP_RECOVERIES = 2  # Give up after this many recovery attempts

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

                # COMPREHENSIVE ERROR CAPTURE - screenshot + full state
                self._debugger.capture_error(
                    error=Exception(f"{error_type}: {error_msg}"),
                    driver=self.appium_driver,
                    ui_elements=elements,
                    error_type=error_type,
                    phase="navigation",
                    context={
                        "step": step,
                        "caption": caption[:100],
                        "video_path": video_path,
                        "video_uploaded": self.video_uploaded,
                        "video_selected": self.video_selected,
                        "caption_entered": self.caption_entered,
                        "share_clicked": self.share_clicked
                    }
                )

                # Use Vision analysis for richer error context
                print("  [VISION] Capturing error screenshot for analysis...")
                screenshot_path, analysis = self.analyze_failure_screenshot(
                    context=f"Account/app error detected: {error_type} - '{error_msg}'"
                )
                self.last_screenshot_path = screenshot_path
                if analysis:
                    self.last_error_message = f"{error_type}: {error_msg} - Vision analysis: {analysis}"
                else:
                    self.last_error_message = f"{error_type}: {error_msg}"
                flow_logger.log_error(error_type, error_msg, elements)
                flow_logger.log_failure(f"{error_type}: {error_msg}")
                flow_logger.close()
                return False

            # Show what we see (all elements) - wrapped in try/except for Windows console safety
            try:
                print(f"  Found {len(elements)} elements")
                for elem in elements:
                    parts = []
                    text = elem.get('text') or ''
                    desc = elem.get('desc') or ''
                    if text:
                        # Sanitize text for Windows console (remove unprintable chars)
                        safe_text = str(text).encode('ascii', 'replace').decode('ascii')
                        parts.append(f"'{safe_text}'")
                    if desc:
                        safe_desc = str(desc).encode('ascii', 'replace').decode('ascii')
                        parts.append(f"desc='{safe_desc}'")
                    if parts:
                        print(f"    {elem.get('bounds', '?')} {' | '.join(parts)}")
            except (OSError, UnicodeEncodeError):
                # Windows console can't handle some chars - skip debug output
                pass

            # Navigation: Hybrid (rule-based + AI fallback) or AI-only
            ai_called = False
            try:
                if self._hybrid_navigator is not None:
                    # HYBRID MODE: Rule-based detection with AI fallback
                    print("  Analyzing (hybrid)...")

                    # Sync state with hybrid navigator
                    # NOTE: video_selected != video_uploaded
                    # video_uploaded = ADB file push complete
                    # video_selected = user has selected video in gallery (past GALLERY_PICKER screen)
                    self._hybrid_navigator.update_state(
                        video_selected=self.video_selected,
                        caption_entered=self.caption_entered,
                        share_clicked=self.share_clicked
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
                    # AI-ONLY MODE: Use Claude for every decision (for flow mapping)
                    print("  Analyzing (AI-only)...")
                    action = self.analyze_ui(elements, caption)
                    ai_called = True
                    print(f"  [AI] -> {action['action']}")
            except Exception as e:
                print(f"  Analysis error: {e}")
                # COMPREHENSIVE ERROR CAPTURE
                self._debugger.capture_error(
                    error=e,
                    driver=self.appium_driver,
                    ui_elements=elements,
                    error_type="analysis_error",
                    phase="ai_analysis",
                    context={
                        "step": step,
                        "caption": caption[:100],
                        "video_uploaded": self.video_uploaded
                    }
                )
                flow_logger.log_error("analysis_error", str(e), elements)
                time.sleep(2)
                continue

            print(f"  Action: {action['action']} - {action.get('reason', '')}")

            # Log the step for pattern analysis
            flow_logger.log_step(
                elements=elements,
                action=action,
                ai_called=ai_called,  # Track whether AI was used this step
                ai_tokens=0,  # TODO: capture actual token usage from analyzer
                state={
                    'video_uploaded': self.video_uploaded,
                    'video_selected': self.video_selected,
                    'caption_entered': self.caption_entered,
                    'share_clicked': self.share_clicked
                },
                result="pending"
            )

            # Update state based on screen progression, NOT action intent
            # This prevents state desync when an action fails silently
            #
            # video_selected: Set True when we detect post-gallery screens
            # (VIDEO_EDITING, SHARE_PREVIEW, etc.) - means user has selected a video in gallery
            #
            # Check for post-gallery indicators in current screen:
            post_gallery_indicators = [
                'clips_right_action_button',  # Video editing Next button
                'caption_input_text_view',    # Caption screen
                'share_button',               # Share screen
                'edit cover',                 # Share preview
            ]
            element_ids = [e.get('id', '') for e in elements]
            element_texts = ' '.join([e.get('text', '').lower() for e in elements])

            if not self.video_selected:
                # Set video_selected when we detect post-gallery screen elements
                # This means the video has been selected in the gallery UI
                if any(pid in element_ids for pid in post_gallery_indicators[:2]):
                    self.video_selected = True
                    print("  [STATE] video_selected = True (detected VIDEO_EDITING screen)")
                elif 'edit cover' in element_texts or 'write a caption' in element_texts:
                    self.video_selected = True
                    print("  [STATE] video_selected = True (detected caption/share screen)")

            if action.get('share_clicked'):
                self.share_clicked = True

            # Execute action using dispatch table (Command pattern)
            action_name = action['action']

            # Special case: 'done' - returns from function
            if action_name == 'done':
                print("\n[SUCCESS] Share initiated!")
                # Wait for upload to actually complete (poll UI for confirmation)
                if self.wait_for_upload_complete(timeout=60):
                    print("[SUCCESS] Upload confirmed complete!")
                else:
                    print("[WARNING] Upload confirmation timeout - may still be processing")
                if humanize:
                    self.humanize_after_post()
                # Log success with stats
                if self._hybrid_navigator is not None:
                    stats = self._hybrid_navigator.get_stats()
                    print(f"\n[SUCCESS] Post completed in {step + 1} steps (HYBRID MODE)")
                    print(f"  Rule-based: {stats['rule_based_steps']} steps ({stats['rule_rate_percent']:.1f}%)")
                    print(f"  AI calls: {stats['ai_calls']} ({stats['ai_rate_percent']:.1f}%)")
                    print(f"  Estimated savings: ${stats['estimated_savings_per_post']:.2f}")
                else:
                    print(f"\n[SUCCESS] Post completed in {step + 1} steps (AI-only mode)")
                flow_logger.log_success()
                flow_logger.close()
                return True

            # Special case: 'error' - abort posting
            if action_name == 'error':
                error_reason = action.get('reason', 'Unknown error from AI analysis')
                print(f"\n[ERROR] {error_reason}")
                self.last_error_type = action.get('error_type', 'ai_error')
                self.last_error_message = error_reason
                flow_logger.log_failure(f"ai_error: {error_reason}")
                flow_logger.close()
                return False

            # Special case: 'tap_and_type' - needs caption and has continue logic
            if action_name == 'tap_and_type':
                if self._handle_tap_and_type(action, elements, caption):
                    continue  # Helper handled it and wants to skip to next step

            # Dispatch table for standard actions
            action_handlers = self._get_action_handlers()
            if action_name in action_handlers:
                action_handlers[action_name](action, elements)

            # Track action and check for stuck loops
            self._track_action_for_loop_detection(action, elements, recent_actions, LOOP_THRESHOLD)
            should_abort, loop_recovery_count, should_clear = self._check_and_recover_from_loop(
                recent_actions, loop_recovery_count, LOOP_THRESHOLD, MAX_LOOP_RECOVERIES
            )
            if should_abort:
                # COMPREHENSIVE ERROR CAPTURE
                self._debugger.capture_error(
                    error=Exception(f"Loop stuck on action: {recent_actions[-1] if recent_actions else 'unknown'}"),
                    driver=self.appium_driver,
                    ui_elements=elements,
                    error_type="loop_stuck",
                    phase="navigation",
                    context={
                        "step": step,
                        "recent_actions": recent_actions[-10:],
                        "loop_recovery_count": loop_recovery_count,
                        "video_uploaded": self.video_uploaded,
                        "video_selected": self.video_selected,
                        "caption_entered": self.caption_entered,
                        "share_clicked": self.share_clicked
                    }
                )

                # Capture and analyze failure screenshot
                print("  [VISION] Capturing failure screenshot for analysis...")
                screenshot_path, analysis = self.analyze_failure_screenshot(
                    context=f"Loop recovery failed after {MAX_LOOP_RECOVERIES} attempts. Last action: {recent_actions[-1] if recent_actions else 'unknown'}"
                )
                self.last_screenshot_path = screenshot_path
                if analysis:
                    self.last_error_message = f"Loop stuck - Vision analysis: {analysis}"
                    self.last_error_type = "loop_stuck"
                else:
                    self.last_error_message = "Loop recovery failed - could not escape stuck state"
                    self.last_error_type = "loop_stuck"
                flow_logger.log_failure(f"loop_stuck: {self.last_error_message}")
                flow_logger.close()
                return False
            if should_clear:
                recent_actions.clear()
                # CRITICAL: Reset posting state when starting fresh after loop recovery
                # This prevents the bug where caption_entered=True persists but caption
                # wasn't actually typed in the new posting attempt
                print("  [RECOVERY] Resetting posting state for fresh attempt...")
                self.video_selected = False  # Will need to select video again
                self.caption_entered = False  # MUST re-type caption
                self.share_clicked = False  # Haven't clicked share yet
                # Note: video_uploaded stays True since file is still on device

                # Also reset the HybridNavigator's internal state
                if self._hybrid_navigator is not None:
                    self._hybrid_navigator.update_state(
                        video_selected=False,
                        caption_entered=False,
                        share_clicked=False
                    )

            time.sleep(1)

        print(f"\n[FAILED] Max steps ({max_steps}) reached")

        # Get final UI state for error capture
        try:
            final_elements, _ = self.dump_ui()
        except:
            final_elements = []

        # COMPREHENSIVE ERROR CAPTURE
        self._debugger.capture_error(
            error=Exception(f"Max steps ({max_steps}) reached"),
            driver=self.appium_driver,
            ui_elements=final_elements,
            error_type="max_steps",
            phase="navigation",
            context={
                "max_steps": max_steps,
                "video_uploaded": self.video_uploaded,
                "video_selected": self.video_selected,
                "caption_entered": self.caption_entered,
                "share_clicked": self.share_clicked,
                "caption": caption[:100]
            }
        )

        # Capture and analyze failure screenshot
        print("  [VISION] Capturing failure screenshot for analysis...")
        screenshot_path, analysis = self.analyze_failure_screenshot(
            context=f"Max steps ({max_steps}) reached without completing post. Caption entered: {self.caption_entered}, Share clicked: {self.share_clicked}"
        )
        self.last_screenshot_path = screenshot_path
        if analysis:
            self.last_error_message = f"Max steps reached - Vision analysis: {analysis}"
            self.last_error_type = "max_steps"
        else:
            self.last_error_message = f"Max steps ({max_steps}) reached without completing post"
            self.last_error_type = "max_steps"
        flow_logger.log_failure(f"max_steps: {self.last_error_message}")
        flow_logger.close()
        return False

    def cleanup(self):
        """Cleanup after posting - delegates to DeviceConnectionManager"""
        print("\nCleaning up...")
        try:
            self.adb("rm -f /sdcard/Download/*.mp4")
        except Exception:
            pass  # Ignore cleanup errors - video deletion is best-effort
        # Delegate connection cleanup to DeviceConnectionManager
        self._conn.disconnect()


def main():
    if len(sys.argv) < 4:
        print("Usage: python post_reel_smart.py <phone_name> <video_path> <caption>")
        print('Example: python post_reel_smart.py talktrackhub video.mp4 "Check this out!"')
        sys.exit(1)

    phone_name = sys.argv[1]
    video_path = sys.argv[2]
    caption = sys.argv[3]

    if not os.path.exists(video_path):
        print(f"Video not found: {video_path}")
        sys.exit(1)

    poster = SmartInstagramPoster(phone_name)

    try:
        poster.connect()
        success = poster.post(video_path, caption)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        poster.cleanup()


if __name__ == "__main__":
    main()
