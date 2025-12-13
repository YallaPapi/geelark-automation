"""
Test script to verify text input methods work on Geelark phones.
Tests ClipboardHelper + paste, and ADBKeyboard broadcast.
"""
import sys
import os
import time
import subprocess
import base64

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from geelark_client import GeelarkClient
from config import Config

ADB_PATH = Config.ADB_PATH


def adb(device, cmd, timeout=30):
    """Run ADB shell command"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "shell", cmd],
        capture_output=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""


def connect_phone(phone_name):
    """Connect to a Geelark phone and return device string"""
    client = GeelarkClient()

    print(f"Finding phone: {phone_name}")
    phone = None
    for page in range(1, 10):
        result = client.list_phones(page=page, page_size=100)
        for p in result["items"]:
            if p["serialName"] == phone_name:
                phone = p
                break
        if phone:
            break

    if not phone:
        raise Exception(f"Phone not found: {phone_name}")

    phone_id = phone["id"]
    print(f"Found: {phone['serialName']} (Status: {phone['status']})")

    # Start if needed
    if phone["status"] != 0:
        print("Starting phone...")
        client.start_phone(phone_id)
        for i in range(60):
            time.sleep(2)
            status = client.get_phone_status([phone_id])
            items = status.get("successDetails", [])
            if items and items[0].get("status") == 0:
                break
        time.sleep(5)

    # Enable ADB
    print("Enabling ADB...")
    client.enable_adb(phone_id)
    time.sleep(5)

    # Get ADB info
    adb_info = client.get_adb_info(phone_id)
    device = f"{adb_info['ip']}:{adb_info['port']}"
    password = adb_info['pwd']

    # Connect
    print(f"Connecting to {device}...")
    subprocess.run([ADB_PATH, "connect", device], capture_output=True)

    # Login
    login_result = adb(device, f"glogin {password}")
    print(f"Login: {login_result or 'OK'}")

    return device, client, phone_id


def test_clipboard_helper(device, test_text):
    """Test ClipboardHelper APK"""
    print(f"\n{'='*50}")
    print("TEST 1: ClipboardHelper APK")
    print('='*50)

    # Check if installed
    result = adb(device, "pm path com.geelark.clipboard")
    if "package:" in result:
        print(f"  ClipboardHelper installed: {result}")
    else:
        print("  ERROR: ClipboardHelper NOT installed!")
        return False

    # Set clipboard
    text_b64 = base64.b64encode(test_text.encode('utf-8')).decode('ascii')
    print(f"  Setting clipboard with base64 text...")
    result = adb(device, f"am start -n com.geelark.clipboard/.ClipboardActivity -a com.geelark.clipboard.COPY --es base64 {text_b64}")
    print(f"  Result: {result[:100] if result else 'Activity started'}")
    time.sleep(1)

    return True


def test_adbkeyboard(device, test_text):
    """Test ADBKeyboard broadcast"""
    print(f"\n{'='*50}")
    print("TEST 2: ADBKeyboard Broadcast")
    print('='*50)

    # Check if installed
    result = adb(device, "pm path com.android.adbkeyboard")
    if "package:" in result:
        print(f"  ADBKeyboard installed: {result}")
    else:
        print("  ERROR: ADBKeyboard NOT installed!")
        return False

    # Check current IME
    current_ime = adb(device, "settings get secure default_input_method")
    print(f"  Current IME: {current_ime}")

    if "adbkeyboard" not in current_ime.lower():
        print("  WARNING: ADBKeyboard is not the default IME!")
        print("  Setting ADBKeyboard as default...")
        adb(device, "settings put secure default_input_method com.android.adbkeyboard/.AdbIME")
        time.sleep(0.5)
        current_ime = adb(device, "settings get secure default_input_method")
        print(f"  New IME: {current_ime}")

    # Send text via broadcast
    text_b64 = base64.b64encode(test_text.encode('utf-8')).decode('ascii')
    print(f"  Sending text via ADB_INPUT_B64 broadcast...")
    result = adb(device, f"am broadcast -a ADB_INPUT_B64 --es msg {text_b64}")
    print(f"  Result: {result[:100] if result else 'Broadcast sent'}")

    return True


def test_in_notes_app(device, test_text):
    """Open a notes app and try to type"""
    print(f"\n{'='*50}")
    print("TEST 3: Actual Typing in Notes App")
    print('='*50)

    # Try to open a simple text input - use Google Keep or default notes
    print("  Opening Google search (has text field)...")
    adb(device, "am start -a android.intent.action.VIEW -d 'https://www.google.com'")
    time.sleep(5)

    # Tap in search area (approximate center-top)
    print("  Tapping search field...")
    adb(device, "input tap 360 200")
    time.sleep(2)

    # Check if keyboard is visible
    result = adb(device, "dumpsys input_method | grep mInputShown")
    print(f"  Keyboard status: {result}")

    # Method 1: Try ADBKeyboard broadcast
    print("\n  Attempting ADBKeyboard broadcast...")
    text_b64 = base64.b64encode(test_text.encode('utf-8')).decode('ascii')
    adb(device, f"am broadcast -a ADB_INPUT_B64 --es msg {text_b64}")
    time.sleep(1)

    print("  Check the phone screen - did text appear in the search field?")

    return True


def test_long_press_paste(device, test_text):
    """Test long-press paste method"""
    print(f"\n{'='*50}")
    print("TEST 4: Long-Press Paste Method")
    print('='*50)

    # First set clipboard
    text_b64 = base64.b64encode(test_text.encode('utf-8')).decode('ascii')
    print("  Setting clipboard via ClipboardHelper...")
    adb(device, f"am start -n com.geelark.clipboard/.ClipboardActivity -a com.geelark.clipboard.COPY --es base64 {text_b64}")
    time.sleep(1)

    # Open a text field (Google search)
    print("  Opening Google for text field...")
    adb(device, "am start -a android.intent.action.VIEW -d 'https://www.google.com'")
    time.sleep(5)

    # Tap search field
    print("  Tapping search field...")
    adb(device, "input tap 360 200")
    time.sleep(1)

    # Long press to show paste menu
    print("  Long-pressing to show paste menu...")
    adb(device, "input swipe 360 200 360 200 800")
    time.sleep(1)

    # Look for paste button in UI
    print("  Checking for paste menu...")
    adb(device, "uiautomator dump /sdcard/ui.xml")
    xml = adb(device, "cat /sdcard/ui.xml")

    if "paste" in xml.lower():
        print("  FOUND 'paste' in UI - attempting to tap it...")
        # Try to find and tap paste
        # This is a rough tap at where paste usually appears
        adb(device, "input tap 360 150")
        time.sleep(1)
        print("  Check phone - did text paste?")
        return True
    else:
        print("  No 'paste' option found in UI")
        print("  UI contains:", xml[:500] if xml else "empty")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_typing.py <phone_name>")
        print("Example: python test_typing.py miccliparchive")
        sys.exit(1)

    phone_name = sys.argv[1]
    test_text = "Test 123 with emoji 🎉 and newline\nSecond line!"

    try:
        device, client, phone_id = connect_phone(phone_name)

        print(f"\nTest text: {test_text}")
        print("="*50)

        # Run tests
        test_clipboard_helper(device, test_text)
        test_adbkeyboard(device, test_text)
        test_in_notes_app(device, "Hello from ADBKeyboard!")
        test_long_press_paste(device, test_text)

        print(f"\n{'='*50}")
        print("TESTS COMPLETE")
        print("="*50)
        print("\nPlease check the phone screen to see which methods worked.")
        print("Look for the test text in any text fields.")

        # Cleanup
        print("\nDisabling ADB...")
        client.disable_adb(phone_id)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
