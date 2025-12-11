"""
Test connecting to a Geelark phone via ADB
"""
import time
from geelark_client import GeelarkClient
from adb_controller import ADBController

def test_connection(phone_name):
    client = GeelarkClient()

    # Find phone
    print(f"Looking for phone: {phone_name}")
    result = client.list_phones(page_size=100)
    phone = None
    for p in result["items"]:
        if p["serialName"] == phone_name:
            phone = p
            break

    if not phone:
        print(f"Phone not found: {phone_name}")
        return

    phone_id = phone["id"]
    print(f"Found: {phone['serialName']} (ID: {phone_id}, Status: {phone['status']})")

    # Start if not running
    if phone["status"] != 0:
        print("Starting phone...")
        client.start_phone(phone_id)
        print("Waiting 30 seconds for boot...")
        time.sleep(30)

    # Enable ADB
    print("Enabling ADB...")
    client.enable_adb(phone_id)
    print("Waiting 5 seconds...")
    time.sleep(5)

    # Get ADB info
    print("Getting ADB info...")
    adb_info = client.get_adb_info(phone_id)
    print(f"IP: {adb_info['ip']}")
    print(f"Port: {adb_info['port']}")
    print(f"Password: {adb_info['pwd']}")

    # Connect
    print("\nConnecting via ADB...")
    adb = ADBController(adb_info["ip"], adb_info["port"], adb_info["pwd"])

    if adb.connect():
        print("\n✓ Connected successfully!")

        # Test a command
        print("\nTesting shell command...")
        result = adb.shell("getprop ro.product.model")
        print(f"Device model: {result}")

        # Take screenshot
        print("\nTaking screenshot...")
        if adb.screenshot_to_file("test_screenshot.png"):
            print("✓ Screenshot saved to test_screenshot.png")
        else:
            print("✗ Screenshot failed")

        adb.disconnect()
    else:
        print("\n✗ Connection failed")

    # Cleanup
    print("\nDisabling ADB...")
    client.disable_adb(phone_id)
    print("Done!")

if __name__ == "__main__":
    test_connection("talkloopclips")
