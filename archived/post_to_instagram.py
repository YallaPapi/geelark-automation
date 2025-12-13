"""
Post videos to Instagram via Geelark cloud phones.

Usage:
    python post_to_instagram.py <phone_name_or_id> <video_path> <caption>

Or import and use:
    from post_to_instagram import post_video
    post_video("cloudypenguinzip", "video.mp4", "Check this out! #funny")
"""
import sys
import os
import time
import tempfile
from geelark_client import GeelarkClient
from adb_controller import ADBController
from vision import analyze_for_instagram_post


def post_video(phone_identifier, video_path, caption, max_steps=50):
    """
    Post a video to Instagram on a Geelark cloud phone.

    Args:
        phone_identifier: Phone name or ID
        video_path: Local path to video file
        caption: Caption text to post
        max_steps: Maximum vision-action loops before giving up

    Returns:
        bool: True if post was successful
    """
    client = GeelarkClient()

    # Find phone
    print(f"Looking for phone: {phone_identifier}")
    result = client.list_phones(page_size=100)
    phone = None
    for p in result["items"]:
        if p["id"] == phone_identifier or p["serialName"] == phone_identifier:
            phone = p
            break

    if not phone:
        print(f"Phone not found: {phone_identifier}")
        return False

    phone_id = phone["id"]
    phone_name = phone["serialName"]
    print(f"Found phone: {phone_name} (ID: {phone_id})")

    # Start phone if not running
    if phone["status"] != 0:  # 0 = started
        print("Starting phone...")
        try:
            client.start_phone(phone_id)
            print("Phone starting, waiting 10 seconds...")
            time.sleep(10)
        except Exception as e:
            print(f"Failed to start phone: {e}")
            return False

    # Enable ADB
    print("Enabling ADB...")
    client.enable_adb(phone_id)
    print("Waiting 5 seconds for ADB to initialize...")
    time.sleep(5)

    # Get ADB connection info
    print("Getting ADB connection info...")
    adb_info = client.get_adb_info(phone_id)
    print(f"ADB: {adb_info['ip']}:{adb_info['port']}")

    # Connect via ADB
    adb = ADBController(adb_info["ip"], adb_info["port"], adb_info["pwd"])
    if not adb.connect():
        print("Failed to connect via ADB")
        return False

    try:
        # Upload video via Geelark API (not ADB - more reliable)
        print(f"Uploading video to Geelark cloud: {video_path}")
        resource_url = client.upload_file_to_geelark(video_path)
        print(f"Video uploaded to: {resource_url}")

        print("Pushing video to phone's Downloads folder...")
        upload_result = client.upload_file_to_phone(phone_id, resource_url)
        task_id = upload_result.get("taskId")
        print(f"Upload task started: {task_id}")

        print("Waiting for upload to complete...")
        client.wait_for_upload(task_id)
        print("Video uploaded to phone!")

        # Trigger media scan so video appears in gallery
        remote_video = "/sdcard/Download/" + os.path.basename(video_path)
        adb.shell(f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{remote_video}")
        time.sleep(3)

        # Launch Instagram
        print("Launching Instagram...")
        adb.launch_instagram()
        time.sleep(5)

        # Vision-action loop
        video_uploaded = False
        step = 0

        with tempfile.TemporaryDirectory() as tmpdir:
            while step < max_steps:
                step += 1
                print(f"\n--- Step {step} ---")

                # Take screenshot via Geelark API (more reliable than ADB)
                screenshot_path = os.path.join(tmpdir, f"screen_{step}.png")
                print("Taking screenshot...")

                try:
                    download_url = client.wait_for_screenshot(phone_id, timeout=30)
                    # Download the screenshot
                    import requests as req
                    resp = req.get(download_url)
                    with open(screenshot_path, "wb") as f:
                        f.write(resp.content)
                except Exception as e:
                    print(f"Failed to take screenshot: {e}")
                    time.sleep(2)
                    continue

                # Analyze with Claude Vision
                print("Analyzing screen...")
                try:
                    result = analyze_for_instagram_post(
                        screenshot_path,
                        caption,
                        video_uploaded=video_uploaded
                    )
                except Exception as e:
                    print(f"Vision error: {e}")
                    time.sleep(2)
                    continue

                print(f"Action: {result.get('action')} - {result.get('message')}")

                # Track if video was selected
                if result.get("video_selected"):
                    video_uploaded = True

                # Execute action
                action = result.get("action")

                if action == "done":
                    print("\n[SUCCESS] Post completed successfully!")
                    return True

                elif action == "error":
                    print(f"\n[ERROR] Error detected: {result.get('message')}")
                    return False

                elif action == "wait":
                    print("Waiting for loading...")
                    time.sleep(3)

                elif action == "tap":
                    x, y = result.get("x"), result.get("y")
                    print(f"Tapping ({x}, {y})")
                    adb.tap(x, y)
                    time.sleep(2)

                elif action == "type":
                    text = result.get("text", caption)
                    print(f"Typing: {text[:50]}...")
                    adb.type_text(text)
                    time.sleep(1)

                elif action == "swipe":
                    swipe = result.get("swipe", {})
                    print(f"Swiping from ({swipe['x1']},{swipe['y1']}) to ({swipe['x2']},{swipe['y2']})")
                    adb.swipe(swipe["x1"], swipe["y1"], swipe["x2"], swipe["y2"])
                    time.sleep(1)

                elif action == "back":
                    print("Pressing back")
                    adb.back()
                    time.sleep(1)

                else:
                    print(f"Unknown action: {action}")
                    time.sleep(2)

        print(f"\n[FAILED] Max steps ({max_steps}) reached without completing post")
        return False

    finally:
        # Cleanup
        print("\nCleaning up...")
        try:
            adb.shell(f"rm /sdcard/Download/{os.path.basename(video_path)}")
        except:
            pass
        adb.disconnect()
        client.disable_adb(phone_id)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python post_to_instagram.py <phone_name> <video_path> <caption>")
        print('Example: python post_to_instagram.py cloudypenguinzip video.mp4 "Check this out!"')
        sys.exit(1)

    phone = sys.argv[1]
    video = sys.argv[2]
    caption = sys.argv[3]

    success = post_video(phone, video, caption)
    sys.exit(0 if success else 1)
