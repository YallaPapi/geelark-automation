"""
Install and enable ADBKeyboard on Geelark cloud phones.
This keyboard allows typing special characters via ADB.

Usage:
    python setup_adbkeyboard.py <phone1> <phone2> ...

Example:
    python setup_adbkeyboard.py miccliparchive reelwisdompod_ podmindstudio
"""
import sys
import os
import time
import subprocess
from geelark_client import GeelarkClient
from config import Config

ADB_PATH = Config.ADB_PATH
APK_PATH = os.path.join(os.path.dirname(__file__), "ADBKeyboard.apk")


def adb(device, cmd, timeout=30):
    """Run ADB shell command"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "shell", cmd],
        capture_output=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""


def adb_install(device, apk_path):
    """Install APK via ADB"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "install", "-r", apk_path],
        capture_output=True, timeout=120,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""


def setup_phone(phone_name):
    """Setup ADBKeyboard on a single phone"""
    client = GeelarkClient()

    print(f"\n{'='*50}")
    print(f"Setting up ADBKeyboard on: {phone_name}")
    print('='*50)

    # Find phone
    print("Finding phone...")
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
        print(f"  ERROR: Phone not found: {phone_name}")
        return False

    phone_id = phone["id"]
    print(f"  Found: {phone['serialName']} (Status: {phone['status']})")

    # Start phone if needed
    if phone["status"] != 0:
        print("  Starting phone...")
        client.start_phone(phone_id)
        for i in range(60):
            time.sleep(2)
            status = client.get_phone_status([phone_id])
            items = status.get("successDetails", [])
            if items and items[0].get("status") == 0:
                print(f"    Ready after {(i+1)*2}s")
                break
        time.sleep(5)

    # Enable ADB
    print("  Enabling ADB...")
    client.enable_adb(phone_id)
    time.sleep(5)

    # Get ADB info
    adb_info = client.get_adb_info(phone_id)
    device = f"{adb_info['ip']}:{adb_info['port']}"
    password = adb_info['pwd']

    # Connect
    print(f"  Connecting to {device}...")
    subprocess.run([ADB_PATH, "connect", device], capture_output=True)
    time.sleep(1)

    # Login
    login_result = adb(device, f"glogin {password}")
    print(f"  Login: {login_result or 'OK'}")

    # Force uninstall first (clean slate)
    print("  Uninstalling existing ADBKeyboard (if any)...")
    uninstall_result = adb(device, "pm uninstall com.android.adbkeyboard")
    print(f"    {uninstall_result or 'Not installed'}")
    time.sleep(1)

    # Install fresh APK
    print(f"  Installing ADBKeyboard.apk (fresh)...")
    install_result = adb_install(device, APK_PATH)
    print(f"    {install_result}")
    if "Success" not in install_result:
        print("  ERROR: Installation failed")
        return False

    # Enable ADBKeyboard as an input method
    print("  Enabling ADBKeyboard input method...")
    adb(device, "ime enable com.android.adbkeyboard/.AdbIME")

    # Set as default input method
    print("  Setting ADBKeyboard as default...")
    adb(device, "ime set com.android.adbkeyboard/.AdbIME")

    # Verify
    print("  Verifying...")
    current_ime = adb(device, "settings get secure default_input_method")
    if "adbkeyboard" in current_ime.lower():
        print(f"  SUCCESS: ADBKeyboard is now the default keyboard")
        return True
    else:
        print(f"  WARNING: Current IME is: {current_ime}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_adbkeyboard.py <phone1> <phone2> ...")
        print("Example: python setup_adbkeyboard.py miccliparchive reelwisdompod_ podmindstudio")
        sys.exit(1)

    if not os.path.exists(APK_PATH):
        print(f"ERROR: ADBKeyboard.apk not found at {APK_PATH}")
        sys.exit(1)

    phones = sys.argv[1:]
    results = {}

    for phone in phones:
        try:
            results[phone] = setup_phone(phone)
        except Exception as e:
            print(f"  ERROR: {e}")
            results[phone] = False

    # Summary
    print("\n" + "="*50)
    print("SETUP COMPLETE")
    print("="*50)
    for phone, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"  {phone}: {status}")


if __name__ == "__main__":
    main()
