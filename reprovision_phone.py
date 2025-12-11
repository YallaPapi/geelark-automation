"""
Reprovision Geelark phones using "One-click New Device" API.
This resets the phone completely and reinstalls ADBKeyboard as a system app.

WARNING: This will WIPE ALL DATA on the phone including:
- Installed apps
- Logged-in accounts (Instagram, etc.)
- All files and settings

Usage:
    python reprovision_phone.py <phone_name>

Example:
    python reprovision_phone.py reelwisdompod_
"""
import sys
import time
import subprocess
from geelark_client import GeelarkClient

ADB_PATH = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"


def adb(device, cmd, timeout=30):
    """Run ADB shell command"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "shell", cmd],
        capture_output=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""


def check_adbkeyboard(device):
    """Check if ADBKeyboard is properly installed"""
    pm_path = adb(device, "pm path com.android.adbkeyboard")
    return bool(pm_path)


def reprovision_phone(phone_name, confirm=True):
    """Reprovision a phone using Geelark one-click new device API"""
    client = GeelarkClient()

    print(f"\n{'='*60}")
    print(f"REPROVISIONING: {phone_name}")
    print('='*60)

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
    print(f"  Found: {phone['serialName']} (ID: {phone_id})")
    print(f"  Current status: {phone['status']}")

    # Confirm
    if confirm:
        print(f"\n  WARNING: This will WIPE ALL DATA on {phone_name}!")
        print("  - All installed apps will be removed")
        print("  - Logged-in accounts will be logged out")
        print("  - All files will be deleted")
        print()
        response = input("  Type 'YES' to confirm: ")
        if response != 'YES':
            print("  Aborted.")
            return False

    # Call one-click new device API
    print("\n  Calling Geelark One-Click New Device API...")
    try:
        result = client.one_click_new_device(phone_id, change_brand_model=False)
        print(f"  API Response: {result}")
    except Exception as e:
        print(f"  ERROR: API call failed: {e}")
        return False

    # Wait for phone to reprovision (this can take 1-2 minutes)
    print("\n  Waiting for phone to reprovision...")
    print("  This may take 1-2 minutes...")

    # The phone will restart, so we need to wait for it to come back online
    for i in range(90):  # Wait up to 3 minutes
        time.sleep(2)
        try:
            status = client.get_phone_status([phone_id])
            items = status.get("successDetails", [])
            if items and items[0].get("status") == 0:
                print(f"    Phone is online after {(i+1)*2}s")
                break
        except:
            pass
        if (i + 1) % 15 == 0:
            print(f"    Still waiting... ({(i+1)*2}s)")
    else:
        print("  WARNING: Phone may still be reprovisioning. Check Geelark dashboard.")

    # Give it a moment to fully boot
    print("  Waiting for full boot...")
    time.sleep(10)

    # Enable ADB and verify
    print("\n  Verifying ADBKeyboard installation...")
    try:
        client.enable_adb(phone_id)
        time.sleep(5)

        adb_info = client.get_adb_info(phone_id)
        device = f"{adb_info['ip']}:{adb_info['port']}"
        password = adb_info['pwd']

        subprocess.run([ADB_PATH, "connect", device], capture_output=True)
        adb(device, f"glogin {password}")

        if check_adbkeyboard(device):
            pm_path = adb(device, "pm path com.android.adbkeyboard")
            print(f"  SUCCESS: ADBKeyboard installed at {pm_path}")

            # Set as default IME
            adb(device, "ime enable com.android.adbkeyboard/.AdbIME")
            adb(device, "ime set com.android.adbkeyboard/.AdbIME")
            print("  ADBKeyboard set as default IME")

            return True
        else:
            print("  WARNING: ADBKeyboard still not installed after reprovisioning")
            print("  Check Geelark dashboard or contact support")
            return False

    except Exception as e:
        print(f"  ERROR during verification: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python reprovision_phone.py <phone_name>")
        print("Example: python reprovision_phone.py reelwisdompod_")
        print()
        print("WARNING: This will WIPE ALL DATA on the phone!")
        sys.exit(1)

    phone_name = sys.argv[1]

    # Check for --yes flag to skip confirmation
    confirm = "--yes" not in sys.argv

    success = reprovision_phone(phone_name, confirm=confirm)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
