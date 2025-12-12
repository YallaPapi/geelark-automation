"""
Install ClipboardHelper APK on Geelark cloud phones.
This app enables clipboard access via ADB for typing Unicode text, emojis, and newlines.

Usage:
    python setup_clipboard_helper.py <phone1> <phone2> ...

Example:
    python setup_clipboard_helper.py miccliparchive reelwisdompod_ podmindstudio
"""
import sys
import os
import time
import subprocess
from geelark_client import GeelarkClient

ADB_PATH = r"C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe"
APK_PATH = os.path.join(os.path.dirname(__file__), "ClipboardHelper.apk")


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
    """Setup ClipboardHelper on a single phone"""
    client = GeelarkClient()

    print(f"\n{'='*50}")
    print(f"Setting up ClipboardHelper on: {phone_name}")
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

    # Check if already installed
    print("  Checking if ClipboardHelper is installed...")
    packages = adb(device, "pm list packages | grep geelark.clipboard")
    if "com.geelark.clipboard" in packages:
        print("  ClipboardHelper already installed!")
    else:
        # Install APK
        print(f"  Installing ClipboardHelper.apk...")
        install_result = adb_install(device, APK_PATH)
        print(f"    {install_result}")
        if "Success" not in install_result:
            print("  ERROR: Installation failed")
            return False

    # Test clipboard functionality (basic smoke test)
    print("  Testing clipboard...")
    import base64
    test_text = "ClipboardHelper OK\nSecond line test"
    text_b64 = base64.b64encode(test_text.encode('utf-8')).decode('ascii')
    result = adb(
        device,
        f"am start -n com.geelark.clipboard/.CopyActivity -a com.geelark.clipboard.COPY --es base64 {text_b64}"
    )
    if "Error" in result or "Exception" in result:
        print(f"  WARNING: ClipboardHelper test may have failed: {result}")
    else:
        print("  SUCCESS: ClipboardHelper activity invoked (clipboard should be set)")

    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python setup_clipboard_helper.py <phone1> <phone2> ...")
        print("Example: python setup_clipboard_helper.py miccliparchive reelwisdompod_ podmindstudio")
        sys.exit(1)

    if not os.path.exists(APK_PATH):
        print(f"ERROR: ClipboardHelper.apk not found at {APK_PATH}")
        print("Run the build script first: ClipboardHelper/build.ps1")
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
