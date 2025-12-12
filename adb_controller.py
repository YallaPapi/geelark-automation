"""
ADB Controller - connects to Geelark devices and runs commands
"""
import subprocess
import time
import os

# ADB executable path
ADB_PATH = r"C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe"


class ADBController:
    def __init__(self, ip, port, password):
        self.ip = ip
        self.port = port
        self.password = password
        self.device = f"{ip}:{port}"
        self.connected = False

    def connect(self, retries=3):
        """Connect to device via ADB"""
        for attempt in range(retries):
            try:
                # Disconnect first to clean state
                subprocess.run(
                    [ADB_PATH, "disconnect", self.device],
                    capture_output=True, timeout=5
                )

                # Connect with password
                # Geelark uses adb connect with auth
                result = subprocess.run(
                    [ADB_PATH, "connect", self.device],
                    capture_output=True, text=True, timeout=10
                )

                if "connected" in result.stdout.lower():
                    self.connected = True
                    print(f"Connected to {self.device}")
                    # Geelark requires glogin with password
                    login_result = subprocess.run(
                        [ADB_PATH, "-s", self.device, "shell", f"glogin {self.password}"],
                        capture_output=True, text=True, timeout=10
                    )
                    if "success" in login_result.stdout.lower():
                        print("Geelark login successful")
                    else:
                        print(f"Geelark login: {login_result.stdout}")
                    return True

                # May need to pair first
                if "authenticate" in result.stdout.lower() or "pair" in result.stdout.lower():
                    # Try pairing
                    pair_result = subprocess.run(
                        [ADB_PATH, "pair", self.device, self.password],
                        capture_output=True, text=True, timeout=10
                    )
                    print(f"Pair result: {pair_result.stdout}")

                    # Try connect again
                    result = subprocess.run(
                        [ADB_PATH, "connect", self.device],
                        capture_output=True, text=True, timeout=10
                    )

                    if "connected" in result.stdout.lower():
                        self.connected = True
                        print(f"Connected to {self.device}")
                        return True

                print(f"Connect attempt {attempt + 1} failed: {result.stdout} {result.stderr}")
                time.sleep(2)

            except subprocess.TimeoutExpired:
                print(f"Connect attempt {attempt + 1} timed out")
                time.sleep(2)

        return False

    def disconnect(self):
        """Disconnect from device"""
        subprocess.run([ADB_PATH, "disconnect", self.device], capture_output=True)
        self.connected = False

    def shell(self, command, timeout=30):
        """Run shell command on device"""
        if not self.connected:
            raise Exception("Not connected to device")

        result = subprocess.run(
            [ADB_PATH, "-s", self.device, "shell", command],
            capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()

    def tap(self, x, y):
        """Tap at coordinates"""
        return self.shell(f"input tap {x} {y}")

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        """Swipe from (x1,y1) to (x2,y2)"""
        return self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    def type_text(self, text):
        """Type text (spaces become %s)"""
        # Escape special characters for shell
        escaped = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        return self.shell(f"input text '{escaped}'")

    def key_event(self, keycode):
        """Send key event (e.g., KEYCODE_BACK=4, KEYCODE_HOME=3)"""
        return self.shell(f"input keyevent {keycode}")

    def back(self):
        """Press back button"""
        return self.key_event(4)

    def home(self):
        """Press home button"""
        return self.key_event(3)

    def screenshot_to_file(self, local_path):
        """Take screenshot and pull to local file"""
        remote_path = "/sdcard/screenshot.png"

        # Take screenshot
        self.shell(f"screencap -p {remote_path}")

        # Pull to local
        result = subprocess.run(
            [ADB_PATH, "-s", self.device, "pull", remote_path, local_path],
            capture_output=True, text=True, timeout=30
        )

        # Clean up remote
        self.shell(f"rm {remote_path}")

        return os.path.exists(local_path)

    def push_file(self, local_path, remote_path):
        """Push file to device"""
        result = subprocess.run(
            [ADB_PATH, "-s", self.device, "push", local_path, remote_path],
            capture_output=True, text=True, timeout=300
        )
        print(f"Push stdout: {result.stdout}")
        print(f"Push stderr: {result.stderr}")
        print(f"Push returncode: {result.returncode}")
        return "pushed" in result.stdout.lower() or result.returncode == 0

    def launch_app(self, package_name):
        """Launch an app by package name"""
        return self.shell(
            f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1"
        )

    def launch_instagram(self):
        """Launch Instagram"""
        return self.launch_app("com.instagram.android")

    def get_current_activity(self):
        """Get current foreground activity"""
        result = self.shell("dumpsys activity activities | grep mResumedActivity")
        return result


if __name__ == "__main__":
    # Test with dummy values
    print("ADB Controller module loaded successfully")
    print("Usage: adb = ADBController(ip, port, password)")
    print("       adb.connect()")
    print("       adb.tap(500, 500)")
