"""
Diagnose ADBKeyboard installation state on Geelark phones.
Checks for ghost packages, system apps, and IME settings.
"""
import sys
import time
import subprocess
from geelark_client import GeelarkClient

ADB_PATH = r"C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe"

PHONES = ["podmindstudio", "miccliparchive", "reelwisdompod_", "talktrackhub"]


def adb(device, cmd, timeout=30):
    """Run ADB shell command"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "shell", cmd],
        capture_output=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""


def diagnose_phone(phone_name):
    """Diagnose ADBKeyboard state on a phone"""
    client = GeelarkClient()

    print(f"\n{'='*60}")
    print(f"DIAGNOSING: {phone_name}")
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
        return {"phone": phone_name, "error": "not_found"}

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

    results = {"phone": phone_name, "device": device}

    # 1. Check pm path
    print("\n  [1] pm path com.android.adbkeyboard:")
    pm_path = adb(device, "pm path com.android.adbkeyboard")
    print(f"      {pm_path or '(empty - not installed)'}")
    results["pm_path"] = pm_path

    # 2. Check installed packages
    print("\n  [2] pm list packages | grep adbkeyboard:")
    installed = adb(device, "pm list packages | grep -i adbkeyboard")
    print(f"      {installed or '(not in installed list)'}")
    results["installed"] = installed

    # 3. Check ghost packages (uninstalled but retained)
    print("\n  [3] pm list packages -u | grep adbkeyboard (includes ghosts):")
    ghost_check = adb(device, "pm list packages -u | grep -i adbkeyboard")
    print(f"      {ghost_check or '(not in ghost list either)'}")
    results["ghost"] = ghost_check

    # 4. Check system vs user app
    print("\n  [4] pm list packages -s | grep adbkeyboard (system apps):")
    system_pkg = adb(device, "pm list packages -s | grep -i adbkeyboard")
    print(f"      {system_pkg or '(not a system app)'}")
    results["system_pkg"] = system_pkg

    # 5. Check filesystem for APK
    print("\n  [5] Checking filesystem for ADBKeyboard.apk:")
    locations = [
        "/system/app/AdbKeyboard/",
        "/system/app/ADBKeyboard/",
        "/system/priv-app/AdbKeyboard/",
        "/product/app/AdbKeyboard/",
        "/data/app/",
    ]
    for loc in locations:
        files = adb(device, f"ls {loc} 2>/dev/null | grep -i adb")
        if files:
            print(f"      FOUND at {loc}: {files}")
            results["apk_location"] = loc
    if "apk_location" not in results:
        print("      (not found in any standard location)")
        results["apk_location"] = None

    # 6. Check current IME
    print("\n  [6] Current IME setting:")
    current_ime = adb(device, "settings get secure default_input_method")
    print(f"      {current_ime}")
    results["current_ime"] = current_ime

    # 7. Check all IMEs
    print("\n  [7] Available IMEs (ime list -a):")
    ime_list = adb(device, "ime list -a 2>/dev/null | head -20")
    if "adbkeyboard" in ime_list.lower():
        print(f"      ADBKeyboard found in IME list")
        results["ime_registered"] = True
    else:
        print(f"      ADBKeyboard NOT in IME list")
        results["ime_registered"] = False

    # 8. Check package dump
    print("\n  [8] dumpsys package com.android.adbkeyboard (summary):")
    pkg_dump = adb(device, "dumpsys package com.android.adbkeyboard 2>/dev/null | head -30")
    if "Unable to find package" in pkg_dump or not pkg_dump:
        print("      Package not found in package manager")
        results["pkg_dump"] = "not_found"
    else:
        print("      Package exists in package manager database")
        # Check if enabled/disabled
        if "enabled=" in pkg_dump.lower():
            print(f"      Enabled state found in dump")
        results["pkg_dump"] = "exists"

    # Summary
    print("\n  " + "-"*50)
    print("  DIAGNOSIS SUMMARY:")
    if results.get("pm_path"):
        print("    STATUS: INSTALLED and working")
        results["status"] = "installed"
    elif results.get("ghost") and not results.get("installed"):
        print("    STATUS: GHOST PACKAGE (in -u list but not installed)")
        results["status"] = "ghost"
    elif results.get("apk_location"):
        print("    STATUS: APK exists on filesystem but not registered")
        results["status"] = "unregistered"
    else:
        print("    STATUS: NOT INSTALLED (clean slate)")
        results["status"] = "not_installed"

    return results


def main():
    phones_to_check = sys.argv[1:] if len(sys.argv) > 1 else PHONES

    all_results = []
    for phone in phones_to_check:
        try:
            result = diagnose_phone(phone)
            all_results.append(result)
        except Exception as e:
            print(f"\n  ERROR: {e}")
            all_results.append({"phone": phone, "error": str(e)})

    # Final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"{'Phone':<20} {'Status':<15} {'IME Set':<10} {'APK Location'}")
    print("-"*60)
    for r in all_results:
        if "error" in r:
            print(f"{r['phone']:<20} ERROR: {r['error']}")
        else:
            ime_ok = "Yes" if "adbkeyboard" in r.get("current_ime", "").lower() else "No"
            apk = r.get("apk_location", "None")[:20] if r.get("apk_location") else "None"
            print(f"{r['phone']:<20} {r.get('status', 'unknown'):<15} {ime_ok:<10} {apk}")


if __name__ == "__main__":
    main()
