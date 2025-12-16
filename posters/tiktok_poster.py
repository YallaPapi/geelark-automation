"""TikTok poster implementation - implements BasePoster interface for TikTok video posting."""
import time
import json
import re
from typing import Optional, Dict, List

import anthropic

from .base_poster import BasePoster, PostResult


class TikTokPoster(BasePoster):
    """TikTok poster implementation using Claude-driven UI navigation.

    This poster automates TikTok video posting using the same architectural
    pattern as InstagramPoster:
    - Device connection via DeviceConnectionManager
    - Claude AI-driven UI navigation
    - TikTok-specific error detection and classification

    The TikTok posting flow:
    1. Launch TikTok app
    2. Navigate to Create (+) button
    3. Select "Upload" to access gallery
    4. Select video from gallery
    5. Add caption/description
    6. Tap "Post" button
    7. Wait for upload confirmation
    """

    # TikTok package name
    APP_PACKAGE = "com.zhiliaoapp.musically"  # International TikTok
    # Alternative: "com.ss.android.ugc.trill" for some regions

    # TikTok-specific error patterns
    ERROR_PATTERNS = {
        'account_banned': [
            'account has been permanently banned',
            'your account was banned',
            'account is permanently suspended',
        ],
        'account_suspended': [
            'account has been suspended',
            'temporarily suspended',
            'account is suspended',
        ],
        'community_violation': [
            'violates our community guidelines',
            'community guidelines violation',
            'content removed',
        ],
        'rate_limited': [
            'too many posts',
            'posting too frequently',
            'try again later',
            'limit reached',
        ],
        'network_error': [
            'no network connection',
            'connection failed',
            'network unavailable',
            'check your internet',
        ],
        'processing_failed': [
            'video processing failed',
            'upload failed',
            'could not process',
            'format not supported',
        ],
        'logged_out': [
            'log in to tiktok',
            'sign up',
            'create account',
            'login required',
        ],
        'age_restricted': [
            'age verification',
            'verify your age',
            'must be 18',
        ],
    }

    # Error types that indicate account-level issues (non-retryable)
    ACCOUNT_ERROR_TYPES = {
        'account_banned',
        'account_suspended',
        'community_violation',
        'logged_out',
        'age_restricted',
    }

    # Claude system prompt for TikTok UI navigation
    TIKTOK_NAVIGATION_PROMPT = """You are controlling an Android phone to post a video to TikTok.

Current state:
- Video uploaded to phone: {video_uploaded}
- Caption entered: {caption_entered}
- Post button clicked: {post_clicked}
- Caption to post: "{caption}"

{ui_description}

Based on the UI elements, decide the next action to take.

TikTok posting flow:
1. Find and tap the Create (+) button in the bottom center navigation bar
2. Tap "Upload" to access gallery (NOT the red record button)
3. Select video from gallery - tap the video thumbnail
4. Tap "Next" to proceed to editing
5. Skip editing (tap "Next" again or skip any effects/sounds)
6. Find the caption/description field and enter the caption
7. Tap "Post" button (usually red, bottom right)
8. Wait for "Posted" or "Uploading" confirmation

TIKTOK UI PATTERNS:
- Bottom nav: Home | Friends | + (Create) | Inbox | Profile
- Create button is the large + in center of bottom nav
- Upload option appears after tapping + (may say "Upload" or show gallery icon)
- Video gallery shows thumbnails with duration overlay
- Post button is usually red with "Post" text
- Caption field may say "Describe your video" or "Add a description"

ERROR DETECTION - Return immediately if you see:
1. "Account banned/suspended" messages
2. "Community guidelines violation" warnings
3. "Login required" or login screen
4. "Network error" messages
5. "Too many posts" rate limit warnings

POPUP HANDLING:
- "Add music" popup: Tap "Skip" or outside the popup
- "Effects" suggestions: Tap "Skip" or "Next"
- "Who can view" settings: Keep as is, tap away
- Permission requests: Tap "Allow"

Respond with JSON:
{{
    "action": "tap" | "tap_and_type" | "back" | "scroll_down" | "scroll_up" | "home" | "open_tiktok" | "done",
    "element_index": <index of element to tap>,
    "text": "<text to type if action is tap_and_type>",
    "reason": "<brief explanation>",
    "video_selected": true/false,
    "caption_entered": true/false,
    "post_clicked": true/false
}}

CRITICAL RULES:
- NEVER return "error". Always try to recover.
- If stuck, press "back" and try again
- If on wrong screen, use "home" then "open_tiktok"
- Return "done" only when post is confirmed uploading/posted

Only output JSON."""

    def __init__(
        self,
        phone_name: str,
        system_port: int = 8200,
        appium_url: str = None
    ):
        """Initialize TikTok poster.

        Args:
            phone_name: Geelark phone name to post from.
            system_port: UiAutomator2 systemPort for Appium.
            appium_url: Appium server URL (e.g., 'http://127.0.0.1:4723').
        """
        self._phone_name = phone_name
        self._system_port = system_port
        self._appium_url = appium_url
        self._conn = None  # DeviceConnectionManager - lazy init
        self._ui_controller = None  # AppiumUIController - lazy init
        self._connected = False
        self._start_time = None

        # Posting state
        self._video_uploaded = False
        self._caption_entered = False
        self._post_clicked = False

        # Error tracking
        self._last_error_type = None
        self._last_error_message = None
        self._last_screenshot_path = None

        # Claude client - lazy init
        self._claude = None

    @property
    def platform(self) -> str:
        """Return platform identifier."""
        return "tiktok"

    def _ensure_connection_manager(self):
        """Lazy-initialize the DeviceConnectionManager."""
        if self._conn is None:
            from device_connection import DeviceConnectionManager
            self._conn = DeviceConnectionManager(
                phone_name=self._phone_name,
                system_port=self._system_port,
                appium_url=self._appium_url
            )

    def _ensure_ui_controller(self):
        """Lazy-initialize the AppiumUIController."""
        if self._ui_controller is None and self._conn and self._conn.appium_driver:
            from appium_ui_controller import AppiumUIController
            self._ui_controller = AppiumUIController(self._conn.appium_driver)

    def _ensure_claude(self):
        """Lazy-initialize Claude client."""
        if self._claude is None:
            self._claude = anthropic.Anthropic()

    def connect(self) -> bool:
        """Connect to device.

        Returns:
            True if connection successful, False otherwise.
        """
        self._ensure_connection_manager()
        self._start_time = time.time()

        try:
            self._conn.connect()
            self._ensure_ui_controller()
            self._connected = True
            return True
        except Exception as e:
            print(f"[TikTokPoster] Connect failed: {e}")
            return False

    def _classify_error(self, error_message: str) -> tuple:
        """Classify an error message into type and category.

        Args:
            error_message: Error message to classify.

        Returns:
            Tuple of (error_type, error_category, retryable).
        """
        error_lower = error_message.lower()

        for error_type, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if pattern in error_lower:
                    is_account_error = error_type in self.ACCOUNT_ERROR_TYPES
                    category = 'account' if is_account_error else 'infrastructure'
                    retryable = not is_account_error
                    return (error_type, category, retryable)

        return ('unknown', 'unknown', True)

    def _detect_error_state(self, elements: List[Dict]) -> Optional[tuple]:
        """Detect TikTok error states from UI elements.

        Args:
            elements: List of UI element dicts.

        Returns:
            Tuple of (error_type, error_message) or None if no error.
        """
        all_text = ' '.join([
            (e.get('text', '') + ' ' + e.get('desc', '')).lower()
            for e in elements
        ])

        for error_type, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if pattern in all_text:
                    return (error_type, pattern)

        return None

    def post(self, video_path: str, caption: str, humanize: bool = False, max_steps: int = 30) -> PostResult:
        """Post video to TikTok using Claude-driven UI navigation.

        Args:
            video_path: Path to video file.
            caption: Caption/description text.
            humanize: Whether to perform human-like delays.
            max_steps: Maximum navigation steps before giving up.

        Returns:
            PostResult with outcome details.
        """
        if not self._connected:
            return PostResult(
                success=False,
                error="Not connected - call connect() first",
                error_type="connection_error",
                error_category="infrastructure",
                retryable=True,
                platform=self.platform,
                account=self._phone_name
            )

        # Reset state
        self._video_uploaded = False
        self._caption_entered = False
        self._post_clicked = False
        self._last_error_type = None
        self._last_error_message = None

        try:
            # Initialize Claude
            self._ensure_claude()

            # Upload video to phone
            self._upload_video(video_path)

            # Launch TikTok
            self._restart_app()

            # Humanize before posting if requested
            if humanize:
                self._humanize_before_post()

            # Claude-driven navigation loop
            for step in range(max_steps):
                print(f"\n--- TikTok Step {step + 1} ---")

                # Dump UI
                elements = self._dump_ui()
                if not elements:
                    print("  No UI elements found, waiting...")
                    time.sleep(2)
                    continue

                # Check for errors
                error_result = self._detect_error_state(elements)
                if error_result:
                    error_type, error_msg = error_result
                    print(f"  [ERROR] {error_type}: {error_msg}")
                    self._last_error_type = error_type
                    self._last_error_message = error_msg

                    duration = time.time() - self._start_time if self._start_time else 0
                    is_account = error_type in self.ACCOUNT_ERROR_TYPES

                    return PostResult(
                        success=False,
                        error=f"{error_type}: {error_msg}",
                        error_type=error_type,
                        error_category='account' if is_account else 'infrastructure',
                        retryable=not is_account,
                        platform=self.platform,
                        account=self._phone_name,
                        duration_seconds=duration
                    )

                # Get Claude's action recommendation
                print(f"  Analyzing UI... ({len(elements)} elements)")
                # Debug: Print first 10 elements
                for i, e in enumerate(elements[:10]):
                    txt = e.get('text', '')[:30] if e.get('text') else ''
                    desc = e.get('desc', '')[:30] if e.get('desc') else ''
                    ctr = e.get('center', '')
                    print(f"    [{i}] text='{txt}' desc='{desc}' center={ctr}")
                action = self._analyze_ui(elements, caption)
                print(f"  Action: {action['action']} - {action.get('reason', '')}")

                # Update state from Claude's response
                if action.get('caption_entered'):
                    self._caption_entered = True
                if action.get('post_clicked'):
                    self._post_clicked = True

                # Check if done
                if action['action'] == 'done':
                    print("  Post completed!")
                    duration = time.time() - self._start_time if self._start_time else 0
                    return PostResult(
                        success=True,
                        platform=self.platform,
                        account=self._phone_name,
                        duration_seconds=duration
                    )

                # Execute the action
                self._execute_action(action, elements, caption)

                # Small delay between steps
                time.sleep(1)

            # Max steps reached
            duration = time.time() - self._start_time if self._start_time else 0
            return PostResult(
                success=False,
                error=f"Max steps ({max_steps}) reached without completing post",
                error_type="max_steps",
                error_category="infrastructure",
                retryable=True,
                platform=self.platform,
                account=self._phone_name,
                duration_seconds=duration
            )

        except Exception as e:
            duration = time.time() - self._start_time if self._start_time else 0
            error_type, category, retryable = self._classify_error(str(e))

            return PostResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                error_type=error_type,
                error_category=category,
                retryable=retryable,
                platform=self.platform,
                account=self._phone_name,
                duration_seconds=duration
            )

    def _dump_ui(self) -> List[Dict]:
        """Dump current UI elements from Appium."""
        try:
            elements, _ = self._ui_controller.dump_ui()
            return elements
        except Exception as e:
            print(f"  [TikTokPoster] dump_ui error: {e}")
            return []

    def _format_elements_for_claude(self, elements: List[Dict]) -> str:
        """Format UI elements for Claude prompt."""
        lines = ["UI Elements:"]
        for i, elem in enumerate(elements):
            parts = [f"[{i}]"]
            if elem.get('text'):
                parts.append(f"text='{elem['text']}'")
            if elem.get('desc'):
                parts.append(f"desc='{elem['desc']}'")
            if elem.get('id'):
                parts.append(f"id='{elem['id']}'")
            if elem.get('center'):
                parts.append(f"center={elem['center']}")
            if elem.get('clickable'):
                parts.append("clickable")
            lines.append("  " + " ".join(parts))
        return "\n".join(lines)

    def _analyze_ui(self, elements: List[Dict], caption: str) -> Dict:
        """Send UI to Claude and get next action."""
        ui_description = self._format_elements_for_claude(elements)

        prompt = self.TIKTOK_NAVIGATION_PROMPT.format(
            video_uploaded=self._video_uploaded,
            caption_entered=self._caption_entered,
            post_clicked=self._post_clicked,
            caption=caption[:100],  # Truncate for prompt
            ui_description=ui_description
        )

        response = self._claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse JSON response
        text = response.content[0].text.strip()
        print(f"  [Claude Raw Response]: {text[:500]}")  # Debug logging

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in text:
            match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)
        elif "```" in text:
            match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)

        try:
            action = json.loads(text)
        except json.JSONDecodeError:
            # Fallback - try to extract action manually
            action = {"action": "scroll_down", "reason": "Could not parse response, scrolling to find elements"}

        return action

    def _execute_action(self, action: Dict, elements: List[Dict], caption: str):
        """Execute the action recommended by Claude."""
        action_type = action.get('action', '')

        if action_type == 'tap':
            idx = action.get('element_index', 0)
            if 0 <= idx < len(elements) and elements[idx].get('center'):
                x, y = elements[idx]['center']
                print(f"  Tapping element {idx} at ({x}, {y})")
                self._ui_controller.tap(x, y)
            else:
                print(f"  Invalid element index {idx}, skipping tap")

        elif action_type == 'tap_and_type':
            idx = action.get('element_index', 0)
            text = action.get('text', caption)
            if 0 <= idx < len(elements) and elements[idx].get('center'):
                x, y = elements[idx]['center']
                print(f"  Tapping element {idx} at ({x}, {y}) and typing")
                self._ui_controller.tap(x, y)
                time.sleep(0.5)
                self._ui_controller.type_text(text)
                self._caption_entered = True
            else:
                print(f"  Invalid element index {idx}, skipping tap_and_type")

        elif action_type == 'scroll_down':
            print("  Scrolling down")
            self._ui_controller.swipe(360, 800, 360, 400, duration_ms=300)

        elif action_type == 'scroll_up':
            print("  Scrolling up")
            self._ui_controller.swipe(360, 400, 360, 800, duration_ms=300)

        elif action_type == 'back':
            print("  Pressing back")
            self._ui_controller.press_key('BACK')

        elif action_type == 'home':
            print("  Going to home")
            self._ui_controller.press_key('HOME')

        elif action_type == 'open_tiktok':
            print("  Opening TikTok")
            self._restart_app()

        elif action_type == 'done':
            pass  # Handled in main loop

        else:
            print(f"  Unknown action: {action_type}")

    def _humanize_before_post(self):
        """Perform random human-like actions before posting."""
        import random
        print("[TikTokPoster] Humanizing before post...")

        # Random short scrolls
        for _ in range(random.randint(1, 3)):
            self._ui_controller.swipe(360, 700, 360, 500, duration_ms=200)
            time.sleep(random.uniform(0.5, 1.5))

        time.sleep(random.uniform(1, 2))

    def _upload_video(self, video_path: str):
        """Upload video file to phone.

        Args:
            video_path: Local path to video file.
        """
        print(f"[TikTokPoster] Uploading video: {video_path}")

        # Use GeelarkClient to upload
        client = self._conn.client
        phone_id = self._conn.phone_id

        resource_url = client.upload_file_to_geelark(video_path)
        upload_result = client.upload_file_to_phone(phone_id, resource_url)
        task_id = upload_result.get("taskId")
        client.wait_for_upload(task_id)

        # Trigger media scanner
        self._conn.adb_command(
            "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
            "-d file:///sdcard/Download/"
        )
        time.sleep(3)

        self._video_uploaded = True
        print("[TikTokPoster] Video uploaded to phone")

    def _restart_app(self):
        """Restart TikTok app."""
        print("[TikTokPoster] Restarting TikTok...")
        self._conn.adb_command(f"am force-stop {self.APP_PACKAGE}")
        time.sleep(2)
        self._conn.adb_command(f"monkey -p {self.APP_PACKAGE} 1")
        time.sleep(5)

    def cleanup(self):
        """Cleanup and disconnect."""
        print("[TikTokPoster] Cleaning up...")

        if self._conn:
            try:
                # Clean up video files
                self._conn.adb_command("rm -f /sdcard/Download/*.mp4")
            except Exception:
                pass

            try:
                self._conn.disconnect()
            except Exception as e:
                print(f"[TikTokPoster] Cleanup warning: {e}")
            finally:
                self._conn = None
                self._ui_controller = None
                self._connected = False
