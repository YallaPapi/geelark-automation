"""
TikTok Video Poster - Rules-Only Mode (Default)

Posts videos to TikTok using 100% rule-based navigation.
Based on screen detection patterns from AI-only data collection.

Usage:
    python tiktok_poster.py <phone_name> <video_path> <caption>

Modes:
    --rules-only (default): 100% rule-based navigation, no AI
    --hybrid: Rule-based with AI fallback for unknown screens
    --ai-only: Use AI for every decision (for flow mapping)

Example:
    python tiktok_poster.py themotivationmischief video.mp4 "Check this out! #fyp"
"""
import sys
import os
import argparse
import random

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
from device_manager_base import DeviceManager
# UI interactions
from appium_ui_controller import AppiumUIController
# Flow logging for pattern analysis
from flow_logger import FlowLogger
# Comprehensive error debugging with screenshots
from error_debugger import ErrorDebugger
# Hybrid Navigator - rule-based + AI fallback
from tiktok_hybrid_navigator import TikTokHybridNavigator
from tiktok_screen_detector import TikTokScreenType
from tiktok_id_map import set_tiktok_version
# Account-seeded humanization
from humanization import (
    BehaviorProfile,
    get_or_create_base_seed,
    get_session_seed,
    build_behavior_profile,
    tap_with_jitter,
    human_scroll_vertical,
    human_sleep,
    warmup_scrolls,
    cooldown_scrolls,
    # Logging utilities
    HumanizationLogger,
    get_humanization_logger,
    reset_humanization_logger
)

# Configure logging for humanization module
import logging
humanization_logger = logging.getLogger('humanization')
humanization_logger.setLevel(logging.INFO)

# Screen coordinates from centralized config
SCREEN_CENTER_X = Config.SCREEN_CENTER_X
SCREEN_CENTER_Y = Config.SCREEN_CENTER_Y

# TikTok package name
TIKTOK_PACKAGE = "com.zhiliaoapp.musically"


class TikTokPoster:
    """TikTok poster using rule-based navigation (100% deterministic by default)."""

    # Humanization constants (legacy - now using BehaviorProfile)
    TAP_JITTER_PX = 8
    SWIPE_JITTER_PX = 15
    DELAY_MIN_MS = 100
    DELAY_MAX_MS = 400
    WARMUP_SCROLLS_MIN = 0
    WARMUP_SCROLLS_MAX = 3
    IDLE_ACTION_CHANCE = 0.05

    def __init__(self, phone_name=None, system_port=8200, appium_url=None,
                 device_manager: DeviceManager = None, humanize: bool = True,
                 device_type: str = 'geelark'):
        """
        Initialize TikTokPoster.

        Args:
            phone_name: Phone/account name (required if device_manager not provided)
            system_port: Port for UiAutomator2 server
            appium_url: Appium server URL
            device_manager: Optional DeviceManager instance (for GrapheneOS or testing)
                           If not provided, creates DeviceConnectionManager (Geelark)
            humanize: Add random jitter to taps/swipes (default: True)
            device_type: 'geelark' or 'grapheneos' - used for behavior profile seeding
        """
        self.humanize = humanize
        self.device_type = device_type

        # Initialize account-seeded humanization
        self._init_humanization(phone_name or 'unknown', device_type)

        # Device manager: use provided one or create DeviceConnectionManager
        if device_manager is not None:
            self._device_manager = device_manager
            self.phone_name = phone_name or "grapheneos_device"
            # Create connection wrapper for Appium management
            self._conn = DeviceConnectionManager(
                phone_name=self.phone_name,
                system_port=system_port,
                appium_url=appium_url or Config.DEFAULT_APPIUM_URL
            )
            self._uses_external_device_manager = True
        else:
            # Legacy mode: use DeviceConnectionManager for Geelark
            if phone_name is None:
                raise ValueError("phone_name is required when device_manager is not provided")
            self._conn = DeviceConnectionManager(
                phone_name=phone_name,
                system_port=system_port,
                appium_url=appium_url or Config.DEFAULT_APPIUM_URL
            )
            self._device_manager = self._conn  # DeviceConnectionManager IS a DeviceManager
            self.phone_name = phone_name
            self._uses_external_device_manager = False

        # Expose client for compatibility (only available for Geelark)
        self.client = getattr(self._conn, 'client', None)
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
        self.last_screenshot_path = None

        # Error debugger (initialized per post)
        self._debugger = None

        # TikTok version (populated at start of post)
        self._tiktok_version = None

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

    def _init_humanization(self, phone_name: str, device_type: str):
        """
        Initialize account-seeded humanization profile.

        Creates a BehaviorProfile unique to this account that remains
        consistent across runs but varies between accounts.
        """
        # Get or create stable seed for this account
        self._base_seed = get_or_create_base_seed(device_type, phone_name)

        # Derive session seed (changes every 6 hours)
        self._session_seed = get_session_seed(self._base_seed)

        # Build profile from base seed (deterministic per account)
        self._behavior_profile = build_behavior_profile(self._base_seed)

        # Create RNG for this session
        self._rng = random.Random(self._session_seed)

        # Reset and initialize humanization logger for this session
        self._humanization_logger = reset_humanization_logger(max_detailed_logs=20)
        self._humanization_logger.log_session_start(
            device_type=device_type,
            account_name=phone_name,
            base_seed=self._base_seed,
            session_seed=self._session_seed,
            profile=self._behavior_profile
        )

        # Console output for immediate visibility
        print(f"[HUMANIZATION] Account: {phone_name}")
        print(f"[HUMANIZATION] Base seed: {self._base_seed}")
        print(f"[HUMANIZATION] Session seed: {self._session_seed}")
        print(f"[HUMANIZATION] Tap jitter: {self._behavior_profile.tap_jitter_min_px:.1f}-{self._behavior_profile.tap_jitter_max_px:.1f}px")
        print(f"[HUMANIZATION] Pre-scroll prob: {self._behavior_profile.prob_scroll_before_post:.0%}")

    def adb(self, cmd, timeout=30):
        """Run ADB shell command."""
        return self._conn.adb_command(cmd, timeout=timeout)

    def get_tiktok_version(self) -> str:
        """Get TikTok app version for debugging ID drift.

        Uses: adb shell dumpsys package com.zhiliaoapp.musically | grep versionName

        Returns:
            Version string (e.g., "35.3.3") or "unknown" if not found.
        """
        try:
            result = self.adb(f"dumpsys package {TIKTOK_PACKAGE}")
            if result:
                # Parse output to find versionName
                for line in result.split('\n'):
                    if 'versionName=' in line:
                        # Extract version from line like "versionName=35.3.3"
                        version = line.split('versionName=')[1].strip()
                        # Remove trailing info if any
                        if ' ' in version:
                            version = version.split()[0]
                        return version
            return "unknown"
        except Exception as e:
            print(f"  [WARN] Failed to get TikTok version: {e}")
            return "unknown"

    def _add_jitter(self, x, y, jitter_px):
        """Add random offset to coordinates for humanization."""
        if not self.humanize:
            return x, y
        jitter_x = random.randint(-jitter_px, jitter_px)
        jitter_y = random.randint(-jitter_px, jitter_px)
        return x + jitter_x, y + jitter_y

    def _random_delay(self):
        """Add random delay between actions for humanization."""
        if not self.humanize:
            return
        delay_ms = random.randint(self.DELAY_MIN_MS, self.DELAY_MAX_MS)
        time.sleep(delay_ms / 1000.0)

    def _do_warmup_scrolls(self):
        """Browse the feed randomly before starting to post (simulates human behavior).

        Uses account-seeded BehaviorProfile for consistent per-account behavior.
        """
        if not self.humanize:
            return

        # Use the new warmup_scrolls primitive with account-seeded profile
        num_scrolls = warmup_scrolls(
            driver=self.appium_driver,
            profile=self._behavior_profile,
            rng=self._rng,
            screen_height=2400 if self.device_type == 'grapheneos' else 1280,
            screen_width=1080 if self.device_type == 'grapheneos' else 720,
            log_action=True
        )

        if num_scrolls > 0:
            print(f"[WARMUP] Completed {num_scrolls} warmup scrolls")
        else:
            print(f"[WARMUP] Skipped (probability check)")

    def _swipe_back(self):
        """Swipe right twice to go back (required on Pixel/TikTok)."""
        for swipe_num in range(2):
            # Swipe from left edge to right
            start_x = random.randint(5, 60)
            end_x = random.randint(350, 650)
            y = random.randint(900, 1500)
            duration = random.randint(180, 380)
            print(f"  [RECOVERY] Swipe back {swipe_num + 1}/2 ({start_x} -> {end_x})")
            self.ui_controller.swipe(start_x, y, end_x, y, duration)

            # Delay between swipes (500-1500ms)
            if swipe_num == 0:
                delay = random.randint(500, 1500) / 1000.0
                time.sleep(delay)

        time.sleep(0.5)

    def _maybe_idle_action(self):
        """Occasionally do a small idle action (micro-movement, pause, etc.)."""
        if not self.humanize:
            return

        if random.random() > self.IDLE_ACTION_CHANCE:
            return  # No idle action this time

        action = random.choice(['pause', 'micro_scroll', 'tap_empty'])

        if action == 'pause':
            # Just pause and "look" at the screen (variable duration)
            pause_time = random.uniform(0.3, 2.5)
            print(f"  [IDLE] Pausing {pause_time:.1f}s")
            time.sleep(pause_time)

        elif action == 'micro_scroll':
            # Tiny scroll that doesn't change screens
            # Randomize everything: distance, start position, direction
            distance = random.randint(30, 180)
            direction = random.choice([-1, 1])
            x = random.randint(350, 730)
            start_y = random.randint(900, 1500)
            end_y = start_y + (distance * direction)
            duration = random.randint(80, 250)
            print(f"  [IDLE] Micro-scroll ({distance}px {'down' if direction < 0 else 'up'})")
            self.ui_controller.swipe(x, start_y, x, end_y, duration)
            time.sleep(random.uniform(0.2, 0.5))

        elif action == 'tap_empty':
            # Tap on center-ish area (usually safe/empty space on video)
            x = random.randint(150, 930)
            y = random.randint(700, 1500)
            print(f"  [IDLE] Tap empty area ({x}, {y})")
            self.ui_controller.tap(x, y)
            time.sleep(random.uniform(0.15, 0.4))

    def tap(self, x, y):
        """Tap at coordinates using Appium with optional jitter."""
        if self.ui_controller:
            actual_x, actual_y = self._add_jitter(x, y, self.TAP_JITTER_PX)
            print(f"  [TAP] ({actual_x}, {actual_y})" + (f" (jittered from {x},{y})" if self.humanize and (actual_x != x or actual_y != y) else ""))
            self._random_delay()
            self.ui_controller.tap(actual_x, actual_y)
        else:
            raise Exception("UI controller not initialized")

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        """Swipe gesture using Appium with optional jitter."""
        if self.ui_controller:
            # Add jitter to start and end points
            actual_x1, actual_y1 = self._add_jitter(x1, y1, self.SWIPE_JITTER_PX)
            actual_x2, actual_y2 = self._add_jitter(x2, y2, self.SWIPE_JITTER_PX)
            # Randomize duration slightly (±50ms)
            if self.humanize:
                duration_ms = duration_ms + random.randint(-50, 50)
            print(f"  [SWIPE] ({actual_x1},{actual_y1}) -> ({actual_x2},{actual_y2})")
            self._random_delay()
            self.ui_controller.swipe(actual_x1, actual_y1, actual_x2, actual_y2, duration_ms)
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
        """Connect to device using DeviceManager abstraction.

        For Geelark: Finds phone, starts it, enables ADB, connects Appium
        For GrapheneOS: Verifies USB connection, switches profile, connects Appium
        """
        if self._uses_external_device_manager:
            # GrapheneOS mode: use external device manager for connection
            print(f"Connecting via {self._device_manager.device_type}...")
            self._device_manager.ensure_connected(self.phone_name)

            # Set up _conn.device for Appium (uses serial/address from device manager)
            adb_address = self._device_manager.get_adb_address()
            self._conn.device = adb_address

            # Connect Appium directly for GrapheneOS (avoid Geelark-specific reconnect logic)
            print(f"Connecting Appium to USB device {adb_address}...")
            caps = self._device_manager.get_appium_caps()
            caps['appium:systemPort'] = self._conn.system_port

            options = UiAutomator2Options()
            for key, value in caps.items():
                if key.startswith('appium:'):
                    options.set_capability(key, value)
                else:
                    setattr(options, key.replace('appium:', ''), value)

            # Set standard options
            options.platform_name = caps.get('platformName', 'Android')
            options.automation_name = caps.get('automationName', 'UiAutomator2')
            options.device_name = adb_address
            options.udid = adb_address
            options.no_reset = True
            options.new_command_timeout = 300

            for attempt in range(3):
                try:
                    self._conn.appium_driver = webdriver.Remote(
                        command_executor=self._conn.appium_url,
                        options=options
                    )
                    print(f"  Appium connected to GrapheneOS device!")
                    return True
                except Exception as e:
                    print(f"  Appium attempt {attempt + 1}/3 failed: {e}")
                    if attempt < 2:
                        time.sleep(2)

            raise Exception("Failed to connect Appium to GrapheneOS device after 3 attempts")
        else:
            # Geelark mode: use full DeviceConnectionManager flow
            return self._conn.connect()

    def disconnect(self):
        """Cleanup after posting using DeviceManager abstraction.

        For Geelark: Stops cloud phone to save billing minutes
        For GrapheneOS: No-op (physical device stays on)
        """
        # Log humanization session summary
        if hasattr(self, '_humanization_logger') and self._humanization_logger:
            self._humanization_logger.log_session_end()
            summary = self._humanization_logger.get_summary()
            print(f"[HUMANIZATION] Session summary: {summary['total_actions']} actions")
            for action_type, count in summary['actions_by_type'].items():
                print(f"  {action_type}: {count}")

        # Close Appium driver if open
        try:
            if self.appium_driver:
                self.appium_driver.quit()
                print("  Appium driver closed")
        except Exception:
            pass

        # Use device manager's cleanup
        self._device_manager.cleanup()

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
        """Upload video to phone using DeviceManager abstraction.

        Works with both Geelark (API upload) and GrapheneOS (adb push).
        """
        if self.video_uploaded:
            print("  Video already uploaded")
            return

        print(f"\nUploading video: {video_path}")

        # Use DeviceManager's upload_video method
        # This abstracts away the difference between Geelark API and adb push
        remote_path = self._device_manager.upload_video(video_path)
        print(f"  Video uploaded to: {remote_path}")
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

        # Initialize error debugger with screenshots at every step
        self._debugger = ErrorDebugger(
            account=self.phone_name,
            job_id=f"tiktok_{int(time.time())}",
            output_dir="tiktok_error_logs"
        )
        print(f"[DEBUG] Screenshots will be saved to: {self._debugger.session_dir}")

        # Get TikTok version for ID drift debugging
        self._tiktok_version = self.get_tiktok_version()
        set_tiktok_version(self._tiktok_version)  # Set in ID map for logging context
        print(f"[VERSION] TikTok version: {self._tiktok_version}")

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
                caption=caption,
                device_type=self.device_type
            )
            if ai_fallback:
                print(f"[HYBRID MODE] Rule-based navigation with AI fallback")
            else:
                print(f"[RULES-ONLY] 100% rule-based navigation (no AI)")
            if self.humanize:
                print(f"[HUMANIZE] Jitter: ±{self.TAP_JITTER_PX}px taps, ±{self.SWIPE_JITTER_PX}px swipes")
                print(f"[HUMANIZE] Delays: {self.DELAY_MIN_MS}-{self.DELAY_MAX_MS}ms between actions")
                print(f"[HUMANIZE] Warmup: {self.WARMUP_SCROLLS_MIN}-{self.WARMUP_SCROLLS_MAX} feed scrolls, {int(self.IDLE_ACTION_CHANCE*100)}% idle action chance")
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

        # Warmup: browse feed before posting (simulates human behavior)
        self._do_warmup_scrolls()

        # Vision-action loop
        for step in range(max_steps):
            print(f"\n--- Step {step + 1} ---")

            # Dump UI
            elements, raw_xml = self.dump_ui()
            if not elements:
                print("  No UI elements found, waiting...")
                # Screenshot even when no elements found
                self._debugger.log_step(
                    step_name=f"step_{step+1}_no_elements",
                    success=False,
                    details={"reason": "No UI elements found"},
                    driver=self.appium_driver
                )
                time.sleep(2)
                continue

            # Check for account/app errors
            error_type, error_msg = self.detect_error_state(elements)
            if error_type:
                print(f"  [ERROR DETECTED] {error_type}: {error_msg}")
                self.last_error_type = error_type
                self.last_error_message = f"{error_type}: {error_msg}"

                # CAPTURE ERROR WITH SCREENSHOT
                error_file = self._debugger.capture_error(
                    error=Exception(f"{error_type}: {error_msg}"),
                    driver=self.appium_driver,
                    ui_elements=elements,
                    error_type=error_type,
                    phase="error_detection",
                    context={
                        "step": step + 1,
                        "error_message": error_msg,
                        "video_selected": self.video_selected,
                        "caption_entered": self.caption_entered,
                        "tiktok_version": self._tiktok_version
                    }
                )
                self.last_screenshot_path = error_file
                print(f"  [DEBUG] Error captured: {error_file}")

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
                    # HYBRID/RULES-ONLY MODE: Rule-based detection
                    print("  Analyzing (rules)...")

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

                    # SCREENSHOT AT EVERY STEP - critical for debugging
                    self._debugger.log_step(
                        step_name=f"step_{step+1}_{nav_result.screen_type.name}",
                        success=True,
                        details={
                            "screen_type": nav_result.screen_type.name,
                            "action": action['action'],
                            "confidence": nav_result.action_confidence,
                            "used_ai": nav_result.used_ai,
                            "elements_count": len(elements)
                        },
                        driver=self.appium_driver
                    )

                    # RECOVERY: If screen is UNKNOWN and no AI fallback, log and continue
                    # Don't do blind swipes - just capture state and let flow continue
                    if nav_result.screen_type == TikTokScreenType.UNKNOWN and not nav_result.used_ai:
                        print(f"  [UNKNOWN SCREEN] Captured screenshot for debugging")
                        self._debugger.capture_error(
                            error=Exception(f"Unknown screen at step {step+1}"),
                            driver=self.appium_driver,
                            ui_elements=elements,
                            error_type="unknown_screen",
                            phase="navigation",
                            context={
                                "step": step + 1,
                                "action_attempted": action['action'],
                                "video_selected": self.video_selected,
                                "caption_entered": self.caption_entered,
                                "tiktok_version": self._tiktok_version
                            }
                        )

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

                # CAPTURE ACTION ERROR WITH SCREENSHOT
                self._debugger.capture_error(
                    error=e,
                    driver=self.appium_driver,
                    ui_elements=elements,
                    error_type="action_error",
                    phase="action_execution",
                    context={
                        "step": step + 1,
                        "action": action_name,
                        "video_selected": self.video_selected,
                        "caption_entered": self.caption_entered,
                        "tiktok_version": self._tiktok_version
                    }
                )

                flow_logger.log_error("action_error", str(e), elements)
                # Check if UiAutomator2 crashed
                if 'instrumentation process is not running' in str(e):
                    print("  [ERROR] UiAutomator2 crashed!")
                    self.last_error_type = "uiautomator2_crash"
                    self.last_error_message = str(e)
                    flow_logger.close()
                    return False

            # NOTE: Idle actions disabled during posting flow - too risky without screen awareness
            # self._maybe_idle_action()

            time.sleep(1)

        print(f"\n[FAILED] Max steps ({max_steps}) reached")
        self.last_error_type = "max_steps"
        self.last_error_message = f"Max steps ({max_steps}) reached without completing post"

        # CAPTURE FINAL STATE WITH SCREENSHOT
        self._debugger.capture_error(
            error=Exception(f"Max steps ({max_steps}) reached"),
            driver=self.appium_driver,
            ui_elements=elements if 'elements' in dir() else None,
            error_type="max_steps",
            phase="completion",
            context={
                "max_steps": max_steps,
                "video_selected": self.video_selected,
                "caption_entered": self.caption_entered,
                "tiktok_version": self._tiktok_version
            }
        )
        print(f"  [DEBUG] Final state captured to: {self._debugger.session_dir}")

        flow_logger.log_failure("max_steps_reached")
        flow_logger.close()
        return False


def setup_humanization_logging(account_name: str, log_dir: str = "logs"):
    """Set up file logging for humanization module.

    Creates a log file at logs/humanization_{account}_{timestamp}.log
    """
    import os
    from datetime import datetime

    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"humanization_{account_name}_{timestamp}.log")

    # Set up file handler for humanization logger
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    # Add to humanization logger
    humanization_logger.addHandler(file_handler)

    # Also add console handler if not already present
    if not any(isinstance(h, logging.StreamHandler) for h in humanization_logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        humanization_logger.addHandler(console_handler)

    print(f"[LOGGING] Humanization logs: {log_file}")
    return log_file


def main():
    parser = argparse.ArgumentParser(
        description='Post video to TikTok',
        epilog='''
Examples:
  %(prog)s alice.account video.mp4 "My caption #fyp"
  %(prog)s alice.account video.mp4 "Caption" --device grapheneos
  %(prog)s alice.account video.mp4 "Caption" --ai-only
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Positional arguments (preferred)
    parser.add_argument('phone_name', nargs='?', help='Account/phone name')
    parser.add_argument('video_path', nargs='?', help='Path to video file')
    parser.add_argument('caption', nargs='?', help='Caption for the video')

    # Device and server options
    parser.add_argument('--device', '-d',
                        choices=['geelark', 'grapheneos'],
                        default='geelark',
                        help='Device type: geelark (cloud) or grapheneos (physical Pixel)')
    parser.add_argument('--appium-url',
                        help='Appium server URL (auto-started if not specified)')

    # Navigation mode options
    parser.add_argument('--rules-only', action='store_true', default=True,
                        help='Use 100%% rule-based navigation, no AI (default)')
    parser.add_argument('--hybrid', action='store_true',
                        help='Use rule-based with AI fallback for unknown screens')
    parser.add_argument('--ai-only', action='store_true',
                        help='Use AI for every decision (for flow mapping)')

    # Humanization options
    parser.add_argument('--no-humanize', action='store_true',
                        help='Disable humanization (no jitter/delays)')
    parser.add_argument('--max-steps', type=int, default=30,
                        help='Maximum navigation steps (default: 30)')

    # =========================================================================
    # LEGACY FLAGS (deprecated - for backwards compatibility)
    # These map to positional arguments with deprecation warnings
    # =========================================================================
    parser.add_argument('--account', dest='legacy_account',
                        help='DEPRECATED: Use positional phone_name instead')
    parser.add_argument('--video', dest='legacy_video',
                        help='DEPRECATED: Use positional video_path instead')
    parser.add_argument('--caption-flag', dest='legacy_caption',
                        help='DEPRECATED: Use positional caption instead')
    parser.add_argument('--mode', dest='legacy_mode',
                        choices=['ai-only', 'rules-only', 'hybrid'],
                        help='DEPRECATED: Use --ai-only, --rules-only, or --hybrid instead')

    args = parser.parse_args()

    # =========================================================================
    # HANDLE LEGACY FLAGS WITH DEPRECATION WARNINGS
    # =========================================================================
    legacy_used = []

    # Map legacy --account to phone_name
    if args.legacy_account:
        if args.phone_name:
            print("WARNING: Both positional phone_name and --account provided. Using positional.")
        else:
            args.phone_name = args.legacy_account
            legacy_used.append('--account')

    # Map legacy --video to video_path
    if args.legacy_video:
        if args.video_path:
            print("WARNING: Both positional video_path and --video provided. Using positional.")
        else:
            args.video_path = args.legacy_video
            legacy_used.append('--video')

    # Map legacy --caption-flag to caption
    if args.legacy_caption:
        if args.caption:
            print("WARNING: Both positional caption and --caption-flag provided. Using positional.")
        else:
            args.caption = args.legacy_caption
            legacy_used.append('--caption-flag')

    # Map legacy --mode to mode flags
    if args.legacy_mode:
        legacy_used.append('--mode')
        if args.legacy_mode == 'ai-only':
            args.ai_only = True
        elif args.legacy_mode == 'hybrid':
            args.hybrid = True
        # else rules-only (default)

    # Show deprecation warning if legacy flags were used
    if legacy_used:
        print("\n" + "="*60)
        print("DEPRECATION WARNING")
        print("="*60)
        print(f"Legacy flags used: {', '.join(legacy_used)}")
        print("\nPlease use the new CLI syntax:")
        print("  tiktok_poster.py <phone_name> <video_path> <caption> [options]")
        print("\nExample:")
        print("  tiktok_poster.py alice.account video.mp4 \"My caption\" --device grapheneos")
        print("="*60 + "\n")

    # Validate required arguments are present
    if not args.phone_name:
        parser.error("phone_name is required (positional or --account)")
    if not args.video_path:
        parser.error("video_path is required (positional or --video)")
    if not args.caption:
        parser.error("caption is required (positional or --caption-flag)")

    # Validate video path
    if not os.path.exists(args.video_path):
        print(f"ERROR: Video not found: {args.video_path}")
        sys.exit(1)

    # Determine mode (rules-only is default)
    use_hybrid = True
    ai_fallback = False  # Default: NO AI fallback

    if args.ai_only:
        use_hybrid = False
        ai_fallback = False
    elif args.hybrid:
        use_hybrid = True
        ai_fallback = True  # Enable AI fallback only if --hybrid specified
    # else: rules-only (default) - use_hybrid=True, ai_fallback=False

    # Humanization
    humanize = not args.no_humanize

    # Set up humanization logging to file
    if humanize:
        setup_humanization_logging(args.phone_name)

    # Create device manager and handle Appium based on device type
    device_manager = None
    appium_manager = None

    if args.device == 'grapheneos':
        # =====================================================================
        # GRAPHENEOS: 1:1 PORT FROM GEELARK - AUTO-START APPIUM
        # This mirrors exactly what parallel_worker.py does for Geelark
        # =====================================================================
        from grapheneos_device_manager import (
            GrapheneOSDeviceManager,
            validate_grapheneos_environment,
            ADBNotFoundError,
            NoDeviceAttachedError,
            AppiumNotReachableError
        )
        from grapheneos_config import PROFILE_MAPPING, DEVICE_SERIAL
        from parallel_config import get_config
        from appium_server_manager import AppiumServerManager, AppiumServerError

        # =====================================================================
        # CONNECTIVITY CHECKS - Validate environment BEFORE starting
        # =====================================================================
        print("\n" + "="*60)
        print("GRAPHENEOS ENVIRONMENT VALIDATION")
        print("="*60)
        try:
            # Only check Appium if user provided external URL
            # (otherwise we auto-start it below)
            validate_grapheneos_environment(
                serial=DEVICE_SERIAL,
                appium_url=args.appium_url if args.appium_url else None
            )
        except ADBNotFoundError as e:
            print(f"\n[ERROR] ADB not found: {e}")
            print("\nFix: Install Android platform-tools and add to PATH:")
            print("  1. Download from https://developer.android.com/tools/releases/platform-tools")
            print(f"  2. Extract and add to PATH, or set Config.ADB_PATH")
            print(f"  3. Current ADB path: {Config.ADB_PATH}")
            sys.exit(1)
        except NoDeviceAttachedError as e:
            print(f"\n[ERROR] No device attached: {e}")
            print("\nFix: Connect GrapheneOS device via USB:")
            print("  1. Enable USB debugging in Developer options")
            print("  2. Connect USB cable and authorize debugging")
            print(f"  3. Expected serial: {DEVICE_SERIAL}")
            sys.exit(1)
        except AppiumNotReachableError as e:
            print(f"\n[ERROR] Appium not reachable: {e}")
            print("\nFix: Start Appium server or let script auto-start:")
            print("  1. Remove --appium-url flag to auto-start Appium")
            print("  2. Or start Appium manually: appium --address 127.0.0.1 --port 4723")
            sys.exit(1)
        print("="*60 + "\n")

        device_manager = GrapheneOSDeviceManager(
            serial=DEVICE_SERIAL,
            profile_mapping=PROFILE_MAPPING
        )
        print(f"[DEVICE] GrapheneOS physical device (USB)")

        # Create config for single worker (exactly like parallel_worker does)
        config = get_config(num_workers=1)
        worker_config = config.get_worker(0)

        # Use provided appium_url or auto-start Appium (1:1 with parallel_worker)
        if args.appium_url:
            appium_url = args.appium_url
            print(f"[APPIUM] Using external Appium at {appium_url}")
        else:
            # Auto-start Appium - EXACTLY like parallel_worker.py line 416-423
            appium_manager = AppiumServerManager(worker_config, config)
            print(f"[APPIUM] Starting Appium server on port {worker_config.appium_port}...")
            try:
                appium_manager.start(timeout=60)
                print(f"[APPIUM] Ready at {worker_config.appium_url}")
            except AppiumServerError as e:
                print(f"[APPIUM] Failed to start: {e}")
                sys.exit(1)
            appium_url = worker_config.appium_url

        system_port = worker_config.system_port
    else:
        # Geelark mode - Appium expected to be managed by orchestrator or external
        print(f"[DEVICE] Geelark cloud phone")
        appium_url = args.appium_url or Config.DEFAULT_APPIUM_URL
        system_port = 8200

    poster = TikTokPoster(
        phone_name=args.phone_name,
        device_manager=device_manager,
        appium_url=appium_url,
        system_port=system_port,
        humanize=humanize,
        device_type=args.device
    )
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
        # Stop Appium if we started it (1:1 with parallel_worker cleanup)
        if appium_manager:
            print("[APPIUM] Stopping Appium server...")
            appium_manager.stop()


if __name__ == "__main__":
    main()
