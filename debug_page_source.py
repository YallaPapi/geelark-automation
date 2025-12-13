"""Debug: Compare Appium page_source vs uiautomator dump XML format"""
import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from config import Config, setup_environment
setup_environment()

from appium import webdriver
from appium.options.android import UiAutomator2Options
import subprocess

ADB_PATH = Config.ADB_PATH

# Use a device that's already connected
result = subprocess.run([ADB_PATH, "devices"], capture_output=True, encoding='utf-8')
print("Connected devices:")
print(result.stdout)

# Pick first online device
lines = result.stdout.strip().split('\n')[1:]
device = None
for line in lines:
    if '\tdevice' in line:
        device = line.split('\t')[0]
        break

if not device:
    print("No device found!")
    sys.exit(1)

print(f"\nUsing device: {device}")

# Check Android version
sdk = subprocess.run([ADB_PATH, "-s", device, "shell", "getprop ro.build.version.sdk"],
                     capture_output=True, encoding='utf-8').stdout.strip()
print(f"Android SDK: {sdk}")

# Connect Appium
print("\nConnecting Appium...")
options = UiAutomator2Options()
options.platform_name = "Android"
options.automation_name = "UiAutomator2"
options.device_name = device
options.udid = device
options.no_reset = True
options.new_command_timeout = 300

driver = webdriver.Remote(command_executor="http://127.0.0.1:4723", options=options)
print("Appium connected!")

# Get page_source
print("\n" + "="*60)
print("APPIUM PAGE_SOURCE (first 2000 chars):")
print("="*60)
ps = driver.page_source
print(ps[:2000] if ps else "EMPTY!")
print(f"\nTotal length: {len(ps) if ps else 0}")

# Check if it has <?xml and node elements
print("\n" + "="*60)
print("FORMAT CHECK:")
print("="*60)
print(f"Has <?xml: {'<?xml' in ps}")
print(f"Has <node: {'<node' in ps}")
print(f"Has <hierarchy: {'<hierarchy' in ps}")
print(f"Has bounds=: {'bounds=' in ps}")

# Save full output for inspection
with open("page_source_debug.xml", "w", encoding="utf-8") as f:
    f.write(ps)
print("\nFull page_source saved to page_source_debug.xml")

driver.quit()
print("\nDone!")
