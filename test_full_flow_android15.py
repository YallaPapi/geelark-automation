"""Test full Instagram posting flow on Android 15 with Appium"""
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
import xml.etree.ElementTree as ET
import re
import time

DEVICE = "98.98.125.37:21293"  # Android 15

def dump_ui(driver):
    """Parse page_source into elements"""
    elements = []
    xml_str = driver.page_source

    if '<?xml' not in xml_str:
        return elements

    xml_clean = xml_str[xml_str.find('<?xml'):]
    root = ET.fromstring(xml_clean)

    for elem in root.iter():
        text = elem.get('text', '')
        desc = elem.get('content-desc', '')
        res_id = elem.get('resource-id', '')
        bounds = elem.get('bounds', '')
        clickable = elem.get('clickable', 'false')

        if bounds and (text or desc or clickable == 'true'):
            m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
            if m:
                x1, y1, x2, y2 = map(int, m.groups())
                cx, cy = (x1+x2)//2, (y1+y2)//2
                elements.append({
                    'text': text,
                    'desc': desc,
                    'id': res_id.split('/')[-1] if '/' in res_id else res_id,
                    'bounds': bounds,
                    'center': (cx, cy),
                    'clickable': clickable == 'true'
                })
    return elements

print(f"Connecting Appium to {DEVICE}...")
options = UiAutomator2Options()
options.platform_name = "Android"
options.automation_name = "UiAutomator2"
options.device_name = DEVICE
options.udid = DEVICE
options.no_reset = True
options.new_command_timeout = 300

driver = webdriver.Remote(command_executor="http://127.0.0.1:4723", options=options)
print(f"Connected! Android {driver.capabilities.get('platformVersion')}")

# Open Instagram
print("\nOpening Instagram...")
driver.press_keycode(3)  # HOME
time.sleep(1)

# Start Instagram via am start (using Appium's executeScript)
# Note: This requires adb_shell to be enabled, fallback to regular ADB
import subprocess
ADB = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
subprocess.run([ADB, "-s", DEVICE, "shell", "am", "force-stop", "com.instagram.android"])
time.sleep(1)
subprocess.run([ADB, "-s", DEVICE, "shell", "monkey", "-p", "com.instagram.android", "1"])
time.sleep(5)

# Dump UI
print("\nDumping UI...")
for step in range(5):
    elements = dump_ui(driver)
    print(f"\nStep {step+1}: Found {len(elements)} elements")

    if elements:
        print("Some elements:")
        for elem in elements[:8]:
            parts = []
            if elem['text']:
                parts.append(f"'{elem['text'][:30]}'")
            if elem['desc']:
                parts.append(f"desc='{elem['desc'][:30]}'")
            if parts:
                print(f"  {elem['bounds']} {' | '.join(parts)}")

        # Look for Create button
        create = [e for e in elements if 'create' in (e['text'] + e['desc']).lower()]
        if create:
            print(f"\n[FOUND] Create button at {create[0]['center']}")
            driver.tap([create[0]['center']])
            time.sleep(2)
    else:
        print("  No elements, waiting...")
        time.sleep(2)

driver.save_screenshot("android15_test.png")
print("\nScreenshot saved to android15_test.png")

driver.quit()
print("\n[OK] Test complete!")
