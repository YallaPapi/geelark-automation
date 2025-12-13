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
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import time
import subprocess
import re
import json
import random
import xml.etree.ElementTree as ET
import anthropic
from geelark_client import GeelarkClient

ADB_PATH = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"


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

    def adb(self, cmd, timeout=30):
        """Run ADB shell command"""
        result = subprocess.run(
            [ADB_PATH, "-s", self.device, "shell", cmd],
            capture_output=True, timeout=timeout,
            encoding='utf-8', errors='replace'
        )
        return result.stdout.strip() if result.stdout else ""

    def tap(self, x, y):
        """Tap at coordinates"""
        print(f"  [TAP] ({x}, {y})")
        self.adb(f"input tap {x} {y}")
        time.sleep(1.5)

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        """Swipe from one point to another"""
        self.adb(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

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
                    self.adb("input keyevent KEYCODE_BACK")
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
                    self.adb("input keyevent KEYCODE_BACK")
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
                    self.adb("input keyevent KEYCODE_BACK")
                    self.random_delay(1.0, 2.0)

        print("[HUMANIZE] Post-posting actions completed")

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
        """Type text via clipboard + paste - supports full Unicode, emojis, newlines"""
        import base64

        # ClipboardHelper APK method (works on Android 10-15)
        # Encode text to base64 for safe transmission of Unicode/emojis/newlines
        text_b64 = base64.b64encode(text.encode('utf-8')).decode('ascii')

        # Set clipboard via our custom ClipboardHelper activity
        result = self.adb(f"am start -a com.geelark.clipboard.COPY --es base64 {text_b64}")
        print(f"    ClipboardHelper: {result[:80] if result else 'started'}")
        time.sleep(0.5)  # Give activity time to set clipboard

        # Paste from clipboard (Ctrl+V / KEYCODE_PASTE)
        self.adb("input keyevent 279")  # KEYCODE_PASTE
        time.sleep(0.3)

        # Verify paste worked
        verify_elements, _ = self.dump_ui()
        text_found = any(text[:20] in elem.get('text', '') for elem in verify_elements)

        if not text_found:
            print("    KEYCODE_PASTE failed, trying long-press paste...")
            # Long press to get paste menu
            self.adb("input swipe 360 400 360 400 1000")
            time.sleep(0.5)

            # Look for Paste button
            paste_elements, _ = self.dump_ui()
            paste_btn = [e for e in paste_elements if 'paste' in e.get('text', '').lower() or 'paste' in e.get('desc', '').lower()]
            if paste_btn:
                self.tap(paste_btn[0]['center'][0], paste_btn[0]['center'][1])
            else:
                # Fallback to ADBKeyboard
                print("    Trying ADBKeyboard fallback...")
                self.adb(f"am broadcast -a ADB_INPUT_B64 --es msg {text_b64}")

        return True

    def dump_ui(self):
        """Dump UI hierarchy and return parsed elements"""
        self.adb("uiautomator dump /sdcard/ui.xml")
        xml_str = self.adb("cat /sdcard/ui.xml")

        elements = []
        if '<?xml' not in xml_str:
            return elements, xml_str

        xml_clean = xml_str[xml_str.find('<?xml'):]
        try:
            root = ET.fromstring(xml_clean)
            for elem in root.iter('node'):
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
- CRITICAL: If "Caption entered: True" is shown above, DO NOT tap the caption field again! The caption has been typed. Tap the Share button instead.
- If you see Share button and Caption entered is True, tap Share immediately
- Allow/OK buttons should be tapped for permissions
- If you see "OK" button in top right, tap it to confirm
- IMPORTANT: Return "done" ONLY when Share button clicked is True AND you see "Sharing to Reels" confirmation
- If Share button clicked is False but you see "Sharing to Reels", that's from a previous post - ignore it and start the posting flow
- Set share_clicked=true when you tap the Share button

Only output JSON."""

        response = self.anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        return json.loads(text)

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

        print(f"Connecting to {self.device}...")
        subprocess.run([ADB_PATH, "connect", self.device], capture_output=True)

        # Geelark requires glogin
        login_result = self.adb(f"glogin {password}")
        print(f"ADB: {login_result or 'connected'}")

        # Ensure ADBKeyboard is enabled
        self.setup_adbkeyboard()

        return True

    def setup_adbkeyboard(self):
        """Ensure ADBKeyboard is enabled and set as default input method"""
        print("Checking ADBKeyboard setup...")

        # Check current IME
        current_ime = self.adb("settings get secure default_input_method")
        if "adbkeyboard" in current_ime.lower():
            print("  ADBKeyboard already active")
            return True

        # Enable the package first
        self.adb("pm enable com.android.adbkeyboard")

        # Set ADBKeyboard as default via settings put (bypasses ime enable restrictions)
        print("  Setting ADBKeyboard as default...")
        self.adb("settings put secure enabled_input_methods com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME:com.android.adbkeyboard/.AdbIME")
        self.adb("settings put secure default_input_method com.android.adbkeyboard/.AdbIME")

        # Verify
        current_ime = self.adb("settings get secure default_input_method")
        if "adbkeyboard" in current_ime.lower():
            print("  ADBKeyboard enabled successfully!")
            return True
        else:
            print(f"  WARNING: ADBKeyboard setup may have failed. Current IME: {current_ime}")
            return False

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

        # Vision-action loop
        for step in range(max_steps):
            print(f"\n--- Step {step + 1} ---")

            # Dump UI
            elements, raw_xml = self.dump_ui()
            if not elements:
                print("  No UI elements found, waiting...")
                time.sleep(2)
                continue

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

            # Update state
            if action.get('video_selected'):
                self.video_uploaded = True
            if action.get('caption_entered'):
                self.caption_entered = True
            if action.get('share_clicked'):
                self.share_clicked = True

            # Execute action
            if action['action'] == 'done':
                print("\n[SUCCESS] Post completed!")
                if humanize:
                    self.humanize_after_post()
                return True

            elif action['action'] == 'home':
                print("  [HOME] Going to home screen...")
                self.adb("input keyevent KEYCODE_HOME")
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

                    # Step 5: Verify text was entered by checking UI
                    print("  Verifying caption was typed...")
                    verify_elements, _ = self.dump_ui()
                    caption_found = False
                    for elem in verify_elements:
                        if text[:20] in elem.get('text', ''):
                            caption_found = True
                            break

                    if caption_found:
                        print("  Caption verified!")
                        self.caption_entered = True
                    else:
                        print("  Caption not found in UI. Trying fallback input method...")
                        # Try the fallback method
                        escaped = text.replace(" ", "%s")
                        for char in ['(', ')', '@', '#', '&', ';', '<', '>', '|', '$', '`', '\\', '"', "'"]:
                            escaped = escaped.replace(char, '\\' + char)
                        self.adb(f'input text "{escaped}"')
                        time.sleep(1)
                        self.caption_entered = True

                    # Hide keyboard
                    self.adb("input keyevent KEYCODE_BACK")
                    time.sleep(0.5)
                else:
                    print("  ERROR: Could not get keyboard to appear. Will retry on next step.")

            elif action['action'] == 'back':
                self.adb("input keyevent KEYCODE_BACK")

            elif action['action'] == 'scroll_down':
                self.adb("input swipe 360 900 360 400 300")

            elif action['action'] == 'scroll_up':
                self.adb("input swipe 360 400 360 900 300")

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
            self.client.disable_adb(self.phone_id)
        except:
            pass


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
