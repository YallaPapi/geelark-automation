"""TikTok poster implementation - implements BasePoster interface for TikTok video posting."""
import os
import time
import json
import re
import base64
from datetime import datetime
from typing import Optional, Dict, List, Tuple

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

=== CURRENT STATE ===
- Video file uploaded to phone storage: {video_uploaded}
- Video selected from gallery: {video_selected}
- Caption/description entered: {caption_entered}
- Post button clicked: {post_clicked}
- Caption to post: "{caption}"

=== UI ELEMENTS ===
{ui_description}

=== TIKTOK POSTING FLOW (follow in order) ===

STEP 1: TAP CREATE BUTTON (from home feed)
- Look for "+" button in bottom navigation bar (usually center)
- May have text "Create", or just the + icon
- Common element patterns: class='...ImageView', desc='Create' or desc='Add'
- ACTION: tap the Create/+ element
- NOTE: If you see "Templates", "New video", "Drafts" - you're already past this step, go to STEP 1B

STEP 1B: TAP "NEW VIDEO" OR RECOGNIZE VIDEO PREVIEW (from template screen)
- If you see a template screen with: "Templates", "New video", "Drafts", "Photo editor", "AutoCut", "Captions"
- FIRST check if you ALSO see "Select" and "Next" buttons - if yes, you're on VIDEO PREVIEW screen (skip to STEP 2B)
- If no Select/Next, this is the creation menu - tap text="New video" to go to camera view
- DO NOT tap "CREATE" button at bottom (that's for templates)
- ACTION: tap "New video" OR if Select/Next visible, go to STEP 2B

STEP 2B: VIDEO PREVIEW SCREEN (has Select + Next buttons)
- If you see "Select" and "Next" buttons at bottom, you're previewing a video
- This means a video is already selected from the gallery
- DO NOT tap "New video" again - that will restart the flow
- ACTION: tap "Next" button to proceed to editing → set video_selected=true

STEP 2: TAP UPLOAD (from camera view)
- After tapping "New video", you see camera/record view with:
  - Red record button in center (DO NOT tap this)
  - "Upload" option (usually bottom-right area)
  - May show "Effects", "Flip", "Timer", "Flash" buttons
- Look for "Upload" text/button
- Common patterns: text='Upload', desc='Upload', or gallery icon
- ACTION: tap Upload element → set video_selected=false (not selected yet)
- NOTE: If there's no "Upload" visible, try scrolling the bottom bar or look for a gallery thumbnail

STEP 2C: GALLERY SCREEN (media picker)
- If you see: "Recents", "All | Videos | Photos" tabs, grid of thumbnails, "Next" button
- This is the media gallery where you select videos/photos to post
- The uploaded video should be the FIRST thumbnail (top-left with duration like "0:09")
- Look for clickable elements in the thumbnail grid area (center=[~100, ~200] range for first row)
- ACTION: tap the first video thumbnail (top-left) → then tap "Next" button

STEP 3: SELECT VIDEO FROM GALLERY
- Gallery shows video thumbnails with duration overlays
- Select the FIRST video (most recently uploaded) - it should be the video we just uploaded
- Look for: clickable thumbnail, duration text like "0:15"
- ACTION: tap the video thumbnail → set video_selected=true

STEP 4: TAP NEXT (after video selection)
- After selecting video, look for "Next" button (usually top-right or bottom)
- May need to tap "Next" multiple times (editing screens)
- Common patterns: text='Next', desc='Next'
- ACTION: tap Next

STEP 5: SKIP EDITING/EFFECTS
- May see: "Sounds", "Effects", "Text", "Stickers", "Filters" screens
- Look for "Next" or "Skip" to proceed
- If stuck, tap "Next" or "Skip" buttons
- ACTION: tap Next/Skip to proceed

STEP 6: ENTER CAPTION
- Look for caption/description input field
- Common patterns: text='Describe your video', text='Add a description', desc='Caption'
- The field may be empty or have placeholder text
- ACTION: tap_and_type on caption field with the caption text → set caption_entered=true

STEP 7: TAP POST BUTTON
- Look for "Post" button (usually red, bottom-right area)
- Common patterns: text='Post', class contains 'Button'
- ACTION: tap Post button → set post_clicked=true

STEP 8: CONFIRM SUCCESS
- After tapping Post, wait for confirmation
- Look for: "Uploading...", "Posted", "Your video is being uploaded", progress indicators
- If you see the main feed again, post succeeded
- ACTION: return action="done" when you see upload confirmation or return to feed

=== ERROR DETECTION ===
If you see ANY of these, the post cannot succeed - return done immediately:
- "Account banned" / "Account suspended" / "Account disabled"
- "Community guidelines violation" / "Content removed"
- "Log in to TikTok" / login/signup screens
- "No network connection" / "Connection failed"
- "You're posting too fast" / rate limit messages

=== POPUP HANDLING ===
- "Add sound" / "Add music": Tap "Skip" or "No thanks" or tap outside
- "Who can watch": Leave default, tap away or "Done"
- Permission requests (camera, microphone, storage): Tap "Allow"
- "Discard draft?": Tap "Discard" to retry
- Promotional overlays: Look for X or "Not now" to dismiss

=== RESPONSE FORMAT ===
Output ONLY valid JSON with these fields:
{{
    "action": "<one of: tap, tap_and_type, scroll_down, scroll_up, back, home, open_tiktok, done>",
    "element_index": <integer index of UI element to interact with, required for tap/tap_and_type>,
    "text": "<text to type, required only for tap_and_type action>",
    "reason": "<brief explanation of why this action>",
    "video_selected": <true if video was just selected from gallery OR was already selected>,
    "caption_entered": <true if caption was just typed OR was already typed>,
    "post_clicked": <true if Post button was just clicked OR was already clicked>
}}

=== CRITICAL RULES ===
1. ALWAYS output valid JSON only - no explanations outside JSON
2. NEVER set state flags to true unless the action just happened OR state shows already done
3. If caption_entered=true in state, do NOT re-enter caption
4. If post_clicked=true in state, look for confirmation then return done
5. If stuck on same screen 3+ times, try: back → scroll → or open_tiktok
6. Return action="done" ONLY when you see upload progress/confirmation OR return to main feed after posting
7. Preserve state: if video_selected was true, keep returning video_selected=true

=== COMMON MISTAKES TO AVOID ===
- Don't tap "CREATE" button on template screen - tap "New video" instead
- Don't tap Record button (red circle) - tap Upload instead
- Don't skip video selection - must tap a video thumbnail
- Don't return done before seeing upload confirmation
- Don't re-enter caption if already entered
- If you see "Templates", "Photo editor", "AutoCut" - you're on template screen, tap "New video"
- If you see "Select" AND "Next" buttons - you're on video preview, tap "Next" (NOT "New video")
- If you see "Recents", thumbnail grid, "Next" - you're on gallery, tap first video then "Next"

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
        self._video_selected = False  # Video selected in gallery
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

    def post(self, video_path: str, caption: str, humanize: bool = False, max_steps: int = 25) -> PostResult:
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
        self._video_selected = False
        self._caption_entered = False
        self._post_clicked = False
        self._last_error_type = None
        self._last_error_message = None
        self._last_screenshot_path = None

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
                # Log step state
                self._log_step_state(step)

                # Dump UI
                elements = self._dump_ui()
                if not elements:
                    print("  No UI elements found, waiting...")
                    time.sleep(2)
                    continue

                # Save periodic UI dump for debugging
                self._debug_save_ui_dump(step, elements)

                # Check for errors
                error_result = self._detect_error_state(elements)
                if error_result:
                    error_type, error_msg = error_result
                    print(f"  [ERROR] {error_type}: {error_msg}")
                    self._last_error_type = error_type
                    self._last_error_message = error_msg

                    # Capture screenshot for error analysis
                    screenshot_path, analysis = self._analyze_failure_screenshot(f"error_{error_type}")
                    if analysis:
                        print(f"  [VISION] {analysis}")

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
                        duration_seconds=duration,
                        screenshot_path=self._last_screenshot_path
                    )

                # Get Claude's action recommendation
                print(f"  Analyzing UI... ({len(elements)} elements)")
                # Debug: Print first 10 elements (sanitize for Windows console)
                for i, e in enumerate(elements[:10]):
                    txt = (e.get('text', '')[:30] if e.get('text') else '').encode('ascii', 'replace').decode('ascii')
                    desc = (e.get('desc', '')[:30] if e.get('desc') else '').encode('ascii', 'replace').decode('ascii')
                    ctr = e.get('center', '')
                    print(f"    [{i}] text='{txt}' desc='{desc}' center={ctr}")
                action = self._analyze_ui(elements, caption)
                print(f"  Action: {action['action']} - {action.get('reason', '')}")

                # Update state from Claude's response
                if action.get('video_selected'):
                    self._video_selected = True
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

            # Max steps reached - capture screenshot for debugging
            print(f"  [WARNING] Max steps ({max_steps}) reached without completing post")
            screenshot_path, analysis = self._analyze_failure_screenshot("max_steps_timeout")
            if analysis:
                print(f"  [VISION] {analysis}")

            duration = time.time() - self._start_time if self._start_time else 0
            return PostResult(
                success=False,
                error=f"Max steps ({max_steps}) reached without completing post",
                error_type="max_steps",
                error_category="infrastructure",
                retryable=True,
                platform=self.platform,
                account=self._phone_name,
                duration_seconds=duration,
                screenshot_path=self._last_screenshot_path
            )

        except Exception as e:
            # Capture screenshot for exception debugging
            print(f"  [EXCEPTION] {type(e).__name__}: {str(e)}")
            try:
                screenshot_path, analysis = self._analyze_failure_screenshot(f"exception_{type(e).__name__}")
                if analysis:
                    print(f"  [VISION] {analysis}")
            except Exception:
                pass  # Don't let screenshot failure mask the original exception

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
                duration_seconds=duration,
                screenshot_path=self._last_screenshot_path
            )

    def _dump_ui(self) -> List[Dict]:
        """Dump current UI elements from Appium."""
        try:
            elements, _ = self._ui_controller.dump_ui()
            return elements
        except Exception as e:
            print(f"  [TikTokPoster] dump_ui error: {e}")
            return []

    def _debug_save_ui_dump(self, step: int, elements: List[Dict]) -> Optional[str]:
        """Save UI dump to file for debugging (every 5 steps).

        Args:
            step: Current navigation step number.
            elements: List of UI element dicts.

        Returns:
            Path to saved dump file or None.
        """
        # Only save every 5 steps to reduce I/O
        if step % 5 != 0:
            return None

        try:
            # Create debug dumps directory
            dump_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'debug_dumps')
            os.makedirs(dump_dir, exist_ok=True)

            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"tiktok_{self._phone_name}_step{step}_{timestamp}.json"
            filepath = os.path.join(dump_dir, filename)

            # Build debug data
            debug_data = {
                "timestamp": timestamp,
                "account": self._phone_name,
                "step": step,
                "state": {
                    "video_uploaded": self._video_uploaded,
                    "video_selected": self._video_selected,
                    "caption_entered": self._caption_entered,
                    "post_clicked": self._post_clicked
                },
                "element_count": len(elements),
                "elements": elements[:50]  # Limit to first 50 elements
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(debug_data, f, indent=2, ensure_ascii=False)

            print(f"  [DEBUG] UI dump saved: {filename}")
            return filepath

        except Exception as e:
            print(f"  [DEBUG] Failed to save UI dump: {e}")
            return None

    def _log_step_state(self, step: int):
        """Log current state at beginning of step."""
        print(f"\n{'='*60}")
        print(f"[TikTok Step {step + 1}]")
        print(f"  State: video_uploaded={self._video_uploaded}, video_selected={self._video_selected}, caption_entered={self._caption_entered}, post_clicked={self._post_clicked}")
        print(f"{'='*60}")

    def _format_elements_for_claude(self, elements: List[Dict]) -> str:
        """Format UI elements for Claude prompt."""
        lines = ["UI Elements:"]
        for i, elem in enumerate(elements):
            parts = [f"[{i}]"]
            if elem.get('class'):
                parts.append(f"class='{elem['class']}'")
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
            video_selected=self._video_selected,
            caption_entered=self._caption_entered,
            post_clicked=self._post_clicked,
            caption=caption[:100],  # Truncate for prompt
            ui_description=ui_description
        )

        response = self._claude.messages.create(
            model="claude-haiku-4-5",
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

    def _capture_failure_screenshot(self, reason: str) -> Optional[str]:
        """Capture screenshot on failure for debugging.

        Args:
            reason: Description of why screenshot is being taken (e.g., 'max_steps', 'error_detected').

        Returns:
            Path to saved screenshot or None if capture failed.
        """
        # Create screenshots directory
        screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'error_screenshots')
        os.makedirs(screenshot_dir, exist_ok=True)

        # Generate filename with platform, account, reason, and timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_reason = reason.replace(' ', '_').replace(':', '')[:30]
        filename = f"tiktok_{self._phone_name}_{safe_reason}_{timestamp}.png"
        filepath = os.path.join(screenshot_dir, filename)

        try:
            if self._ui_controller and self._ui_controller._driver:
                self._ui_controller._driver.save_screenshot(filepath)
                print(f"  [TikTokPoster] Screenshot saved: {filename}")
                self._last_screenshot_path = filepath
                return filepath
            else:
                print("  [TikTokPoster] Cannot capture screenshot - no Appium driver")
        except Exception as e:
            print(f"  [TikTokPoster] Failed to save screenshot: {e}")

        return None

    def _analyze_failure_screenshot(self, context: str = "post failed") -> Tuple[Optional[str], Optional[str]]:
        """Capture screenshot and analyze with Claude Vision to understand failure.

        Args:
            context: Description of what was happening when failure occurred.

        Returns:
            Tuple of (screenshot_path, analysis_text) or (None, None) if failed.
        """
        # Capture screenshot first
        filepath = self._capture_failure_screenshot(context)
        if not filepath:
            return None, None

        try:
            # Read and encode screenshot
            with open(filepath, 'rb') as f:
                image_data = base64.standard_b64encode(f.read()).decode('utf-8')

            # Ensure Claude client is initialized
            self._ensure_claude()

            # Send to Claude Vision for analysis
            print("  [TikTokPoster] Analyzing screenshot with Claude Vision...")

            response = self._claude.messages.create(
                model="claude-haiku-4-5",
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
                                "text": f"""Analyze this TikTok app screenshot. Context: {context}

What do you see on the screen? Look for:
1. Any error messages, popups, or warnings
2. Login/signup screens (account logged out)
3. Verification or captcha requests
4. "Account suspended" or "banned" messages
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
            print(f"  [TikTokPoster] Vision analysis: {analysis[:100]}...")

            return filepath, analysis

        except Exception as e:
            print(f"  [TikTokPoster] Failed to analyze screenshot: {e}")
            return filepath if filepath and os.path.exists(filepath) else None, None
