"""
Device Connection Manager - handles all device connection lifecycle.

This module encapsulates the logic for:
- Finding and starting Geelark cloud phones
- Enabling and connecting ADB
- Establishing Appium sessions
- Reconnecting on failures

Extracted from SmartInstagramPoster to improve separation of concerns.

Implements the DeviceManager interface for Geelark cloud phones.
"""
import subprocess
import time
from typing import Dict, Optional, Tuple

from appium import webdriver
from appium.options.android import UiAutomator2Options

from config import Config
from device_manager_base import DeviceManager
from geelark_client import GeelarkClient


ADB_PATH = Config.ADB_PATH


# Static ADB helper functions for use by parallel workers
def wait_for_adb_device(device_id: str, timeout: int = 90, logger=None) -> bool:
    """Wait for a device to appear in ADB devices list.

    This is an explicit ADB readiness gate that should be called AFTER
    starting the phone but BEFORE creating an Appium session.

    Args:
        device_id: The device identifier (e.g., "192.168.1.100:5555")
        timeout: Maximum seconds to wait (default 90)
        logger: Optional logger for status updates

    Returns:
        True if device is ready, False if timeout reached
    """
    deadline = time.time() + timeout
    check_count = 0

    while time.time() < deadline:
        check_count += 1
        try:
            result = subprocess.run(
                [ADB_PATH, "devices"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                if device_id in line and "device" in line and "offline" not in line:
                    if logger:
                        logger.info(f"ADB ready for {device_id} (took {check_count * 2}s)")
                    return True
        except Exception as e:
            if logger:
                logger.debug(f"ADB check error: {e}")

        time.sleep(2)

    if logger:
        logger.error(f"ADB timeout ({timeout}s) waiting for {device_id}")
    return False


def is_adb_device_alive(device_id: str, logger=None) -> bool:
    """Check if a device is still present in ADB.

    Call this periodically during job execution to detect ADB/device loss.

    Args:
        device_id: The device identifier (e.g., "192.168.1.100:5555")
        logger: Optional logger for status updates

    Returns:
        True if device is alive, False if device has been lost
    """
    try:
        result = subprocess.run(
            [ADB_PATH, "devices"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if device_id in line and "device" in line and "offline" not in line:
                return True
        if logger:
            logger.warning(f"Device {device_id} not found in ADB devices")
        return False
    except Exception as e:
        if logger:
            logger.warning(f"ADB devices check failed: {e}")
        return False


def reconnect_adb_device(device_id: str, logger=None) -> bool:
    """Attempt to reconnect an ADB device.

    Args:
        device_id: The device identifier (e.g., "192.168.1.100:5555")
        logger: Optional logger for status updates

    Returns:
        True if reconnect successful, False otherwise
    """
    try:
        # First disconnect
        subprocess.run([ADB_PATH, "disconnect", device_id],
                      capture_output=True, timeout=10)

        # Then reconnect
        result = subprocess.run([ADB_PATH, "connect", device_id],
                               capture_output=True, text=True, timeout=30)

        if "connected" in result.stdout.lower():
            if logger:
                logger.info(f"Reconnected ADB to {device_id}")
            return True
        else:
            if logger:
                logger.warning(f"ADB reconnect failed: {result.stdout}")
            return False
    except Exception as e:
        if logger:
            logger.warning(f"ADB reconnect error: {e}")
        return False


class DeviceConnectionManager(DeviceManager):
    """Manages device connection lifecycle for Geelark cloud phones.

    Implements the DeviceManager interface for use with SmartInstagramPoster,
    TikTokPoster, and parallel workers.
    """

    def __init__(
        self,
        phone_name: str,
        system_port: int = 8200,
        appium_url: str = None,
        geelark_client: GeelarkClient = None
    ):
        """
        Initialize the connection manager.

        Args:
            phone_name: Name or ID of the Geelark phone
            system_port: Port for UiAutomator2 server (unique per worker)
            appium_url: Appium server URL (default: from Config)
            geelark_client: Optional GeelarkClient instance (for dependency injection)
        """
        self.client = geelark_client or GeelarkClient()
        self.phone_name = phone_name
        self.phone_id: Optional[str] = None
        self.device: Optional[str] = None
        self.system_port = system_port
        self.appium_url = appium_url or Config.DEFAULT_APPIUM_URL
        self.appium_driver: Optional[webdriver.Remote] = None

    def adb_command(self, cmd: str, timeout: int = 30) -> str:
        """Run ADB shell command on the connected device."""
        if not self.device:
            raise Exception("No device connected - call connect() first")
        result = subprocess.run(
            [ADB_PATH, "-s", self.device, "shell", cmd],
            capture_output=True, timeout=timeout,
            encoding='utf-8', errors='replace'
        )
        return result.stdout.strip() if result.stdout else ""

    def find_phone(self) -> dict:
        """Find the phone by name or ID in Geelark.

        Returns:
            Phone info dict with id, serialName, status, etc.

        Raises:
            Exception: If phone not found.
        """
        print(f"Looking for phone: {self.phone_name}")

        for page in range(1, 10):
            result = self.client.list_phones(page=page, page_size=100)
            for p in result["items"]:
                if p["serialName"] == self.phone_name or p["id"] == self.phone_name:
                    print(f"Found: {p['serialName']} (ID: {p['id']}, Status: {p['status']})")
                    return p
            if len(result["items"]) < 100:
                break

        raise Exception(f"Phone not found: {self.phone_name}")

    def start_phone_if_needed(self, phone: dict) -> None:
        """Start the phone if it's not already running."""
        if phone["status"] == 0:
            return  # Already running

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

    def enable_adb_with_retry(self, max_retries: int = 3) -> dict:
        """Enable ADB and get connection info with retry logic.

        Returns:
            ADB info dict with ip, port, pwd.

        Raises:
            Exception: If ADB fails to enable after all retries.
        """
        adb_info = None

        for enable_retry in range(max_retries):
            print(f"Enabling ADB... (attempt {enable_retry + 1}/{max_retries})")
            try:
                self.client.enable_adb(self.phone_id)
            except Exception as e:
                print(f"  enable_adb() API error: {e}")
                if enable_retry < max_retries - 1:
                    print(f"  Retrying in 5s...")
                    time.sleep(5)
                    continue
                else:
                    raise Exception(f"enable_adb() failed after {max_retries} attempts: {e}")

            # Verify ADB is enabled
            print("Verifying ADB is enabled...")
            max_adb_attempts = 30
            for adb_attempt in range(max_adb_attempts):
                try:
                    adb_info = self.client.get_adb_info(self.phone_id)
                    if adb_info and adb_info.get('ip') and adb_info.get('port'):
                        print(f"  ADB enabled and ready (took {(adb_attempt + 1) * 2}s)")
                        return adb_info
                except Exception as e:
                    if adb_attempt == 0:
                        print(f"  ADB not ready yet, waiting... ({e})")
                    elif adb_attempt % 5 == 4:
                        print(f"  Still waiting for ADB... ({(adb_attempt + 1) * 2}s / {max_adb_attempts * 2}s)")
                time.sleep(2)

            # ADB verification failed - restart phone to reset ADB state
            print(f"  ADB verification failed after 60s")
            if enable_retry < max_retries - 1:
                print(f"  Restarting phone to reset ADB...")
                self._restart_phone_for_adb_recovery()

        raise Exception(f"ADB failed to enable after {max_retries} attempts")

    def _restart_phone_for_adb_recovery(self) -> None:
        """Restart phone to reset ADB state."""
        try:
            self.client.stop_phone(self.phone_id)
            time.sleep(3)
            self.client.start_phone(self.phone_id)
            for i in range(30):
                time.sleep(2)
                status_result = self.client.get_phone_status([self.phone_id])
                items = status_result.get("successDetails", [])
                if items and items[0].get("status") == 0:
                    print(f"  Phone restarted (took ~{(i+1)*2}s)")
                    break
            time.sleep(3)
        except Exception as restart_err:
            print(f"  Phone restart failed: {restart_err}")

    def connect_adb(self, adb_info: dict) -> None:
        """Establish ADB connection to device.

        Args:
            adb_info: Dict with ip, port, pwd from Geelark API.
        """
        self.device = f"{adb_info['ip']}:{adb_info['port']}"
        password = adb_info['pwd']

        # Clean any stale connection
        subprocess.run([ADB_PATH, "disconnect", self.device], capture_output=True)
        time.sleep(1)

        print(f"Connecting to {self.device}...")
        connect_result = subprocess.run(
            [ADB_PATH, "connect", self.device],
            capture_output=True, encoding='utf-8'
        )
        print(f"  ADB connect: {connect_result.stdout.strip()}")

        # Wait for device to be ready
        print("Waiting for ADB connection to stabilize...")
        self._wait_for_device_ready()

        # Authenticate with glogin
        self._authenticate_glogin(password)

    def _wait_for_device_ready(self, max_attempts: int = 30) -> None:
        """Wait for device to appear in ADB devices list."""
        device_ready = False

        for attempt in range(max_attempts):
            time.sleep(2)
            result = subprocess.run([ADB_PATH, "devices"], capture_output=True, encoding='utf-8')
            if self.device in result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if self.device in line and '\tdevice' in line:
                        device_ready = True
                        print(f"  Device {self.device} is ready (took {(attempt + 1) * 2}s)")
                        break
                if device_ready:
                    break
            if attempt % 5 == 4:
                print(f"  Waiting... ({(attempt + 1) * 2}s / {max_attempts * 2}s)")

        if not device_ready:
            raise Exception(f"Device {self.device} never appeared in ADB devices list after {max_attempts * 2}s")

    def _authenticate_glogin(self, password: str) -> None:
        """Authenticate with Geelark glogin command."""
        print("Authenticating with glogin...")

        for glogin_attempt in range(3):
            login_result = self.adb_command(f"glogin {password}")
            if login_result and "error" not in login_result.lower():
                print(f"  glogin: {login_result}")
                return
            elif "success" in login_result.lower():
                print(f"  glogin: {login_result}")
                return
            else:
                print(f"  glogin attempt {glogin_attempt + 1}/3 returned: [{login_result}]")
                time.sleep(2)

        print(f"  Warning: glogin may not have succeeded")

    def verify_adb_connection(self) -> bool:
        """Verify device is still connected via ADB."""
        result = subprocess.run([ADB_PATH, "devices"], capture_output=True, encoding='utf-8')
        if self.device in result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if self.device in line and '\tdevice' in line:
                    return True
        return False

    def reconnect_adb(self) -> bool:
        """Re-establish ADB connection if it dropped."""
        print(f"  [ADB RECONNECT] Device {self.device} offline, reconnecting...")

        try:
            adb_info = self.client.get_adb_info(self.phone_id)
            password = adb_info['pwd']
        except Exception as e:
            print(f"  [ADB RECONNECT] Failed to get ADB info: {e}")
            return False

        subprocess.run([ADB_PATH, "disconnect", self.device], capture_output=True)
        time.sleep(1)

        connect_result = subprocess.run(
            [ADB_PATH, "connect", self.device],
            capture_output=True, encoding='utf-8'
        )
        print(f"  [ADB RECONNECT] adb connect: {connect_result.stdout.strip()}")

        for attempt in range(10):
            time.sleep(2)
            if self.verify_adb_connection():
                print(f"  [ADB RECONNECT] Device ready after {attempt + 1} attempts")
                login_result = self.adb_command(f"glogin {password}")
                print(f"  [ADB RECONNECT] glogin: {login_result}")
                return True
            print(f"  [ADB RECONNECT] Waiting... ({attempt + 1}/10)")

        print(f"  [ADB RECONNECT] Failed to reconnect after 10 attempts")
        return False

    def connect_appium(self, retries: int = 3) -> bool:
        """Connect Appium driver.

        Args:
            retries: Number of connection attempts.

        Returns:
            True on success.

        Raises:
            Exception: If all retries fail.
        """
        print(f"Connecting Appium driver to {self.appium_url}...")

        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.automation_name = "UiAutomator2"
        options.device_name = self.device
        options.udid = self.device
        options.no_reset = True
        options.new_command_timeout = 120
        options.set_capability("appium:adbExecTimeout", 120000)
        options.set_capability("appium:uiautomator2ServerInstallTimeout", 120000)
        options.set_capability("appium:uiautomator2ServerLaunchTimeout", 10000)
        options.set_capability("appium:androidDeviceReadyTimeout", 60)
        options.set_capability("appium:systemPort", self.system_port)

        last_error = None
        for attempt in range(retries):
            # Verify ADB connection before each attempt
            if not self.verify_adb_connection():
                print(f"  [ATTEMPT {attempt + 1}] ADB connection lost, attempting to reconnect...")
                if not self.reconnect_adb():
                    print(f"  [ATTEMPT {attempt + 1}] ADB reconnect failed, skipping Appium attempt")
                    last_error = Exception("ADB connection lost and reconnect failed")
                    if attempt < retries - 1:
                        time.sleep(2)
                    continue
                print(f"  [ATTEMPT {attempt + 1}] ADB reconnected, proceeding with Appium")

            try:
                self.appium_driver = webdriver.Remote(
                    command_executor=self.appium_url,
                    options=options
                )

                platform_ver = self.appium_driver.capabilities.get('platformVersion', 'unknown')
                print(f"  Appium connected! (Android {platform_ver})")
                return True
            except Exception as e:
                last_error = e
                print(f"  Appium connection failed (attempt {attempt + 1}/{retries}): {e}")
                self.appium_driver = None
                if attempt < retries - 1:
                    print(f"  Retrying in 2 seconds...")
                    time.sleep(2)

        raise Exception(f"Appium connection failed after {retries} attempts: {last_error}")

    def reconnect_appium(self) -> bool:
        """Reconnect Appium driver after UiAutomator2 crash."""
        print("  [RECOVERY] Reconnecting Appium driver...")
        try:
            if self.appium_driver:
                self.appium_driver.quit()
        except Exception:
            pass  # Ignore errors when quitting - driver may already be dead
        self.appium_driver = None
        time.sleep(2)
        return self.connect_appium()

    def connect(self) -> bool:
        """Full connection flow: find phone, start, enable ADB, connect Appium.

        Returns:
            True on success.

        Raises:
            Exception: On connection failure.
        """
        phone = self.find_phone()
        self.phone_id = phone["id"]

        self.start_phone_if_needed(phone)

        adb_info = self.enable_adb_with_retry()

        self.connect_adb(adb_info)

        self.connect_appium()

        return True

    def disconnect(self) -> None:
        """Disconnect and cleanup."""
        try:
            if self.appium_driver:
                self.appium_driver.quit()
                print("  Appium driver closed")
        except Exception:
            pass  # Ignore errors - cleanup should not fail

        try:
            self.client.disable_adb(self.phone_id)
        except Exception:
            pass  # Ignore errors - ADB may already be disabled

        try:
            self.client.stop_phone(self.phone_id)
            print("  Phone stopped (saving billing minutes)")
        except Exception as e:
            print(f"  Warning: Could not stop phone: {e}")

    def is_uiautomator2_crash(self, exception: Exception) -> bool:
        """Check if exception indicates UiAutomator2 crashed on device."""
        error_msg = str(exception).lower()
        return any(indicator in error_msg for indicator in [
            'instrumentation process is not running',
            'uiautomator2 server',
            'cannot be proxied',
            'probably crashed',
        ])

    # =========================================================================
    # DeviceManager Interface Implementation
    # =========================================================================

    @property
    def device_type(self) -> str:
        """Return device type identifier."""
        return "geelark"

    def ensure_connected(self, account_name: str) -> bool:
        """
        Ensure Geelark device is connected and ready.

        This performs the full Geelark connection flow:
        1. Find phone by name in Geelark
        2. Start phone if not running
        3. Enable ADB with retry logic
        4. Connect ADB and authenticate

        Args:
            account_name: The account name (same as phone_name for Geelark)

        Returns:
            True if device is ready

        Raises:
            Exception: If connection fails
        """
        # For Geelark, phone_name IS the account identifier
        # (each phone = one account)
        phone = self.find_phone()
        self.phone_id = phone["id"]

        self.start_phone_if_needed(phone)

        adb_info = self.enable_adb_with_retry()

        self.connect_adb(adb_info)

        return True

    def get_adb_address(self) -> str:
        """
        Get ADB connection address for Appium.

        Returns:
            ADB address in "ip:port" format
        """
        if not self.device:
            raise Exception("Device not connected - call ensure_connected() first")
        return self.device

    def upload_video(self, local_path: str) -> str:
        """
        Upload video to Geelark cloud phone.

        Uses Geelark's file upload API to transfer video to device.

        Args:
            local_path: Local path to video file

        Returns:
            Remote path on device where video was uploaded

        Raises:
            Exception: If upload fails
        """
        import os
        if not os.path.exists(local_path):
            raise Exception(f"Video file not found: {local_path}")

        if not self.phone_id:
            raise Exception("Phone ID not set - call ensure_connected() first")

        # Step 1: Upload local file to Geelark cloud CDN
        resource_url = self.client.upload_file_to_geelark(local_path)

        # Step 2: Upload from cloud CDN to phone's Downloads folder
        upload_result = self.client.upload_file_to_phone(self.phone_id, resource_url)
        task_id = upload_result.get("taskId")

        # Step 3: Wait for upload to complete
        self.client.wait_for_upload(task_id)

        # Construct remote path (Geelark uploads to /sdcard/Download/)
        filename = os.path.basename(local_path)
        return f"/sdcard/Download/{filename}"

    def get_appium_caps(self) -> Dict:
        """
        Get Appium desired capabilities for Geelark device.

        Returns:
            Dictionary of Appium capabilities
        """
        return {
            'platformName': 'Android',
            'automationName': 'UiAutomator2',
            'deviceName': self.phone_name,
            'udid': self.device or f"pending:{self.phone_name}",
            'noReset': True,
            'newCommandTimeout': 120,
            'systemPort': self.system_port,
        }

    def cleanup(self) -> None:
        """
        Cleanup Geelark device after posting.

        Stops the cloud phone to save billing minutes.
        """
        self.disconnect()
