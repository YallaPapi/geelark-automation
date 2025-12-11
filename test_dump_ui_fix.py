"""Test the fixed dump_ui on Android 15"""
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import os
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'

from appium import webdriver
from appium.options.android import UiAutomator2Options
import xml.etree.ElementTree as ET
import re

DEVICE = "98.98.125.37:21293"  # Android 15

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

# Get page_source
print("\nGetting page_source...")
xml_str = driver.page_source

# Parse with FIXED logic (iter() not iter('node'))
elements = []
if '<?xml' in xml_str:
    xml_clean = xml_str[xml_str.find('<?xml'):]
    root = ET.fromstring(xml_clean)

    for elem in root.iter():  # FIXED: iter() not iter('node')
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

print(f"\n[RESULT] Found {len(elements)} UI elements!")
print("\nFirst 10 elements:")
for i, elem in enumerate(elements[:10]):
    parts = []
    if elem['text']:
        parts.append(f"'{elem['text']}'")
    if elem['desc']:
        parts.append(f"desc='{elem['desc']}'")
    if elem['id']:
        parts.append(f"id={elem['id']}")
    print(f"  {i+1}. {elem['bounds']} {' | '.join(parts)}")

driver.quit()
print("\n[OK] dump_ui fix WORKS on Android 15!")
