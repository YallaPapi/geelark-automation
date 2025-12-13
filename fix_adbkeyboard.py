"""
Fix ADBKeyboard installation on Geelark cloud phones.
Handles ghost packages, system app restoration, and fresh installs.

Usage:
    python fix_adbkeyboard.py <phone1> <phone2> ...

Example:
    python fix_adbkeyboard.py miccliparchive reelwisdompod_ talktrackhub
"""
import sys
import os
import time
import subprocess
import base64
from geelark_client import GeelarkClient
from config import Config

ADB_PATH = Config.ADB_PATH
APK_PATH = os.path.join(os.path.dirname(__file__), "ADBKeyboard.apk")
SYSTEM_APK_PATH = os.path.join(os.path.dirname(__file__), "ADBKeyboard_system.apk")


def adb(device, cmd, timeout=30):
    """Run ADB shell command"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "shell", cmd],
        capture_output=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""


def adb_pull(device, remote_path, local_path):
    """Pull file from device"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "pull", remote_path, local_path],
        capture_output=True, timeout=60,
        encoding='utf-8', errors='replace'
    )
    return "pulled" in result.stdout.lower() or result.returncode == 0


def adb_push(device, local_path, remote_path):
    """Push file to device"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "push", local_path, remote_path],
        capture_output=True, timeout=60,
        encoding='utf-8', errors='replace'
    )
    return "pushed" in result.stdout.lower() or result.returncode == 0


def adb_install(device, apk_path):
    """Install APK via ADB"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "install", "-r", apk_path],
        capture_output=True, timeout=120,
        encoding='utf-8', errors='replace'
    )
    stdout = result.stdout.strip() if result.stdout else ""
    stderr = result.stderr.strip() if result.stderr else ""
    return stdout, stderr


def diagnose_state(device):
    """Diagnose ADBKeyboard state on device"""
    pm_path = adb(device, "pm path com.android.adbkeyboard")
    installed = adb(device, "pm list packages | grep -i adbkeyboard")
    ghost = adb(device, "pm list packages -u | grep -i adbkeyboard")
    system_apk = adb(device, "ls /system/app/AdbKeyboard/ 2>/dev/null")

    if pm_path:
        return "installed", pm_path
    elif ghost and not installed:
        if system_apk:
            return "ghost_with_system_apk", system_apk
        else:
            return "ghost_no_apk", None
    else:
        if system_apk:
            return "not_installed_but_apk_exists", system_apk
        else:
            return "clean_slate", None


def fix_phone(phone_name, source_device=None):
    """Fix ADBKeyboard on a single phone"""
    client = GeelarkClient()

    print(f"\n{'='*60}")
    print(f"FIXING: {phone_name}")
    print('='*60)

    # Find phone
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
        print(f"  ERROR: Phone not found")
        return False

    phone_id = phone["id"]
    print(f"  Found: {phone['serialName']} (Status: {phone['status']})")

    # Start if needed
    if phone["status"] != 0:
        print("  Starting phone...")
        client.start_phone(phone_id)
        for i in range(60):
            time.sleep(2)
            status = client.get_phone_status([phone_id])
            items = status.get("successDetails", [])
            if items and items[0].get("status") == 0:
                break
        time.sleep(3)

    # Enable ADB
    print("  Enabling ADB...")
    client.enable_adb(phone_id)
    time.sleep(3)

    # Connect
    adb_info = client.get_adb_info(phone_id)
    device = f"{adb_info['ip']}:{adb_info['port']}"
    password = adb_info['pwd']

    subprocess.run([ADB_PATH, "connect", device], capture_output=True)
    adb(device, f"glogin {password}")

    # Diagnose current state
    print("\n  [1] Diagnosing current state...")
    state, extra = diagnose_state(device)
    print(f"      State: {state}")
    if extra:
        print(f"      Extra: {extra}")

    # Apply fix based on state
    if state == "installed":
        print("\n  [2] Already installed! Just verifying IME settings...")

    elif state == "ghost_with_system_apk":
        print("\n  [2] Ghost package with system APK - restoring...")

        # Try to restore system app
        print("      Running: cmd package install-existing com.android.adbkeyboard")
        result = adb(device, "cmd package install-existing com.android.adbkeyboard")
        print(f"      Result: {result}")

        if "installed" in result.lower() or not result:
            print("      Checking if restored...")
            time.sleep(1)
            pm_path = adb(device, "pm path com.android.adbkeyboard")
            if pm_path:
                print(f"      SUCCESS: Package restored! Path: {pm_path}")
            else:
                print("      WARNING: install-existing may have failed")
                # Try enabling instead
                print("      Trying: pm enable com.android.adbkeyboard")
                adb(device, "pm enable com.android.adbkeyboard")
                time.sleep(1)
                pm_path = adb(device, "pm path com.android.adbkeyboard")
                if pm_path:
                    print(f"      SUCCESS after pm enable: {pm_path}")

    elif state == "ghost_no_apk":
        print("\n  [2] Ghost package without system APK - cleaning and installing...")

        # Try to clear the ghost
        print("      Clearing ghost: pm uninstall --user 0 com.android.adbkeyboard")
        adb(device, "pm uninstall --user 0 com.android.adbkeyboard")
        time.sleep(1)

        # Now try fresh install
        if os.path.exists(APK_PATH):
            print(f"      Installing from: {APK_PATH}")
            stdout, stderr = adb_install(device, APK_PATH)
            print(f"      Result: {stdout} {stderr}")
        else:
            print(f"      ERROR: APK not found at {APK_PATH}")
            return False

    elif state == "clean_slate":
        print("\n  [2] Clean slate - fresh install needed...")

        # Try installing APK
        if os.path.exists(APK_PATH):
            print(f"      Installing from: {APK_PATH}")
            stdout, stderr = adb_install(device, APK_PATH)
            print(f"      Result: {stdout} {stderr}")

            if "Success" not in stdout:
                print("      Standard install failed.")
                # Try pushing to /sdcard and installing from there
                print("      Trying push + pm install method...")
                adb_push(device, APK_PATH, "/sdcard/ADBKeyboard.apk")
                result = adb(device, "pm install -r /sdcard/ADBKeyboard.apk")
                print(f"      pm install result: {result}")
        else:
            print(f"      ERROR: APK not found at {APK_PATH}")
            return False

    elif state == "not_installed_but_apk_exists":
        print("\n  [2] APK exists but not registered - trying to register...")
        print("      Running: cmd package install-existing com.android.adbkeyboard")
        result = adb(device, "cmd package install-existing com.android.adbkeyboard")
        print(f"      Result: {result}")

        if "installed" not in result.lower():
            print("      Trying: pm enable com.android.adbkeyboard")
            adb(device, "pm enable com.android.adbkeyboard")

    # Step 3: Verify installation
    print("\n  [3] Verifying installation...")
    time.sleep(1)
    pm_path = adb(device, "pm path com.android.adbkeyboard")
    if not pm_path:
        print("      ERROR: Package still not installed!")
        print("      This device may need Geelark reprovisioning.")
        return False
    print(f"      Package path: {pm_path}")

    # Step 4: Enable IME
    print("\n  [4] Enabling ADBKeyboard IME...")
    adb(device, "ime enable com.android.adbkeyboard/.AdbIME")
    time.sleep(0.5)
    adb(device, "ime set com.android.adbkeyboard/.AdbIME")
    time.sleep(0.5)

    # Also set via settings for persistence
    adb(device, "settings put secure enabled_input_methods com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME:com.android.adbkeyboard/.AdbIME")
    adb(device, "settings put secure default_input_method com.android.adbkeyboard/.AdbIME")

    # Step 5: Verify IME
    print("\n  [5] Verifying IME setting...")
    current_ime = adb(device, "settings get secure default_input_method")
    print(f"      Current IME: {current_ime}")

    if "adbkeyboard" not in current_ime.lower():
        print("      WARNING: IME setting may not have persisted")
        return False

    # Step 6: Test typing
    print("\n  [6] Testing ADBKeyboard broadcast...")
    test_text = "Test 123 🎉"
    text_b64 = base64.b64encode(test_text.encode('utf-8')).decode('ascii')
    result = adb(device, f"am broadcast -a ADB_INPUT_B64 --es msg {text_b64}")
    if "Broadcast completed" in result:
        print(f"      SUCCESS: Broadcast sent for '{test_text}'")
    else:
        print(f"      Broadcast result: {result}")

    print("\n  " + "="*50)
    print("  FIX COMPLETE!")
    print("  " + "="*50)
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_adbkeyboard.py <phone1> <phone2> ...")
        print("Example: python fix_adbkeyboard.py miccliparchive reelwisdompod_ talktrackhub")
        sys.exit(1)

    phones = sys.argv[1:]
    results = {}

    for phone in phones:
        try:
            results[phone] = fix_phone(phone)
        except Exception as e:
            print(f"\n  ERROR: {e}")
            import traceback
            traceback.print_exc()
            results[phone] = False

    # Summary
    print("\n" + "="*60)
    print("FIX SUMMARY")
    print("="*60)
    for phone, success in results.items():
        status = "SUCCESS" if success else "FAILED"
        print(f"  {phone}: {status}")

    # Return exit code
    all_success = all(results.values())
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()
