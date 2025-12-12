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

# Set ANDROID_HOME for Appium
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'

import time
import subprocess
import re
import json
import random
import xml.etree.ElementTree as ET
import anthropic
from geelark_client import GeelarkClient

# Appium imports
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy

ADB_PATH = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
APPIUM_SERVER = "http://127.0.0.1:4723"


class SmartInstagramPoster:
    def __init__(self, phone_name):
        self.client = GeelarkClient()
        self.anthropic = anthropic.Anthropic()
        self.phone_name = phone_name
        self.phone_id = None
        self.device = None
        self.video_uploaded = False
        self.caption_entered = False
        self.share_clicked = False
        self.appium_driver = None  # Appium WebDriver for typing
        # Error tracking
        self.last_error_type = None
        self.last_error_message = None
        self.last_screenshot_path = None

    def adb(self, cmd, timeout=30):
        """Run ADB shell command"""
        result = subprocess.run(
            [ADB_PATH, "-s", self.device, "shell", cmd],
            capture_output=True, timeout=timeout,
            encoding='utf-8', errors='replace'
        )
        return result.stdout.strip() if result.stdout else ""

    def is_uiautomator2_crash(self, exception):
        """Check if exception indicates UiAutomator2 crashed on device"""
        error_msg = str(exception).lower()
        return any(indicator in error_msg for indicator in [
            'instrumentation process is not running',
            'uiautomator2 server',
            'cannot be proxied',
            'probably crashed',
        ])

    def reconnect_appium(self):
        """Reconnect Appium driver after UiAutomator2 crash"""
        print("  [RECOVERY] Reconnecting Appium driver...")
        try:
            if self.appium_driver:
                self.appium_driver.quit()
        except:
            pass
        self.appium_driver = None
        time.sleep(2)
        return self.connect_appium()

    def tap(self, x, y):
        """Tap at coordinates using Appium (required)"""
        print(f"  [TAP] ({x}, {y})")
        if not self.appium_driver:
            raise Exception("Appium driver not connected - cannot tap")
        self.appium_driver.tap([(x, y)])
        time.sleep(1.5)

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        """Swipe from one point to another using Appium (required)"""
        if not self.appium_driver:
            raise Exception("Appium driver not connected - cannot swipe")
        self.appium_driver.swipe(x1, y1, x2, y2, duration_ms)

    def press_key(self, keycode):
        """Press a key using Appium (required). Keycode can be int or string like 'KEYCODE_BACK'"""
        if not self.appium_driver:
            raise Exception("Appium driver not connected - cannot press key")
        # Convert string keycode to int if needed
        key_map = {
            'KEYCODE_BACK': 4,
            'KEYCODE_HOME': 3,
            'KEYCODE_ENTER': 66,
        }
        if isinstance(keycode, str):
            keycode = key_map.get(keycode, 4)  # Default to BACK
        self.appium_driver.press_keycode(keycode)

    def random_delay(self, min_sec=0.5, max_sec=2.0):
        """Random delay between actions to appear more human"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def humanize_before_post(self):
        """Perform random human-like actions before posting"""
        print("\n[HUMANIZE] Performing random actions before posting...")
        actions_done = 0
        max_actions = random.randint(2, 4)

        for _ in range(max_actions):
            action = random.choice(['scroll_feed', 'view_story', 'scroll_reels', 'check_notifications'])

            if action == 'scroll_feed':
                print("  - Scrolling feed...")
                scroll_count = random.randint(1, 3)
                for _ in range(scroll_count):
                    self.swipe(360, 900, 360, 400, random.randint(200, 400))
                    self.random_delay(1.0, 3.0)
                # Scroll back up sometimes
                if random.random() < 0.3:
                    self.swipe(360, 400, 360, 900, 300)
                    self.random_delay(0.5, 1.5)
                actions_done += 1

            elif action == 'view_story':
                print("  - Viewing a story...")
                elements, _ = self.dump_ui()
                story_elements = [e for e in elements if 'story' in e.get('desc', '').lower() and 'unseen' in e.get('desc', '').lower()]
                if story_elements:
                    story = random.choice(story_elements)
                    self.tap(story['center'][0], story['center'][1])
                    view_time = random.uniform(3, 8)
                    print(f"    Watching for {view_time:.1f}s...")
                    time.sleep(view_time)
                    # Tap through a few more stories sometimes
                    if random.random() < 0.5:
                        for _ in range(random.randint(1, 3)):
                            self.tap(650, 640)  # Tap right side to skip to next story
                            time.sleep(random.uniform(2, 5))
                    # Go back
                    self.press_key('KEYCODE_BACK')
                    self.random_delay(1.0, 2.0)
                    actions_done += 1

            elif action == 'scroll_reels':
                print("  - Browsing reels...")
                elements, _ = self.dump_ui()
                reels_tab = [e for e in elements if 'reels' in e.get('desc', '').lower() and e['clickable']]
                if reels_tab:
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
                            self.tap(360, 640)
                            time.sleep(0.1)
                            self.tap(360, 640)
                            self.random_delay(0.5, 1.0)
                        # Swipe to next reel
                        self.swipe(360, 1000, 360, 300, 200)
                        self.random_delay(0.5, 1.5)
                    # Go back to home
                    elements, _ = self.dump_ui()
                    home_tab = [e for e in elements if 'home' in e.get('desc', '').lower() and e['clickable']]
                    if home_tab:
                        self.tap(home_tab[0]['center'][0], home_tab[0]['center'][1])
                    self.random_delay(1.0, 2.0)
                    actions_done += 1

            elif action == 'check_notifications':
                print("  - Checking notifications...")
                elements, _ = self.dump_ui()
                notif_btn = [e for e in elements if ('notification' in e.get('desc', '').lower() or 'activity' in e.get('desc', '').lower()) and e['clickable']]
                if notif_btn:
                    self.tap(notif_btn[0]['center'][0], notif_btn[0]['center'][1])
                    self.random_delay(2.0, 4.0)
                    # Scroll through notifications
                    if random.random() < 0.5:
                        self.swipe(360, 800, 360, 400, 300)
                        self.random_delay(1.0, 2.0)
                    # Go back
                    self.press_key('KEYCODE_BACK')
                    self.random_delay(1.0, 2.0)
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
                    self.swipe(360, 900, 360, 400, random.randint(200, 400))
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

        # Error patterns to detect
        error_patterns = {
            'suspended': [
                'account has been suspended',
                'account has been disabled',
                'your account was disabled',
                'we suspended your account',
                'account is disabled',
            ],
            'captcha': [
                'confirm it\'s you',
                'we detected unusual activity',
                'verify your identity',
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
                'sign up',
                'don\'t have an account',
            ],
            'app_update': [
                'update instagram',
                'update required',
                'new version available',
            ],
            'rate_limited': [
                'please wait a few minutes',
                'too many requests',
                'slow down',
            ],
        }

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
        """Type text using Appium. Supports Unicode/emojis/newlines on all Android versions."""
        if not self.appium_driver:
            print("    ERROR: Appium driver not connected!")
            return False

        print(f"    Typing via Appium ({len(text)} chars)...")
        try:
            # Find the currently focused EditText element
            edit_texts = self.appium_driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
            if edit_texts:
                # Use the first visible/focused EditText
                for et in edit_texts:
                    if et.is_displayed():
                        et.send_keys(text)
                        print("    Appium: text sent successfully")
                        time.sleep(0.8)
                        return True

            # Fallback: try to type using the active element
            active = self.appium_driver.switch_to.active_element
            if active:
                active.send_keys(text)
                print("    Appium: text sent to active element")
                time.sleep(0.8)
                return True

            print("    ERROR: No text field found to type into")
            return False

        except Exception as e:
            print(f"    Appium typing error: {e}")
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
        """Use Claude to analyze UI and decide next action"""

        # Format elements for Claude
        ui_description = "Current UI elements:\n"
        for i, elem in enumerate(elements):
            parts = []
            if elem['text']:
                parts.append(f"text=\"{elem['text']}\"")
            if elem['desc']:
                parts.append(f"desc=\"{elem['desc']}\"")
            if elem['id']:
                parts.append(f"id={elem['id']}")
            if elem['clickable']:
                parts.append("CLICKABLE")
            ui_description += f"{i}. {elem['bounds']} center={elem['center']} | {' | '.join(parts)}\n"

        prompt = f"""You are controlling an Android phone to post a Reel to Instagram.

Current state:
- Video uploaded to phone: {self.video_uploaded}
- Caption entered: {self.caption_entered}
- Share button clicked: {self.share_clicked}
- Caption to post: "{caption}"

{ui_description}

Based on the UI elements, decide the next action to take.

Instagram posting flow:
1. Find and tap Create/+ button. IMPORTANT: On different Instagram versions:
   - Some have "Create" in bottom nav bar
   - Some have "Create New" in top left corner (only visible from Profile tab)
   - If you don't see Create, tap "Profile" tab first to find "Create New"
2. Select "Reel" option if a menu appears
3. Select the video from gallery (look for video thumbnails, usually most recent)
4. Tap "Next" to proceed to editing
5. Tap "Next" again to proceed to sharing
6. When you see the caption field ("Write a caption" or similar), return "type" action with the caption text
7. Tap "Share" to publish
8. Done when you see confirmation, "Sharing to Reels", or back on feed

Respond with JSON:
{{
    "action": "tap" | "tap_and_type" | "back" | "scroll_down" | "scroll_up" | "home" | "open_instagram" | "done",
    "element_index": <index of element to tap>,
    "text": "<text to type if action is tap_and_type>",
    "reason": "<brief explanation>",
    "video_selected": true/false,
    "caption_entered": true/false,
    "share_clicked": true/false
}}

CRITICAL RULES - NEVER GIVE UP:
- NEVER return "error". There is no error action. Always try to recover.
- If you see Play Store, Settings, or any non-Instagram app: return "home" to go back to home screen
- If you see home screen or launcher: return "open_instagram" to reopen Instagram
- If you see a popup, dialog, or unexpected screen: return "back" to dismiss it
- If you're lost or confused: return "back" and try again
- If you don't see Create button, tap Profile tab first
- Look for "Create New" in desc field (top left area, small button)
- Look for "Profile" in desc field (bottom nav, usually id=profile_tab)
- If you see "Reel" or "Create new reel" option, tap it
- If you see gallery thumbnails with video, tap the video
- If you see "Next" button anywhere, tap it
- IMPORTANT: When you see a caption field (text containing "Write a caption", "Add a caption", or similar placeholder) AND "Caption entered" is False, return action="tap_and_type" with the element_index of the caption field and text set to the caption
- CRITICAL: If "Caption entered: True" is shown above, DO NOT return tap_and_type! The caption is already typed. Just tap the Share button directly.
- Allow/OK buttons should be tapped for permissions
- IMPORTANT: Return "done" ONLY when Share button clicked is True AND you see "Sharing to Reels" confirmation
- If Share button clicked is False but you see "Sharing to Reels", that's from a previous post - ignore it and start the posting flow
- Set share_clicked=true when you tap the Share button
- CRITICAL OK BUTTON RULE: After caption has been entered (Caption entered: True), if you see an "OK" button visible on screen (text='OK' or desc='OK'), you MUST tap the OK button FIRST before tapping Next or Share. This OK button dismisses the keyboard or a dialog and must be tapped for Next/Share to work properly.

Only output JSON."""

        # Retry Claude API calls for transient errors
        for attempt in range(3):
            try:
                response = self.anthropic.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=500,
                    messages=[{"role": "user", "content": prompt}]
                )

                # Check for empty response
                if not response.content:
                    if attempt < 2:
                        time.sleep(1)
                        continue
                    raise ValueError("Claude returned empty response")

                text = response.content[0].text.strip()

                # Check for empty text
                if not text:
                    if attempt < 2:
                        time.sleep(1)
                        continue
                    raise ValueError("Claude returned empty text")

                # Handle markdown code blocks
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()

                try:
                    return json.loads(text)
                except json.JSONDecodeError as e:
                    # Log full raw response for debugging JSON issues
                    print(f"  [JSON PARSE ERROR] attempt {attempt+1}: {e}")
                    print(f"  Raw response (full): {text}")
                    if attempt < 2:
                        time.sleep(1)
                        continue
                    raise ValueError(f"JSON parse failed after 3 attempts: {e}. Response: {text[:100]}")

            except Exception as e:
                if attempt < 2 and "rate" not in str(e).lower():
                    time.sleep(1)
                    continue
                raise

        raise ValueError("Failed to get valid response from Claude after 3 attempts")

    def connect(self):
        """Find phone and connect via ADB"""
        print(f"Looking for phone: {self.phone_name}")

        # Search across multiple pages
        phone = None
        for page in range(1, 10):
            result = self.client.list_phones(page=page, page_size=100)
            for p in result["items"]:
                if p["serialName"] == self.phone_name or p["id"] == self.phone_name:
                    phone = p
                    break
            if phone or len(result["items"]) < 100:
                break

        if not phone:
            raise Exception(f"Phone not found: {self.phone_name}")

        self.phone_id = phone["id"]
        print(f"Found: {phone['serialName']} (ID: {self.phone_id}, Status: {phone['status']})")

        # Start phone if not running
        if phone["status"] != 0:
            print("Starting phone...")
            self.client.start_phone(self.phone_id)
            print("Waiting for phone to boot...")
            for i in range(60):
                time.sleep(2)
                status_result = self.client.get_phone_status([self.phone_id])
                items = status_result.get("successDetails", [])
                if items and items[0].get("status") == 0:
                    print(f"  Phone ready! (took ~{(i+1)*2}s)")
                    break
                print(f"  Booting... ({(i+1)*2}s)")
            time.sleep(5)

        # Enable ADB
        print("Enabling ADB...")
        self.client.enable_adb(self.phone_id)
        time.sleep(5)

        # Get ADB info
        adb_info = self.client.get_adb_info(self.phone_id)
        self.device = f"{adb_info['ip']}:{adb_info['port']}"
        password = adb_info['pwd']

        # Clean any stale connection to this device first
        subprocess.run([ADB_PATH, "disconnect", self.device], capture_output=True)
        time.sleep(1)

        print(f"Connecting to {self.device}...")
        connect_result = subprocess.run([ADB_PATH, "connect", self.device], capture_output=True, encoding='utf-8')
        print(f"  ADB connect: {connect_result.stdout.strip()}")

        # Wait for device to appear in ADB devices list BEFORE running glogin
        print("Waiting for ADB connection to stabilize...")
        device_ready = False
        for attempt in range(10):  # Increased attempts
            time.sleep(2)
            result = subprocess.run([ADB_PATH, "devices"], capture_output=True, encoding='utf-8')
            if self.device in result.stdout:
                # Check if device status is "device" (not "offline" or "unauthorized")
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if self.device in line and '\tdevice' in line:
                        device_ready = True
                        print(f"  Device {self.device} is ready")
                        break
                if device_ready:
                    break
            print(f"  Waiting... (attempt {attempt + 1}/10)")

        if not device_ready:
            print(f"  Warning: Device not in ADB device list after 20s")

        # NOW run glogin after device is ready - with retry
        print("Authenticating with glogin...")
        glogin_success = False
        for glogin_attempt in range(3):
            login_result = self.adb(f"glogin {password}")
            # Check both stdout and for error indicators
            if login_result and "error" not in login_result.lower():
                print(f"  glogin: {login_result}")
                glogin_success = True
                break
            elif "success" in login_result.lower():
                print(f"  glogin: {login_result}")
                glogin_success = True
                break
            else:
                print(f"  glogin attempt {glogin_attempt + 1}/3 returned: [{login_result}]")
                time.sleep(2)

        if not glogin_success:
            print(f"  Warning: glogin may not have succeeded")

        # Connect Appium for UI interaction
        self.connect_appium()

        return True

    def connect_appium(self, retries=3):
        """Connect Appium driver - REQUIRED for automation to work"""
        print("Connecting Appium driver...")

        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.automation_name = "UiAutomator2"
        options.device_name = self.device
        options.udid = self.device
        options.no_reset = True
        options.new_command_timeout = 120  # Allow time for slow cloud phone operations
        options.set_capability("appium:adbExecTimeout", 120000)  # 120s for slow cloud connections
        options.set_capability("appium:uiautomator2ServerInstallTimeout", 120000)  # 120s for install
        options.set_capability("appium:uiautomator2ServerLaunchTimeout", 10000)  # 10s for launch - binary: works in ~1s or not at all
        options.set_capability("appium:androidDeviceReadyTimeout", 60)  # 60s to wait for device ready

        last_error = None
        for attempt in range(retries):
            try:
                # Direct connection - removed ThreadPoolExecutor which left orphaned sessions
                # Appium's own timeouts (adbExecTimeout, uiautomator2ServerLaunchTimeout) handle slow connections
                self.appium_driver = webdriver.Remote(
                    command_executor=APPIUM_SERVER,
                    options=options
                )

                platform_ver = self.appium_driver.capabilities.get('platformVersion', 'unknown')
                print(f"  Appium connected! (Android {platform_ver})")
                return True
            except Exception as e:
                last_error = e
                print(f"  Appium connection failed (attempt {attempt + 1}/{retries}): {e}")
                self.appium_driver = None
                if attempt < retries - 1:
                    print(f"  Retrying in 2 seconds...")
                    time.sleep(2)  # Binary: works in ~1s or not at all, no point waiting

        # All retries failed - raise exception
        raise Exception(f"Appium connection failed after {retries} attempts: {last_error}")

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

    def post(self, video_path, caption, max_steps=30, humanize=False):
        """Main posting flow with smart navigation

        Args:
            video_path: Path to video file
            caption: Caption text for the post
            max_steps: Maximum navigation steps
            humanize: If True, perform random human-like actions before/after posting
        """

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
                self.last_error_message = error_msg
                self.last_screenshot_path = self.take_error_screenshot(self.phone_name, error_type)
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

            # Execute action
            if action['action'] == 'done':
                print("\n[SUCCESS] Share initiated!")
                # Wait for upload to actually complete (poll UI for confirmation)
                if self.wait_for_upload_complete(timeout=60):
                    print("[SUCCESS] Upload confirmed complete!")
                else:
                    print("[WARNING] Upload confirmation timeout - may still be processing")
                if humanize:
                    self.humanize_after_post()
                return True

            elif action['action'] == 'home':
                print("  [HOME] Going to home screen...")
                self.press_key('KEYCODE_HOME')
                time.sleep(2)

            elif action['action'] == 'open_instagram':
                print("  [OPEN] Opening Instagram...")
                self.adb("am force-stop com.instagram.android")
                time.sleep(1)
                self.adb("monkey -p com.instagram.android 1")
                time.sleep(4)

            elif action['action'] == 'tap':
                idx = action.get('element_index', 0)
                if 0 <= idx < len(elements):
                    elem = elements[idx]
                    self.tap(elem['center'][0], elem['center'][1])
                else:
                    print(f"  Invalid element index: {idx}")

            elif action['action'] == 'tap_and_type':
                # Prevent re-typing if caption already entered - just tap Share instead
                if self.caption_entered:
                    print("  [SKIP] Caption already entered! Tapping Share instead.")
                    share_elements = [e for e in elements if e.get('text', '').lower() == 'share' or e.get('desc', '').lower() == 'share']
                    if share_elements:
                        self.tap(share_elements[0]['center'][0], share_elements[0]['center'][1])
                        self.share_clicked = True
                    continue

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

            elif action['action'] == 'back':
                self.press_key('KEYCODE_BACK')

            elif action['action'] == 'scroll_down':
                self.adb("input swipe 360 900 360 400 300")

            elif action['action'] == 'scroll_up':
                self.adb("input swipe 360 400 360 900 300")

            # Track action for loop detection
            action_signature = action['action']
            if action['action'] == 'tap' and 'element_index' in action:
                idx = action.get('element_index', 0)
                if 0 <= idx < len(elements):
                    x, y = elements[idx]['center']
                    action_signature = f"tap_{x}_{y}"
            recent_actions.append(action_signature)
            if len(recent_actions) > LOOP_THRESHOLD:
                recent_actions.pop(0)

            # Check for loop - if last N actions are all identical, we're stuck
            if len(recent_actions) >= LOOP_THRESHOLD and len(set(recent_actions)) == 1:
                loop_recovery_count += 1
                print(f"\n  [LOOP DETECTED] Same action '{recent_actions[0]}' repeated {LOOP_THRESHOLD} times!")
                print(f"  [RECOVERY] Attempt {loop_recovery_count}/{MAX_LOOP_RECOVERIES}")

                if loop_recovery_count > MAX_LOOP_RECOVERIES:
                    print("  [ABORT] Too many loop recoveries, giving up")
                    return False

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

                # Reset action tracking
                recent_actions = []
                print("  [RECOVERY] Restarted - continuing from step", step + 1)

            time.sleep(1)

        print(f"\n[FAILED] Max steps ({max_steps}) reached")
        return False

    def cleanup(self):
        """Cleanup after posting"""
        print("\nCleaning up...")
        try:
            self.adb("rm -f /sdcard/Download/*.mp4")
        except:
            pass
        try:
            if self.appium_driver:
                self.appium_driver.quit()
                print("  Appium driver closed")
        except:
            pass
        try:
            self.client.disable_adb(self.phone_id)
        except:
            pass
        # Stop the cloud phone to save Geelark billing minutes
        try:
            self.client.stop_phone(self.phone_id)
            print("  Phone stopped (saving billing minutes)")
        except Exception as e:
            print(f"  Warning: Could not stop phone: {e}")


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
