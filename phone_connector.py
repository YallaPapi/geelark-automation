"""
Phone Connector - shared helper for phone connection in setup scripts.

This module provides a lightweight interface for the find→start→enable ADB→connect
flow used by setup scripts (setup_adbkeyboard.py, setup_clipboard_helper.py, etc.)

For full posting workflow with Appium, use DeviceConnectionManager instead.
"""
import subprocess
import time
from typing import Optional, Tuple

from config import Config
from geelark_client import GeelarkClient


ADB_PATH = Config.ADB_PATH


class PhoneConnector:
    """Lightweight helper for phone connection in setup scripts."""

    def __init__(self, geelark_client: GeelarkClient = None):
        """
        Initialize the connector.

        Args:
            geelark_client: Optional GeelarkClient instance (for dependency injection).
        """
        self.client = geelark_client or GeelarkClient()

    def find_phone(self, phone_name: str) -> Optional[dict]:
        """Find a phone by name or ID.

        Args:
            phone_name: Phone serial name or ID.

        Returns:
            Phone info dict with id, serialName, status, etc., or None if not found.
        """
        for page in range(1, 10):
            result = self.client.list_phones(page=page, page_size=100)
            for phone in result.get("items", []):
                if phone.get("serialName") == phone_name or phone.get("id") == phone_name:
                    return phone
            if len(result.get("items", [])) < 100:
                break
        return None

    def ensure_running(self, phone_id: str, timeout: int = 120) -> bool:
        """Ensure phone is running, start if needed.

        Args:
            phone_id: Phone ID from find_phone().
            timeout: Max seconds to wait for phone to start.

        Returns:
            True if phone is running.
        """
        # Check current status
        status_result = self.client.get_phone_status([phone_id])
        items = status_result.get("successDetails", [])
        if items and items[0].get("status") == 0:
            return True  # Already running

        # Start phone
        print("  Starting phone...")
        self.client.start_phone(phone_id)

        # Wait for ready
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2)
            status_result = self.client.get_phone_status([phone_id])
            items = status_result.get("successDetails", [])
            if items and items[0].get("status") == 0:
                print(f"    Phone ready")
                return True

        print(f"    Phone start timeout after {timeout}s")
        return False

    def connect_adb(self, phone_id: str) -> Tuple[str, str]:
        """Enable ADB and establish connection.

        Args:
            phone_id: Phone ID.

        Returns:
            Tuple of (device_string, password) e.g. ("192.168.1.1:5555", "abc123")

        Raises:
            Exception: If ADB cannot be enabled.
        """
        # Enable ADB
        print("  Enabling ADB...")
        self.client.enable_adb(phone_id)
        time.sleep(5)

        # Get ADB info
        adb_info = self.client.get_adb_info(phone_id)
        if not adb_info or not adb_info.get('ip') or not adb_info.get('port'):
            raise Exception("Failed to get ADB info")

        device = f"{adb_info['ip']}:{adb_info['port']}"
        password = adb_info.get('pwd', '')

        # Connect via ADB
        print(f"  Connecting to {device}...")
        subprocess.run([ADB_PATH, "connect", device], capture_output=True)
        time.sleep(1)

        # Authenticate with glogin
        if password:
            result = subprocess.run(
                [ADB_PATH, "-s", device, "shell", f"glogin {password}"],
                capture_output=True, encoding='utf-8', errors='replace', timeout=30
            )
            login_result = result.stdout.strip() if result.stdout else ""
            print(f"  Login: {login_result or 'OK'}")

        return device, password

    def setup_for_adb(self, phone_name: str) -> Tuple['GeelarkClient', str, str, str]:
        """Full setup flow: find → start → connect ADB.

        This is the main convenience method for setup scripts.

        Args:
            phone_name: Phone serial name.

        Returns:
            Tuple of (client, phone_id, device_string, password)

        Raises:
            Exception: If phone not found or setup fails.
        """
        # Find phone
        print(f"Finding phone: {phone_name}")
        phone = self.find_phone(phone_name)
        if not phone:
            raise Exception(f"Phone not found: {phone_name}")

        phone_id = phone["id"]
        print(f"  Found: {phone.get('serialName')} (Status: {phone.get('status')})")

        # Ensure running
        if phone.get("status") != 0:
            if not self.ensure_running(phone_id):
                raise Exception(f"Failed to start phone: {phone_name}")
            time.sleep(5)

        # Connect ADB
        device, password = self.connect_adb(phone_id)

        return self.client, phone_id, device, password


def adb_shell(device: str, cmd: str, timeout: int = 30) -> str:
    """Run ADB shell command on a device.

    Convenience function for setup scripts.

    Args:
        device: Device string (e.g., "192.168.1.1:5555")
        cmd: Shell command to run.
        timeout: Command timeout in seconds.

    Returns:
        Command output as string.
    """
    result = subprocess.run(
        [ADB_PATH, "-s", device, "shell", cmd],
        capture_output=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""


def adb_install(device: str, apk_path: str, timeout: int = 120) -> str:
    """Install APK on a device.

    Convenience function for setup scripts.

    Args:
        device: Device string.
        apk_path: Path to APK file.
        timeout: Installation timeout in seconds.

    Returns:
        Installation output.
    """
    result = subprocess.run(
        [ADB_PATH, "-s", device, "install", "-r", apk_path],
        capture_output=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""
