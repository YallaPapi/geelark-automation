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

from phone_connector import PhoneConnector, adb_shell, adb_install

APK_PATH = os.path.join(os.path.dirname(__file__), "ADBKeyboard.apk")


def setup_phone(phone_name):
    """Setup ADBKeyboard on a single phone"""
    print(f"\n{'='*50}")
    print(f"Setting up ADBKeyboard on: {phone_name}")
    print('='*50)

    # Use shared PhoneConnector for find → start → ADB connect
    connector = PhoneConnector()
    try:
        client, phone_id, device, password = connector.setup_for_adb(phone_name)
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

    # Force uninstall first (clean slate)
    print("  Uninstalling existing ADBKeyboard (if any)...")
    uninstall_result = adb_shell(device, "pm uninstall com.android.adbkeyboard")
    print(f"    {uninstall_result or 'Not installed'}")

    # Install fresh APK
    print(f"  Installing ADBKeyboard.apk (fresh)...")
    install_result = adb_install(device, APK_PATH)
    print(f"    {install_result}")
    if "Success" not in install_result:
        print("  ERROR: Installation failed")
        return False

    # Enable ADBKeyboard as an input method
    print("  Enabling ADBKeyboard input method...")
    adb_shell(device, "ime enable com.android.adbkeyboard/.AdbIME")

    # Set as default input method
    print("  Setting ADBKeyboard as default...")
    adb_shell(device, "ime set com.android.adbkeyboard/.AdbIME")

    # Verify
    print("  Verifying...")
    current_ime = adb_shell(device, "settings get secure default_input_method")
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
