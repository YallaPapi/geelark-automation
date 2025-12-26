"""
GrapheneOS Device Manager.

Device manager for GrapheneOS physical devices connected via USB.
Uses Android's multi-user feature for account isolation - each profile
can have its own Instagram/TikTok logged in.

Usage:
    from grapheneos_device_manager import GrapheneOSDeviceManager
    from grapheneos_config import PROFILE_MAPPING, DEVICE_SERIAL

    manager = GrapheneOSDeviceManager(
        serial=DEVICE_SERIAL,
        profile_mapping=PROFILE_MAPPING
    )

    # Validate environment before starting
    manager.validate_environment(appium_url="http://127.0.0.1:4723")

    # Connect for a specific account (switches to correct profile)
    manager.ensure_connected("my_instagram_account")

    # Upload video via adb push
    remote_path = manager.upload_video("local/video.mp4")

    # Get Appium capabilities
    caps = manager.get_appium_caps()
"""

import subprocess
import os
import time
import re
import logging
import requests
from typing import Dict, List, Optional, Tuple

from device_manager_base import DeviceManager
from config import Config

logger = logging.getLogger(__name__)


# =============================================================================
# Connectivity Validation Exceptions
# =============================================================================

class ADBNotFoundError(Exception):
    """Raised when ADB is not installed or not in PATH."""
    pass


class NoDeviceAttachedError(Exception):
    """Raised when no Android device is attached via ADB."""
    pass


class AppiumNotReachableError(Exception):
    """Raised when Appium server is not reachable."""
    pass


# =============================================================================
# Standalone Connectivity Check Functions
# =============================================================================

def check_adb_installed(adb_path: str = None) -> Tuple[bool, str]:
    """
    Check if ADB is installed and accessible.

    Args:
        adb_path: Path to ADB executable (uses Config.ADB_PATH if not provided)

    Returns:
        Tuple of (success: bool, version_or_error: str)

    Raises:
        ADBNotFoundError: If ADB is not found or cannot be executed
    """
    adb_path = adb_path or Config.ADB_PATH

    try:
        result = subprocess.run(
            [adb_path, 'version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            # Extract version from output
            version_line = result.stdout.strip().split('\n')[0]
            logger.info(f"ADB found: {version_line}")
            return True, version_line
        else:
            error_msg = f"ADB returned error: {result.stderr.strip()}"
            logger.error(error_msg)
            raise ADBNotFoundError(error_msg)
    except FileNotFoundError:
        error_msg = f"ADB not found at path: {adb_path}. Install Android platform-tools and add to PATH."
        logger.error(error_msg)
        raise ADBNotFoundError(error_msg)
    except subprocess.TimeoutExpired:
        error_msg = "ADB command timed out"
        logger.error(error_msg)
        raise ADBNotFoundError(error_msg)
    except Exception as e:
        error_msg = f"Failed to run ADB: {e}"
        logger.error(error_msg)
        raise ADBNotFoundError(error_msg)


def check_device_attached(adb_path: str = None, serial: str = None) -> Tuple[bool, List[str]]:
    """
    Check if any Android device is attached via ADB.

    Args:
        adb_path: Path to ADB executable
        serial: Optional specific serial to check for

    Returns:
        Tuple of (success: bool, list of attached device serials)

    Raises:
        NoDeviceAttachedError: If no devices are attached
    """
    adb_path = adb_path or Config.ADB_PATH

    try:
        result = subprocess.run(
            [adb_path, 'devices'],
            capture_output=True,
            text=True,
            timeout=10
        )

        devices = []
        for line in result.stdout.strip().split('\n')[1:]:  # Skip header
            if '\tdevice' in line and 'offline' not in line:
                device_serial = line.split('\t')[0]
                devices.append(device_serial)

        if not devices:
            error_msg = "No devices attached. Connect a device via USB and enable USB debugging."
            logger.error(error_msg)
            raise NoDeviceAttachedError(error_msg)

        # If specific serial requested, check for it
        if serial and serial not in devices:
            error_msg = f"Device {serial} not found. Available: {devices}"
            logger.error(error_msg)
            raise NoDeviceAttachedError(error_msg)

        logger.info(f"Found {len(devices)} device(s): {devices}")
        return True, devices

    except subprocess.TimeoutExpired:
        error_msg = "ADB devices command timed out"
        logger.error(error_msg)
        raise NoDeviceAttachedError(error_msg)
    except NoDeviceAttachedError:
        raise
    except Exception as e:
        error_msg = f"Failed to list devices: {e}"
        logger.error(error_msg)
        raise NoDeviceAttachedError(error_msg)


def check_appium_status(appium_url: str = "http://127.0.0.1:4723") -> Tuple[bool, Dict]:
    """
    Check if Appium server is reachable and ready.

    Args:
        appium_url: Appium server URL (e.g., "http://127.0.0.1:4723")

    Returns:
        Tuple of (success: bool, status_dict)

    Raises:
        AppiumNotReachableError: If Appium is not reachable
    """
    status_url = f"{appium_url.rstrip('/')}/status"

    try:
        response = requests.get(status_url, timeout=5)
        if response.status_code == 200:
            status = response.json()
            logger.info(f"Appium ready at {appium_url}")
            return True, status
        else:
            error_msg = f"Appium returned status {response.status_code}"
            logger.error(error_msg)
            raise AppiumNotReachableError(error_msg)
    except requests.ConnectionError:
        error_msg = f"Appium not reachable at {appium_url}. Start Appium server first."
        logger.error(error_msg)
        raise AppiumNotReachableError(error_msg)
    except requests.Timeout:
        error_msg = f"Appium connection timed out at {appium_url}"
        logger.error(error_msg)
        raise AppiumNotReachableError(error_msg)
    except Exception as e:
        error_msg = f"Failed to check Appium status: {e}"
        logger.error(error_msg)
        raise AppiumNotReachableError(error_msg)


def validate_grapheneos_environment(
    adb_path: str = None,
    serial: str = None,
    appium_url: str = None
) -> Dict[str, any]:
    """
    Validate the complete GrapheneOS automation environment.

    Performs all connectivity checks in order:
    1. ADB installed
    2. Device attached
    3. Appium reachable

    Args:
        adb_path: Path to ADB executable
        serial: Device serial to check for
        appium_url: Appium server URL

    Returns:
        Dict with validation results:
        {
            'adb_version': str,
            'devices': List[str],
            'appium_status': Dict,
        }

    Raises:
        ADBNotFoundError, NoDeviceAttachedError, or AppiumNotReachableError
    """
    results = {}

    print("[ENV CHECK] Validating GrapheneOS automation environment...")

    # 1. Check ADB
    print("  [1/3] Checking ADB installation...")
    _, adb_version = check_adb_installed(adb_path)
    results['adb_version'] = adb_version
    print(f"        ✓ {adb_version}")

    # 2. Check device
    print("  [2/3] Checking device connection...")
    _, devices = check_device_attached(adb_path, serial)
    results['devices'] = devices
    print(f"        ✓ Found device(s): {devices}")

    # 3. Check Appium (only if URL provided)
    if appium_url:
        print(f"  [3/3] Checking Appium at {appium_url}...")
        _, appium_status = check_appium_status(appium_url)
        results['appium_status'] = appium_status
        print(f"        ✓ Appium ready")
    else:
        print("  [3/3] Skipping Appium check (will be auto-started)")
        results['appium_status'] = None

    print("[ENV CHECK] All checks passed!")
    return results


class GrapheneOSDeviceManager(DeviceManager):
    """
    Device manager for GrapheneOS physical devices.

    Handles USB-connected Pixel devices running GrapheneOS.
    Uses Android multi-user profiles for account isolation.
    """

    def __init__(
        self,
        serial: str = "32271FDH2006RW",
        profile_mapping: Optional[Dict[str, int]] = None
    ):
        """
        Initialize GrapheneOS device manager.

        Args:
            serial: USB device serial number (from `adb devices`)
            profile_mapping: Maps account names to Android user IDs
                            e.g. {"account1": 0, "account2": 10, "account3": 11}
                            User 0 is Owner, 10+ are secondary profiles
        """
        self.serial = serial
        self.adb_path = Config.ADB_PATH
        self.profile_mapping = profile_mapping or {}
        self.current_profile: Optional[int] = None
        self._account_name: Optional[str] = None

    @property
    def device_type(self) -> str:
        """Return device type identifier."""
        return "grapheneos"

    def _adb(self, *args, timeout: int = 30) -> subprocess.CompletedProcess:
        """
        Run ADB command targeting this device.

        Args:
            *args: ADB command arguments (e.g., 'shell', 'am', 'get-current-user')
            timeout: Command timeout in seconds

        Returns:
            CompletedProcess with stdout, stderr, returncode
        """
        cmd = [self.adb_path, '-s', self.serial] + list(args)
        logger.debug(f"Running ADB: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode != 0 and result.stderr:
                logger.warning(f"ADB command failed: {result.stderr.strip()}")
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"ADB command timed out after {timeout}s: {' '.join(cmd)}")
            raise

    def ensure_connected(self, account_name: str) -> bool:
        """
        Verify USB connection and switch to correct profile for account.

        Args:
            account_name: The Instagram/TikTok account name

        Returns:
            True if device is ready

        Raises:
            Exception: If device not connected or profile not mapped
        """
        self._account_name = account_name

        # 1. Check device is connected via USB
        result = self._adb('get-state')
        if 'device' not in result.stdout:
            raise Exception(
                f"Device {self.serial} not connected. "
                f"Got state: {result.stdout.strip() or result.stderr.strip()}"
            )
        logger.info(f"Device {self.serial} is connected")

        # 2. Get target profile for this account
        target_profile = self.profile_mapping.get(account_name)
        if target_profile is None:
            raise Exception(
                f"No profile mapped for account: {account_name}. "
                f"Add it to PROFILE_MAPPING in grapheneos_config.py. "
                f"Available mappings: {list(self.profile_mapping.keys())}"
            )

        # 3. Switch profile if needed
        current = self._get_current_user()
        logger.info(f"Current user: {current}, target user: {target_profile}")

        if current != target_profile:
            logger.info(f"Switching from user {current} to user {target_profile}")
            self._switch_profile(target_profile)
            self.current_profile = target_profile

            # Verify switch was successful
            new_user = self._get_current_user()
            if new_user != target_profile:
                raise Exception(
                    f"Profile switch failed. Expected {target_profile}, got {new_user}"
                )
            logger.info(f"Successfully switched to user {target_profile}")
        else:
            logger.info(f"Already on correct user {current}")
            self.current_profile = current

        return True

    def _get_current_user(self) -> int:
        """
        Get the currently active Android user ID.

        Returns:
            User ID (0 = Owner, 10+ = secondary profiles)
        """
        result = self._adb('shell', 'am', 'get-current-user')
        try:
            return int(result.stdout.strip())
        except ValueError:
            raise Exception(
                f"Failed to get current user. Output: {result.stdout.strip()}"
            )

    def _switch_profile(self, user_id: int) -> None:
        """
        Switch to a different Android user profile.

        Args:
            user_id: Target user ID to switch to
        """
        result = self._adb('shell', 'am', 'switch-user', str(user_id))
        if result.returncode != 0:
            raise Exception(f"Failed to switch user: {result.stderr.strip()}")

        # Wait for profile switch animation and initialization
        logger.info(f"Waiting for profile {user_id} to become active...")
        time.sleep(3)

    def get_adb_address(self) -> str:
        """
        Return USB serial for Appium connection.

        For USB-connected devices, Appium uses the serial number
        directly instead of IP:port.

        Returns:
            Device serial number
        """
        return self.serial

    def upload_video(self, local_path: str) -> str:
        """
        Push video to device via ADB and trigger media scan.

        Args:
            local_path: Path to local video file

        Returns:
            Remote path on device (/sdcard/Download/filename.mp4)

        Raises:
            Exception: If adb push fails
        """
        if not os.path.exists(local_path):
            raise Exception(f"Video file not found: {local_path}")

        filename = os.path.basename(local_path)
        remote_path = f"/sdcard/Download/{filename}"

        logger.info(f"Pushing {local_path} to {remote_path}")
        result = self._adb('push', local_path, remote_path, timeout=120)

        if result.returncode != 0:
            raise Exception(
                f"adb push failed: {result.stderr.strip() or result.stdout.strip()}"
            )

        # Verify file exists on device
        check = self._adb('shell', 'ls', '-la', remote_path)
        if result.returncode != 0:
            raise Exception(f"File not found after push: {remote_path}")

        # CRITICAL: Trigger media scan so the video appears in gallery
        # Without this, TikTok won't see the uploaded video!
        print(f"  [MEDIA SCAN] Triggering media scan for {remote_path}")
        scan_result = self._adb(
            'shell', 'am', 'broadcast',
            '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
            '-d', f'file://{remote_path}'
        )
        print(f"  [MEDIA SCAN] Broadcast result: {scan_result.stdout.strip()}")

        # Also try the newer content provider method (for Android 10+)
        print(f"  [MEDIA SCAN] Running content scan_volume...")
        scan2_result = self._adb(
            'shell', 'content', 'call',
            '--method', 'scan_volume',
            '--uri', 'content://media',
            '--arg', 'external_primary'
        )
        print(f"  [MEDIA SCAN] Content result: {scan2_result.stdout.strip()}")

        # Wait for media scan to complete
        print(f"  [MEDIA SCAN] Waiting 3s for scan to complete...")
        time.sleep(3)

        print(f"  [MEDIA SCAN] Done! Video should now appear in TikTok gallery")
        return remote_path

    def get_appium_caps(self) -> Dict:
        """
        Get Appium desired capabilities for USB-connected device.

        Returns:
            Dictionary of Appium capabilities
        """
        return {
            'platformName': 'Android',
            'automationName': 'UiAutomator2',
            'udid': self.serial,
            'noReset': True,
            'fullReset': False,
            'newCommandTimeout': 300,
        }

    def cleanup(self) -> None:
        """
        No cleanup needed for physical device.

        Unlike Geelark cloud phones, physical devices stay on.
        """
        logger.debug(f"Cleanup called for {self.serial} - no action needed")
        pass

    def list_profiles(self) -> List[Dict]:
        """
        List all Android user profiles on the device.

        Useful for discovering available profiles and their IDs.

        Returns:
            List of dicts with 'id', 'name', and 'running' keys
        """
        result = self._adb('shell', 'pm', 'list', 'users')
        profiles = []

        for line in result.stdout.split('\n'):
            if 'UserInfo{' in line:
                # Parse: UserInfo{0:Owner:c13} running
                match = re.search(r'UserInfo\{(\d+):([^:]+):', line)
                if match:
                    profiles.append({
                        'id': int(match.group(1)),
                        'name': match.group(2),
                        'running': 'running' in line.lower()
                    })

        return profiles

    def wake_screen(self) -> None:
        """Wake up the device screen if it's off."""
        # Check if screen is on
        result = self._adb('shell', 'dumpsys', 'power')
        if 'mWakefulness=Awake' not in result.stdout:
            logger.info("Waking screen...")
            self._adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
            time.sleep(1)

    def unlock_screen(self, swipe_up: bool = True) -> None:
        """
        Unlock the screen (assumes no PIN/pattern on profile).

        Args:
            swipe_up: Whether to swipe up to dismiss lock screen
        """
        self.wake_screen()
        if swipe_up:
            # Swipe up to unlock (for lock screens without security)
            self._adb('shell', 'input', 'swipe', '540', '1800', '540', '800', '300')
            time.sleep(0.5)

    def validate_environment(self, appium_url: str = None) -> Dict:
        """
        Validate the automation environment before starting.

        Performs connectivity checks:
        1. ADB is installed
        2. This device is attached
        3. Appium is reachable (if URL provided)

        Args:
            appium_url: Optional Appium URL to check

        Returns:
            Dict with validation results

        Raises:
            ADBNotFoundError, NoDeviceAttachedError, or AppiumNotReachableError
        """
        return validate_grapheneos_environment(
            adb_path=self.adb_path,
            serial=self.serial,
            appium_url=appium_url
        )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<GrapheneOSDeviceManager "
            f"serial={self.serial} "
            f"profile={self.current_profile} "
            f"account={self._account_name}>"
        )
