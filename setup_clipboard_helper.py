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
import base64

from phone_connector import PhoneConnector, adb_shell, adb_install

APK_PATH = os.path.join(os.path.dirname(__file__), "ClipboardHelper.apk")


def setup_phone(phone_name):
    """Setup ClipboardHelper on a single phone"""
    print(f"\n{'='*50}")
    print(f"Setting up ClipboardHelper on: {phone_name}")
    print('='*50)

    # Use shared PhoneConnector for find → start → ADB connect
    connector = PhoneConnector()
    try:
        client, phone_id, device, password = connector.setup_for_adb(phone_name)
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

    # Check if already installed
    print("  Checking if ClipboardHelper is installed...")
    packages = adb_shell(device, "pm list packages | grep geelark.clipboard")
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
    test_text = "ClipboardHelper OK\nSecond line test"
    text_b64 = base64.b64encode(test_text.encode('utf-8')).decode('ascii')
    result = adb_shell(
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
