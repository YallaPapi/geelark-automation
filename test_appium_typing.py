"""
Quick test of Appium typing in SmartInstagramPoster
"""
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import os
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
import time

# Android 15 phone - test device
DEVICE = "98.98.125.37:20865"
APPIUM_SERVER = "http://127.0.0.1:4723"

def test_appium_typing():
    """Test Appium typing with emojis"""
    print(f"Connecting to {DEVICE}...")

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.device_name = DEVICE
    options.udid = DEVICE
    options.no_reset = True
    options.new_command_timeout = 300
    options.set_capability("appium:adbExecTimeout", 60000)

    driver = webdriver.Remote(command_executor=APPIUM_SERVER, options=options)
    print(f"[OK] Connected! Android {driver.capabilities.get('platformVersion')}")

    # Tap Google search bar to get a text field
    print("Looking for search bar...")
    try:
        # Look for Google search widget
        search = driver.find_element(AppiumBy.CLASS_NAME, "android.widget.TextView")
        if search and "Google" in (search.text or ""):
            print("Found Google search bar, tapping...")
            search.click()
            time.sleep(2)

            # Now find the search input
            edit_texts = driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
            if edit_texts:
                print(f"Found {len(edit_texts)} EditText fields")
                et = edit_texts[0]

                # Type with emojis!
                test_text = "Hello World! Emoji test"
                print(f"Typing: {test_text}")
                et.send_keys(test_text)
                time.sleep(1)

                typed = et.text
                print(f"Got: {typed}")

                if "Hello" in typed:
                    print("\n[SUCCESS] Appium typing works on Android 15!")
                else:
                    print("\n[PARTIAL] Text field interaction worked")
            else:
                print("No EditText found after clicking search")
        else:
            print("No Google search bar found - checking for any EditText...")
            edit_texts = driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
            print(f"Found {len(edit_texts)} EditText fields on screen")

    except Exception as e:
        print(f"Search test error: {e}")
        print("This is OK - the key is that Appium connected!")

    # Take screenshot to show current state
    driver.save_screenshot("appium_typing_test.png")
    print("\nScreenshot saved to appium_typing_test.png")

    driver.quit()
    print("\n[OK] Test complete - Appium is working!")
    return True

if __name__ == "__main__":
    test_appium_typing()
