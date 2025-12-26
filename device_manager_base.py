"""
Device Manager Base Class.

Abstract base class defining the interface for device management.
Implementations:
    - DeviceConnectionManager (Geelark cloud phones)
    - GrapheneOSDeviceManager (Physical GrapheneOS devices)

This abstraction enables the same posting/follow code to work
with either Geelark cloud phones or physical GrapheneOS devices.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class DeviceManager(ABC):
    """
    Abstract base class for device management.

    All device managers must implement this interface to be used
    with SmartInstagramPoster, TikTokPoster, and the parallel workers.
    """

    @abstractmethod
    def ensure_connected(self, account_name: str) -> bool:
        """
        Ensure device is connected and ready for the given account.

        For Geelark: finds phone by name, starts it, enables ADB, authenticates
        For GrapheneOS: verifies USB connection, switches to correct profile

        Args:
            account_name: The Instagram/TikTok account name to connect for

        Returns:
            True if device is ready, raises exception on failure

        Raises:
            Exception: If device cannot be connected or prepared
        """
        pass

    @abstractmethod
    def get_adb_address(self) -> str:
        """
        Get ADB connection address for Appium.

        For Geelark: returns "ip:port" (e.g., "192.168.1.100:5555")
        For GrapheneOS: returns USB serial (e.g., "32271FDH2006RW")

        Returns:
            ADB address string suitable for Appium's udid capability
        """
        pass

    @abstractmethod
    def upload_video(self, local_path: str) -> str:
        """
        Upload video to device, return remote path.

        For Geelark: uses Geelark API upload (upload_file_to_phone)
        For GrapheneOS: uses adb push to /sdcard/Download/

        Args:
            local_path: Local path to the video file

        Returns:
            Remote path on device where video was uploaded

        Raises:
            Exception: If upload fails
        """
        pass

    @abstractmethod
    def get_appium_caps(self) -> Dict:
        """
        Get Appium desired capabilities for this device.

        Returns dict with at minimum:
            - platformName: 'Android'
            - automationName: 'UiAutomator2'
            - udid: device identifier (IP:port or serial)
            - noReset: True

        Returns:
            Dictionary of Appium desired capabilities
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """
        Cleanup after posting completes.

        For Geelark: stops the cloud phone to save resources/cost
        For GrapheneOS: no-op (physical device stays on)

        Should be called in a finally block to ensure cleanup happens.
        """
        pass

    @property
    @abstractmethod
    def device_type(self) -> str:
        """
        Return the device type identifier.

        Returns:
            'geelark' for cloud phones, 'grapheneos' for physical devices
        """
        pass

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<{self.__class__.__name__} type={self.device_type}>"
