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
import xml.etree.ElementTree as ET
import openai
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
        self.openai_client = self._analyzer.client  # For backwards compatibility
        self.phone_name = phone_name
        # UI controller (created lazily when Appium is connected)
        self._ui_controller = None
        # State tracking
        self.video_uploaded = False
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

            # Send to GPT Vision for analysis
            print("    Analyzing screenshot with GPT Vision...")

            response = self.openai_client.chat.completions.create(
                model="gpt-5-mini",
                max_completion_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_data}"
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

            analysis = response.choices[0].message.content
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
        """Handle 'open_instagram' action - restart Instagram app."""
        print("  [OPEN] Opening Instagram...")
        self.adb("am force-stop com.instagram.android")
        time.sleep(1)
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
        }

    def _track_action_for_loop_detection(self, action, elements, recent_actions, loop_threshold):
        """Track action signature for loop detection.

        Modifies recent_actions in place.
        """
        action_signature = action['action']
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
                # Capture full error details for debugging
                import traceback
                print(f"  [FULL ERROR]\n{traceback.format_exc()}")
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

    def restart_posting_flow(self) -> bool:
        """Restart the posting flow from scratch.

        Close and reopen Instagram, reset state flags.
        Used when max steps reached to give one more chance.

        Returns:
            True if restart successful, False otherwise
        """
        print("  [RESTART] Restarting posting flow from scratch...")
        try:
            # Close Instagram
            self.adb("am force-stop com.instagram.android")
            time.sleep(2)

            # Reopen Instagram
            self.adb("monkey -p com.instagram.android 1")
            time.sleep(4)

            # Reset state flags (video is still on phone, just need to repost)
            self.caption_entered = False
            self.share_clicked = False
            # Note: video_uploaded stays True since video is still on the phone

            print("  [RESTART] Instagram reopened, state reset")
            return True
        except Exception as e:
            print(f"  [RESTART] Failed to restart: {e}")
            return False

    def post(self, video_path, caption, max_steps=30, humanize=False):
        """Main posting flow with smart navigation

        Args:
            video_path: Path to video file
            caption: Caption text for the post
            max_steps: Maximum navigation steps (default 30)
            humanize: If True, perform random human-like actions before/after posting
        """
        # Track if we've already tried a restart
        flow_restarted = False

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
        step = 0
        while True:
            # Check if max steps reached
            if step >= max_steps:
                # Try flow restart before giving up
                if not flow_restarted:
                    print(f"\n[MAX STEPS] Reached {max_steps} steps - attempting flow restart...")
                    if self.restart_posting_flow():
                        flow_restarted = True
                        step = 0  # Reset step counter
                        recent_actions.clear()  # Clear action history
                        loop_recovery_count = 0  # Reset recovery count
                        print(f"  [RESTART] Flow restarted successfully, resuming from step 1")
                        continue  # Start over from step 0
                # If already restarted or restart failed, exit loop and fail
                break

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
                # Skip expensive vision analysis - just use the error message
                self.last_error_message = f"{error_type}: {error_msg}"
                return False

            # Show what we see (all elements)
            print(f"  Found {len(elements)} elements")
            for elem in elements:
                parts = []
                if elem['text']:
                    parts.append(f"'{elem['text']}'")
                if elem['desc']:
                    parts.append(f"desc='{elem['desc']}'")
                if parts:
                    print(f"    {elem['bounds']} {' | '.join(parts)}")

            # Ask Claude what to do
            print("  Analyzing...")
            try:
                action = self.analyze_ui(elements, caption)
            except Exception as e:
                print(f"  Analysis error: {e}")
                time.sleep(2)
                continue

            print(f"  Action: {action['action']} - {action.get('reason', '')}")

            # Update state (only video_selected and share_clicked from Claude's analysis)
            # caption_entered is ONLY set after we actually type the caption
            if action.get('video_selected'):
                self.video_uploaded = True
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
                return True

            # Execute action with inline error recovery
            try:
                # Special case: 'tap_and_type' - needs caption and has continue logic
                if action_name == 'tap_and_type':
                    if self._handle_tap_and_type(action, elements, caption):
                        continue  # Helper handled it and wants to skip to next step

                # Dispatch table for standard actions
                action_handlers = self._get_action_handlers()
                if action_name in action_handlers:
                    action_handlers[action_name](action, elements)

            except Exception as action_error:
                error_str = str(action_error).lower()
                print(f"  [ACTION ERROR] {type(action_error).__name__}: {action_error}")

                # Check if UiAutomator2 crashed
                if self.is_uiautomator2_crash(action_error):
                    print("  [RECOVERY] UiAutomator2 crashed during action - reconnecting...")
                    if self.reconnect_appium():
                        print("  [RECOVERY] Appium reconnected, retrying action next step")
                        continue  # Retry by going to next loop iteration
                    else:
                        print("  [RECOVERY FAILED] Could not reconnect Appium")
                        self.last_error_message = f"UiAutomator2 crash: {action_error}"
                        self.last_error_type = "infrastructure"
                        return False

                # Check if ADB issue
                elif "adb" in error_str or "device" in error_str or "connection" in error_str:
                    print("  [RECOVERY] ADB connection issue - attempting reconnect...")
                    if self._conn and self._conn.reconnect_adb():
                        print("  [RECOVERY] ADB reconnected, retrying action next step")
                        continue  # Retry by going to next loop iteration
                    else:
                        print("  [RECOVERY FAILED] Could not reconnect ADB")
                        self.last_error_message = f"ADB error: {action_error}"
                        self.last_error_type = "infrastructure"
                        return False

                # Unknown error - log and continue (don't fail entire post)
                else:
                    print(f"  [WARNING] Action failed but continuing: {action_error}")
                    # Continue to next step - Claude will see updated UI and decide next action

            # Track action and check for stuck loops
            self._track_action_for_loop_detection(action, elements, recent_actions, LOOP_THRESHOLD)
            should_abort, loop_recovery_count, should_clear = self._check_and_recover_from_loop(
                recent_actions, loop_recovery_count, LOOP_THRESHOLD, MAX_LOOP_RECOVERIES
            )
            if should_abort:
                # Skip expensive vision analysis
                self.last_error_message = "Loop recovery failed - could not escape stuck state"
                self.last_error_type = "loop_stuck"
                return False
            if should_clear:
                recent_actions.clear()

            time.sleep(1)
            step += 1

        print(f"\n[FAILED] Max steps ({max_steps}) reached")
        # Skip expensive vision analysis
        self.last_error_message = f"Max steps ({max_steps}) reached without completing post"
        self.last_error_type = "max_steps"
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
