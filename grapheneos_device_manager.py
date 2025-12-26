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
from typing import Dict, List, Optional

from device_manager_base import DeviceManager
from config import Config

logger = logging.getLogger(__name__)


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
        Push video to device via ADB.

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

        logger.info(f"Successfully uploaded to {remote_path}")
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

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<GrapheneOSDeviceManager "
            f"serial={self.serial} "
            f"profile={self.current_profile} "
            f"account={self._account_name}>"
        )
