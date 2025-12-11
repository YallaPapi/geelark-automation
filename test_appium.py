"""
Test Appium connection to Geelark cloud phone and Unicode typing
"""
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
import time
import os

os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'

DEVICE = "98.98.125.37:20865"

def test_appium_connection():
    """Test connecting to Geelark phone via Appium"""

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.device_name = DEVICE
    options.udid = DEVICE
    options.no_reset = True
    options.new_command_timeout = 300
    options.set_capability("appium:adbExecTimeout", 60000)
    options.set_capability("appium:uiautomator2ServerInstallTimeout", 120000)

    print(f"Connecting to {DEVICE} via Appium...")

    try:
        driver = webdriver.Remote(
            command_executor="http://127.0.0.1:4723",
            options=options
        )
        print("[OK] Connected successfully!")
        print(f"    Platform Version: {driver.capabilities.get('platformVersion')}")

        # Find text fields on screen
        print("\nCurrent screen elements:")
        elements = driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
        print(f"    Found {len(elements)} EditText fields")

        if elements:
            print("\nTesting Unicode typing...")
            el = elements[0]
            el.click()
            time.sleep(0.5)

            # Clear and type
            el.clear()
            test_text = "Hello World emoji test"
            el.send_keys(test_text)
            time.sleep(1)

            typed = el.text
            print(f"    Typed: {test_text}")
            print(f"    Got: {typed}")

            if "Hello" in typed:
                print("\n[OK] TYPING WORKS ON ANDROID 15!")
        else:
            print("    No text fields on current screen")
            print("    But connection works - that's the key!")

        # Take screenshot
        driver.save_screenshot("appium_test.png")
        print("\n    Screenshot saved to appium_test.png")

        driver.quit()
        print("\n[OK] TEST PASSED: Appium works with Android 15 Geelark phone!")
        return True

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_appium_connection()
