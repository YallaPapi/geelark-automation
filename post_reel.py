"""
Post a video to Instagram Reels via Geelark cloud phone.

Usage:
    python post_reel.py <phone_name> <video_path> <caption>
"""
import sys
import os
import time
import subprocess
import re
import xml.etree.ElementTree as ET
from geelark_client import GeelarkClient

ADB_PATH = r"C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe"


class InstagramPoster:
    def __init__(self, phone_name):
        self.client = GeelarkClient()
        self.phone_name = phone_name
        self.phone_id = None
        self.device = None

    def adb(self, cmd, timeout=30):
        """Run ADB shell command"""
        result = subprocess.run(
            [ADB_PATH, "-s", self.device, "shell", cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()

    def tap(self, x, y):
        """Tap at coordinates"""
        self.adb(f"input tap {x} {y}")
        time.sleep(1)

    def dump_ui(self, label=""):
        """Dump UI hierarchy and return XML string. Always prints key elements."""
        self.adb("uiautomator dump /sdcard/ui.xml")
        xml_str = self.adb("cat /sdcard/ui.xml")

        # Always print what we see on screen
        if label:
            print(f"\n=== UI DUMP: {label} ===")
        else:
            print(f"\n=== UI DUMP ===")

        # Parse and show clickable elements
        if '<?xml' in xml_str:
            try:
                import xml.etree.ElementTree as ET
                xml_clean = xml_str[xml_str.find('<?xml'):]
                root = ET.fromstring(xml_clean)
                for elem in root.iter('node'):
                    text = elem.get('text', '')
                    desc = elem.get('content-desc', '')
                    res_id = elem.get('resource-id', '')
                    clickable = elem.get('clickable', '')
                    bounds = elem.get('bounds', '')

                    # Show elements that have text, content-desc, or are clickable
                    if text or desc or (clickable == 'true' and bounds):
                        info = []
                        if text:
                            info.append(f'text="{text}"')
                        if desc:
                            info.append(f'desc="{desc}"')
                        if res_id:
                            short_id = res_id.split('/')[-1] if '/' in res_id else res_id
                            info.append(f'id={short_id}')
                        if clickable == 'true':
                            info.append('CLICKABLE')
                        print(f"  [{bounds}] {' | '.join(info)}")
            except Exception as e:
                print(f"  (parse error: {e})")
        else:
            print("  (no XML content)")
        print("=== END UI DUMP ===\n")

        return xml_str

    def find_element(self, xml_str, text=None, content_desc=None, resource_id=None):
        """Find element by text, content-desc, or resource-id. Returns (center_x, center_y, bounds) or None"""
        if '<?xml' not in xml_str:
            return None
        xml_str = xml_str[xml_str.find('<?xml'):]

        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return None

        for elem in root.iter('node'):
            elem_text = elem.get('text', '').lower()
            elem_desc = elem.get('content-desc', '').lower()
            elem_res = elem.get('resource-id', '').lower()

            match = False
            if text and text.lower() in elem_text:
                match = True
            if content_desc and content_desc.lower() in elem_desc:
                match = True
            if resource_id and resource_id.lower() in elem_res:
                match = True

            if match:
                bounds = elem.get('bounds', '')
                if bounds:
                    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if m:
                        x1, y1, x2, y2 = map(int, m.groups())
                        return ((x1+x2)//2, (y1+y2)//2, bounds)
        return None

    def find_and_tap(self, text=None, content_desc=None, resource_id=None, retries=3, label=""):
        """Find element and tap it. Returns True if successful."""
        search_for = text or content_desc or resource_id
        for attempt in range(retries):
            ui = self.dump_ui(label=f"{label} (looking for: {search_for}, attempt {attempt+1}/{retries})")
            elem = self.find_element(ui, text=text, content_desc=content_desc, resource_id=resource_id)
            if elem:
                print(f"  >>> FOUND at {elem[2]}, tapping ({elem[0]}, {elem[1]})")
                self.tap(elem[0], elem[1])
                return True
            print(f"  >>> NOT FOUND: {search_for}")
            time.sleep(1)
        return False

    def dismiss_popups(self):
        """Check for and dismiss common popups"""
        ui = self.dump_ui(label="Checking for popups")

        # Common popup buttons to dismiss
        dismiss_buttons = [
            ("Not now", "text"),
            ("Not Now", "text"),
            ("OK", "text"),
            ("Allow", "text"),
            ("Skip", "text"),
            ("Cancel", "text"),
            ("Dismiss", "text"),
            ("Got it", "text"),
        ]

        for btn_text, _ in dismiss_buttons:
            elem = self.find_element(ui, text=btn_text)
            if elem:
                print(f"  Dismissing popup: {btn_text}")
                self.tap(elem[0], elem[1])
                time.sleep(1)
                return True
        return False

    def connect(self):
        """Find phone and connect via ADB"""
        print(f"Looking for phone: {self.phone_name}")

        # Search across multiple pages
        phone = None
        for page in range(1, 10):  # Check up to 10 pages
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

        # Start phone if not running (status 0 = running)
        if phone["status"] != 0:
            print("Starting phone...")
            self.client.start_phone(self.phone_id)
            print("Waiting for phone to boot (checking status)...")
            # Poll until phone is running (status 0)
            for i in range(60):  # up to 60 seconds
                time.sleep(2)
                status_result = self.client.get_phone_status([self.phone_id])
                items = status_result.get("items", [])
                if items and items[0].get("status") == 0:
                    print(f"  Phone is now running! (took ~{(i+1)*2}s)")
                    break
                print(f"  Still booting... ({(i+1)*2}s)")
            else:
                print("  Warning: Phone may not be fully booted, continuing anyway...")
            time.sleep(5)  # Extra buffer after boot

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
        if "success" in login_result.lower():
            print("ADB connected and logged in")
        else:
            print(f"Login result: {login_result}")

        return True

    def upload_video(self, video_path):
        """Upload video to phone"""
        print(f"Uploading video: {video_path}")

        # Upload to Geelark cloud
        resource_url = self.client.upload_file_to_geelark(video_path)
        print(f"  Uploaded to cloud: {resource_url}")

        # Push to phone
        upload_result = self.client.upload_file_to_phone(self.phone_id, resource_url)
        task_id = upload_result.get("taskId")
        self.client.wait_for_upload(task_id)
        print("  Video on phone!")

        # Trigger media scanner
        self.adb("am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Download/")
        time.sleep(3)

        return True

    def cleanup_screenshots(self):
        """Remove old screenshots that could interfere with gallery"""
        print("Cleaning up old screenshots...")
        self.adb("rm -f /sdcard/DCIM/Camera/IMG_*.png")
        self.adb("rm -f /sdcard/Pictures/Screenshots/*.png")
        time.sleep(1)

    def post(self, video_path, caption):
        """Main posting flow"""

        # 1. Upload video first
        self.upload_video(video_path)

        # 2. Clean up screenshots
        self.cleanup_screenshots()

        # 3. Force close and open Instagram
        print("Opening Instagram...")
        self.adb("am force-stop com.instagram.android")
        time.sleep(2)
        self.adb("monkey -p com.instagram.android 1")
        time.sleep(5)

        # Dismiss any initial popups
        self.dismiss_popups()
        time.sleep(1)

        # 4. Tap Create button
        print("\n>>> STEP 4: Tapping Create...")
        if not self.find_and_tap(content_desc="Create", label="STEP 4a"):
            # Try by resource ID
            if not self.find_and_tap(resource_id="creation_tab", label="STEP 4b"):
                # Try the + button
                if not self.find_and_tap(content_desc="New post", label="STEP 4c"):
                    raise Exception("Could not find Create button")
        time.sleep(2)
        self.dismiss_popups()

        # 5. Select first gallery item (most recent = our video)
        print("\n>>> STEP 5: Selecting video from gallery...")
        if not self.find_and_tap(resource_id="gallery_grid_item_thumbnail", label="STEP 5a"):
            # Try other gallery selectors
            if not self.find_and_tap(resource_id="media_thumbnail", label="STEP 5b"):
                # Try tapping center of expected gallery area
                print("  Trying default gallery position...")
                self.dump_ui(label="STEP 5c - before default tap")
                self.tap(360, 484)
        time.sleep(2)
        self.dismiss_popups()

        # 6. Tap Next
        print("\n>>> STEP 6: Tapping Next...")
        if not self.find_and_tap(text="Next", label="STEP 6a"):
            if not self.find_and_tap(content_desc="Next", label="STEP 6b"):
                raise Exception("Could not find Next button")
        time.sleep(3)
        self.dismiss_popups()

        # 7. Tap caption field and type
        print("\n>>> STEP 7: Typing caption...")
        if not self.find_and_tap(text="Write a caption", label="STEP 7a"):
            # Try by hint text
            self.find_and_tap(text="caption", label="STEP 7b")
        time.sleep(1)

        # Type caption (spaces become %s for ADB)
        escaped_caption = caption.replace(" ", "%s").replace("'", "\\'")
        self.adb(f"input text '{escaped_caption}'")
        print(f"  Typed: {caption}")
        time.sleep(1)

        # Hide keyboard
        self.adb("input keyevent KEYCODE_BACK")
        time.sleep(2)
        self.dump_ui(label="STEP 7c - after typing caption")

        # 8. Scroll down to see Share button
        print("\n>>> STEP 8: Scrolling to Share...")
        self.adb("input swipe 360 900 360 400 300")
        time.sleep(2)
        self.dump_ui(label="STEP 8 - after scroll")

        # 9. Tap Share
        print("\n>>> STEP 9: Tapping Share...")
        if not self.find_and_tap(content_desc="Share", label="STEP 9a"):
            if not self.find_and_tap(text="Share", label="STEP 9b"):
                raise Exception("Could not find Share button")

        print("Post submitted!")
        time.sleep(5)

        # Check if we're back on feed (success) or still on posting screen (error)
        ui = self.dump_ui()
        if self.find_element(ui, text="Sharing to Reels"):
            print("SUCCESS: Reel is being shared!")
            return True
        elif self.find_element(ui, content_desc="Home") or self.find_element(ui, resource_id="feed_tab"):
            print("SUCCESS: Back on feed, post completed!")
            return True
        elif self.find_element(ui, text="something went wrong"):
            print("ERROR: Instagram reported an error")
            return False
        else:
            print("Post may have completed - check Instagram to verify")
            return True

    def cleanup(self):
        """Cleanup after posting"""
        print("Cleaning up...")
        try:
            # Remove uploaded video
            self.adb("rm -f /sdcard/Download/*.mp4")
        except:
            pass

        try:
            self.client.disable_adb(self.phone_id)
        except:
            pass


def main():
    if len(sys.argv) < 4:
        print("Usage: python post_reel.py <phone_name> <video_path> <caption>")
        print('Example: python post_reel.py talktrackhub video.mp4 "Check this out!"')
        sys.exit(1)

    phone_name = sys.argv[1]
    video_path = sys.argv[2]
    caption = sys.argv[3]

    if not os.path.exists(video_path):
        print(f"Video not found: {video_path}")
        sys.exit(1)

    poster = InstagramPoster(phone_name)

    try:
        poster.connect()
        success = poster.post(video_path, caption)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        poster.cleanup()


if __name__ == "__main__":
    main()
