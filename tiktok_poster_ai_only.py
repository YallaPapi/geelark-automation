"""
TikTok Video Poster - AI-Only Mode for Data Collection

This script posts videos to TikTok using 100% AI navigation (no hybrid rules).
Purpose: Capture UI dumps to understand TikTok's posting flow for building hybrid rules.

Usage:
    python tiktok_poster_ai_only.py <phone_name> <video_path> <caption>

Example:
    python tiktok_poster_ai_only.py themotivationmischief video.mp4 "Check this out!"

Output:
    tiktok_flow_analysis/<phone>_<timestamp>.jsonl  (flow logs for each session)
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
import subprocess
import xml.etree.ElementTree as ET
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

# Screen coordinates from centralized config
SCREEN_CENTER_X = Config.SCREEN_CENTER_X
SCREEN_CENTER_Y = Config.SCREEN_CENTER_Y

# TikTok package name
TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


class TikTokAIPoster:
    """TikTok poster using 100% AI navigation for data collection."""

    def __init__(self, phone_name, system_port=8200, appium_url=None):
        self._conn = DeviceConnectionManager(
            phone_name=phone_name,
            system_port=system_port,
            appium_url=appium_url or Config.DEFAULT_APPIUM_URL
        )
        self.client = self._conn.client
        self.phone_name = phone_name
        self._ui_controller = None

        # Claude client for AI analysis
        self.anthropic = anthropic.Anthropic()

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
        return self._conn.adb_command(cmd, timeout=timeout)

    def tap(self, x, y):
        if self.ui_controller:
            self.ui_controller.tap(x, y)
        else:
            raise Exception("Appium driver not connected - cannot tap")

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        if self.ui_controller:
            self.ui_controller.swipe(x1, y1, x2, y2, duration_ms)
        else:
            raise Exception("Appium driver not connected - cannot swipe")

    def press_key(self, keycode):
        if self.ui_controller:
            self.ui_controller.press_key(keycode)
        else:
            raise Exception("Appium driver not connected - cannot press key")

    def type_text(self, text):
        if self.ui_controller:
            return self.ui_controller.type_text(text)
        else:
            raise Exception("Appium driver not connected - cannot type")

    def connect(self):
        return self._conn.connect()

    def connect_appium(self, retries=3):
        return self._conn.connect_appium(retries=retries)

    def dump_ui(self):
        """Dump UI hierarchy and return parsed elements using Appium."""
        elements = []
        xml_str = ""

        if not self.appium_driver:
            raise Exception("Appium driver not connected - cannot dump UI")

        try:
            xml_str = self.appium_driver.page_source
        except Exception as e:
            print(f"  [UI DUMP ERROR] {type(e).__name__}: {str(e)[:200]}")
            raise Exception(f"UI dump failed: {e}")

        if '<?xml' not in xml_str:
            return elements, xml_str

        xml_clean = xml_str[xml_str.find('<?xml'):]
        try:
            root = ET.fromstring(xml_clean)
            for elem in root.iter():
                text = elem.get('text', '')
                desc = elem.get('content-desc', '')
                res_id = elem.get('resource-id', '')
                bounds = elem.get('bounds', '')
                clickable = elem.get('clickable', 'false')

                if bounds and (text or desc or clickable == 'true'):
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

    def analyze_ui_tiktok(self, elements, caption):
        """Use Claude to analyze TikTok UI and decide next action."""

        # Format elements for Claude
        elements_text = ""
        for i, elem in enumerate(elements):
            parts = [f"[{i}]"]
            parts.append(f"bounds={elem['bounds']}")
            if elem['text']:
                parts.append(f"text='{elem['text'][:50]}'")
            if elem['desc']:
                parts.append(f"desc='{elem['desc'][:50]}'")
            if elem['id']:
                parts.append(f"id='{elem['id']}'")
            if elem['clickable']:
                parts.append("CLICKABLE")
            elements_text += " ".join(parts) + "\n"

        # TikTok-specific prompt
        prompt = f"""You are automating TikTok video posting on an Android phone.

CURRENT STATE:
- Video uploaded to phone: {self.video_uploaded}
- Video selected in app: {self.video_selected}
- Caption entered: {self.caption_entered}
- Caption to post: "{caption[:100]}..."

UI ELEMENTS (format: [index] bounds text/desc id CLICKABLE):
{elements_text}

TIKTOK POSTING FLOW (typical sequence):
1. From home feed (For You/Following tabs), tap + button (center bottom) to create
2. In create menu, tap "Upload" or gallery icon to select video
3. In gallery, tap video thumbnail to select
4. On video preview/trim screen, tap "Next" to proceed
5. On sounds/effects screen, tap "Next" or skip to proceed
6. On caption screen, tap description field, type caption, tap "Post"
7. Wait for upload to complete

COMMON TIKTOK ELEMENTS:
- Bottom nav: Home, Discover/Search, + (create), Inbox, Profile
- Create menu: Camera, Upload, Templates, LIVE options
- Gallery: Video thumbnails with duration labels
- Editor: Sounds, Effects, Text, Stickers buttons
- Caption screen: "Describe your video", hashtag suggestions, Post button

RESPOND WITH JSON ONLY:
{{"action": "<action_type>", "element_index": <index>, "reason": "<brief reason>"}}

Valid action types:
- "tap" - tap element by index
- "tap_and_type" - tap element then type caption (for caption/description field)
- "back" - press back key
- "scroll_down" - scroll down to see more
- "wait" - wait for transition (e.g. upload progress)
- "done" - posting complete, success
- "error" - unrecoverable error (include "error_type" in response)

Analyze the screen and choose the NEXT action to continue posting."""

        try:
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()
            # Extract JSON from response
            if '{' in response_text:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                json_str = response_text[json_start:json_end]
                return json.loads(json_str)
            else:
                return {"action": "wait", "reason": "Could not parse response"}
        except Exception as e:
            print(f"  AI analysis error: {e}")
            return {"action": "wait", "reason": f"AI error: {e}"}

    def detect_error_state(self, elements):
        """Detect TikTok account/app error states."""
        all_text = ' '.join([
            (e.get('text', '') + ' ' + e.get('desc', '')).lower()
            for e in elements
        ])

        error_patterns = {
            'banned': [
                'your account was permanently banned',
                'account has been banned',
                'this account was banned',
                'account is banned',
            ],
            'suspended': [
                'account suspended',
                'temporarily suspended',
                'account has been suspended',
            ],
            'logged_out': [
                'log in to tiktok',
                'sign up for tiktok',
                'phone number or email',
                'log in or sign up',
            ],
            'captcha': [
                'verify you are human',
                'security verification',
                'slide to verify',
                'complete the puzzle',
            ],
            'restriction': [
                'you cannot post',
                'posting is restricted',
                'this action is blocked',
                'try again later',
            ],
        }

        for error_type, patterns in error_patterns.items():
            for pattern in patterns:
                if pattern in all_text:
                    return (error_type, pattern)

        return (None, None)

    def validate_video(self, video_path):
        """Check if video file is valid."""
        if not os.path.exists(video_path):
            return False, f"File not found: {video_path}"

        try:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                if 'moov atom not found' in error_msg:
                    return False, "Video corrupted: missing moov atom"
                return False, f"Video error: {error_msg[:100]}"

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
            print("  [WARN] ffprobe not found, skipping video validation")
            return True, "skipped"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def upload_video(self, video_path):
        """Upload video to phone."""
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

        self.video_uploaded = True
        return True

    def post(self, video_path, caption, max_steps=40):
        """Main posting flow with AI navigation for data collection.

        Uses 100% AI mode - every step uses Claude analysis.
        Logs all steps to tiktok_flow_analysis/ for later analysis.
        """
        # Initialize flow logger
        flow_logger = FlowLogger(self.phone_name, log_dir="tiktok_flow_analysis")

        print(f"\n[TIKTOK AI-ONLY] Starting TikTok posting flow")
        print(f"  Phone: {self.phone_name}")
        print(f"  Video: {video_path}")
        print(f"  Caption: {caption[:50]}...")

        # Validate video
        print(f"\nValidating video: {video_path}")
        is_valid, result = self.validate_video(video_path)
        if not is_valid:
            self.last_error_type = "corrupted_video"
            self.last_error_message = result
            print(f"  [ERROR] {result}")
            flow_logger.end_session(success=False, total_steps=0,
                                    error_type="corrupted_video", error_message=result)
            return False
        else:
            if result != "skipped":
                print(f"  Video valid: {result:.1f}s duration")

        # Upload video
        self.upload_video(video_path)

        # Open TikTok
        print("\nOpening TikTok...")
        self.adb(f"am force-stop {TIKTOK_PACKAGE}")
        time.sleep(2)
        self.adb(f"monkey -p {TIKTOK_PACKAGE} 1")
        time.sleep(5)

        # Vision-action loop
        for step in range(max_steps):
            print(f"\n--- Step {step + 1} ---")

            # Dump UI
            try:
                elements, raw_xml = self.dump_ui()
            except Exception as e:
                print(f"  UI dump failed: {e}")
                time.sleep(2)
                continue

            if not elements:
                print("  No UI elements found, waiting...")
                time.sleep(2)
                continue

            # Check for errors
            error_type, error_msg = self.detect_error_state(elements)
            if error_type:
                print(f"  [ERROR DETECTED] {error_type}: {error_msg}")
                self.last_error_type = error_type
                self.last_error_message = error_msg
                flow_logger.log_error(error_type, error_msg, elements)
                flow_logger.log_failure(f"{error_type}: {error_msg}")
                flow_logger.close()
                return False

            # Show what we see
            print(f"  Found {len(elements)} elements")
            for elem in elements[:20]:  # Show first 20 elements
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

            # Get AI decision
            print("  Analyzing with Claude...")
            action = self.analyze_ui_tiktok(elements, caption)
            print(f"  Action: {action['action']} - {action.get('reason', '')}")

            # Log step
            flow_logger.log_step(
                elements=elements,
                action=action,
                ai_called=True,
                ai_tokens=0,
                state={
                    'video_uploaded': self.video_uploaded,
                    'video_selected': self.video_selected,
                    'caption_entered': self.caption_entered,
                },
                result="pending"
            )

            # Execute action
            action_name = action['action']

            if action_name == 'done':
                print("\n[SUCCESS] TikTok post completed!")
                flow_logger.log_success()
                flow_logger.close()
                return True

            if action_name == 'error':
                self.last_error_type = action.get('error_type', 'ai_error')
                self.last_error_message = action.get('reason', 'Unknown error')
                print(f"\n[ERROR] {self.last_error_message}")
                flow_logger.log_failure(f"ai_error: {self.last_error_message}")
                flow_logger.close()
                return False

            if action_name == 'tap':
                idx = action.get('element_index', 0)
                if 0 <= idx < len(elements):
                    elem = elements[idx]
                    print(f"  Tapping element {idx} at ({elem['center'][0]}, {elem['center'][1]})")
                    self.tap(elem['center'][0], elem['center'][1])

            elif action_name == 'tap_and_type':
                idx = action.get('element_index', 0)
                if 0 <= idx < len(elements):
                    elem = elements[idx]
                    print(f"  Tapping element {idx} and typing caption...")
                    self.tap(elem['center'][0], elem['center'][1])
                    time.sleep(1)
                    self.type_text(caption)
                    self.caption_entered = True
                    time.sleep(0.5)
                    self.press_key('KEYCODE_BACK')  # Hide keyboard

            elif action_name == 'back':
                print("  Pressing BACK")
                self.press_key('KEYCODE_BACK')

            elif action_name == 'scroll_down':
                print("  Scrolling down")
                self.swipe(SCREEN_CENTER_X, 1000, SCREEN_CENTER_X, 400, 300)

            elif action_name == 'wait':
                print("  Waiting...")
                time.sleep(2)

            # Update state based on screen progression
            # Detect post-gallery indicators
            element_ids = [e.get('id', '') for e in elements]
            all_text = ' '.join([e.get('text', '').lower() for e in elements])

            if not self.video_selected:
                # TikTok indicators for post-gallery screens
                if 'next' in all_text and ('sounds' in all_text or 'effects' in all_text):
                    self.video_selected = True
                    print("  [STATE] video_selected = True (detected sounds/effects screen)")
                elif 'describe your video' in all_text or 'post' in all_text:
                    self.video_selected = True
                    print("  [STATE] video_selected = True (detected caption screen)")

            time.sleep(1)

        # Max steps reached
        print(f"\n[FAILED] Max steps ({max_steps}) reached")
        self.last_error_type = "max_steps"
        self.last_error_message = f"Max steps ({max_steps}) reached without completing post"
        flow_logger.log_failure(f"max_steps: {self.last_error_message}")
        flow_logger.close()
        return False

    def cleanup(self):
        """Cleanup after posting."""
        print("\nCleaning up...")
        try:
            self.adb("rm -f /sdcard/Download/*.mp4")
        except Exception:
            pass
        self._conn.disconnect()


def main():
    if len(sys.argv) < 4:
        print("Usage: python tiktok_poster_ai_only.py <phone_name> <video_path> <caption>")
        print('Example: python tiktok_poster_ai_only.py themotivationmischief video.mp4 "Check this out!"')
        print("\nTikTok test accounts:")
        print("  themotivationmischief")
        print("  talkingsquidbaby")
        print("  calknowsbestsometimes")
        print("  inspirebanana")
        print("  glowingscarlets")
        print("  crookedwafflezing")
        sys.exit(1)

    phone_name = sys.argv[1]
    video_path = sys.argv[2]
    caption = sys.argv[3]

    if not os.path.exists(video_path):
        print(f"Video not found: {video_path}")
        sys.exit(1)

    poster = TikTokAIPoster(phone_name)

    try:
        poster.connect()
        poster.connect_appium()
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
