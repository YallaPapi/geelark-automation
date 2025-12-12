"""
Single-Lane Posting Script - Isolated Appium instance per lane

This script runs a single posting "lane" with its own Appium server.
Multiple lanes can run in parallel without port collisions.

Usage:
    # Using lane config:
    python posting_lane.py --lane-name lane1 --accounts-file accounts.txt --add-folder chunk_01c

    # Or explicit config:
    python posting_lane.py --appium-url http://127.0.0.1:4723 --system-port-base 8200 \
                          --accounts-file accounts.txt --add-folder chunk_01c

Key features:
- NO shared state with parallel scheduler (no cross-talk)
- Each lane uses its own Appium server and port range
- Writes results to standard batch_results_*.csv for tracking
- Simple single-worker loop (no threading complexity)
"""

import os
import sys

# Set ANDROID_HOME early for Appium
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'
os.environ['ANDROID_SDK_ROOT'] = r'C:\Users\asus\Downloads\android-sdk'

import csv
import glob
import json
import time
import argparse
from datetime import datetime
from typing import Set, List, Dict, Optional
from dataclasses import dataclass

# Fix Windows console encoding
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')


@dataclass
class VideoJob:
    """A single video posting job"""
    shortcode: str
    video_path: str
    caption: str
    account: Optional[str] = None
    status: str = "pending"
    error: str = ""


def log(msg: str, lane_name: str = ""):
    """Simple logging with timestamp"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = f"[{lane_name}]" if lane_name else "[LANE]"
    print(f"[{ts}] {prefix} {msg}")


def get_already_posted_accounts() -> Set[str]:
    """Get accounts that have already successfully posted from batch_results_*.csv"""
    posted = set()

    for filepath in glob.glob("batch_results_*.csv"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'success':
                        account = row.get('phone') or row.get('account')
                        if account:
                            posted.add(account)
        except Exception as e:
            log(f"Warning: Could not read {filepath}: {e}")

    return posted


def get_already_posted_shortcodes() -> Set[str]:
    """Get video shortcodes that have already been posted from batch_results_*.csv"""
    posted = set()

    for filepath in glob.glob("batch_results_*.csv"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'success':
                        shortcode = row.get('shortcode')
                        if shortcode:
                            posted.add(shortcode)
        except Exception as e:
            log(f"Warning: Could not read {filepath}: {e}")

    return posted


def write_result_to_csv(shortcode: str, account: str, status: str, error: str = ""):
    """Write result to batch_results CSV (same format as main scheduler)"""
    timestamp = datetime.now().isoformat()
    date_str = datetime.now().strftime("%Y%m%d")
    filename = f"batch_results_{date_str}.csv"

    file_exists = os.path.exists(filename)

    try:
        with open(filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['shortcode', 'phone', 'status', 'error', 'timestamp'])
            writer.writerow([shortcode, account, status, error, timestamp])
        log(f"Result logged: {shortcode} -> {status}")
    except Exception as e:
        log(f"ERROR: Could not write to CSV: {e}")


def load_accounts_from_file(filepath: str) -> List[str]:
    """Load account names from file, one per line"""
    if not os.path.exists(filepath):
        log(f"Accounts file not found: {filepath}")
        return []

    accounts = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                accounts.append(line)

    return accounts


def load_videos_from_folder(folder_path: str) -> List[VideoJob]:
    """Load video jobs from folder with CSV captions"""
    if not os.path.isdir(folder_path):
        log(f"Folder not found: {folder_path}")
        return []

    # Find CSV with captions
    csv_files = glob.glob(os.path.join(folder_path, "*.csv"))
    if not csv_files:
        log(f"No CSV found in {folder_path}")
        return []

    csv_path = csv_files[0]

    # Build video path lookup
    videos = {}
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            if f.endswith('.mp4'):
                shortcode = f.replace('.mp4', '')
                videos[shortcode] = os.path.join(root, f)

    # Get already posted shortcodes to skip
    already_posted = get_already_posted_shortcodes()
    log(f"Found {len(already_posted)} already-posted videos to skip")

    # Load jobs from CSV
    jobs = []
    skipped = 0
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            caption = row.get('Text', '')
            video_ref = row.get('Image/Video link 1 (shortcode)', '') or \
                       row.get('Image/Video link 1 (file path or URL(works only for images))', '')

            if not video_ref or not caption:
                continue

            shortcode = video_ref.strip()
            video_path = videos.get(shortcode)

            if video_path and os.path.exists(video_path):
                if shortcode in already_posted:
                    skipped += 1
                    continue

                jobs.append(VideoJob(
                    shortcode=shortcode,
                    video_path=video_path,
                    caption=caption
                ))

    log(f"Loaded {len(jobs)} video jobs ({skipped} skipped as already posted)")
    return jobs


def check_appium_health(appium_url: str, timeout: int = 5) -> bool:
    """Check if Appium server is responding"""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(f"{appium_url}/status", method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


ADB_PATH = r"C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe"


def restart_adb_server():
    """Restart ADB server to clear ALL stale port forwards.

    This is the ONLY reliable way to clear forwards from disconnected devices.
    """
    import subprocess
    log("Restarting ADB server to clear stale port forwards...")
    try:
        # Kill ADB server
        subprocess.run([ADB_PATH, "kill-server"], capture_output=True, timeout=10)
        time.sleep(1)
        # Restart ADB server
        subprocess.run([ADB_PATH, "start-server"], capture_output=True, timeout=10)
        time.sleep(1)
        log("ADB server restarted successfully")
        return True
    except Exception as e:
        log(f"Warning: ADB server restart failed: {e}")
        return False


def clear_adb_forwards(system_port_base: int):
    """Clear ADB forwards for our systemPort range.

    Tries to remove forwards for each port. If that fails due to
    multiple devices, we already restarted ADB server at lane startup.
    """
    import subprocess
    for offset in range(1, 6):
        port = system_port_base + offset
        try:
            subprocess.run(
                [ADB_PATH, "forward", "--remove", f"tcp:{port}"],
                capture_output=True, timeout=5
            )
        except Exception:
            pass  # Ignore errors - main cleanup is ADB restart


def restart_appium(lane_name: str, appium_port: int) -> bool:
    """Restart Appium server for this lane"""
    from process_tracker import kill_process, start_process

    label = f"appium_{lane_name}"
    log(f"Restarting Appium server ({label})...", lane_name)

    # Kill existing Appium if running
    kill_process(label)
    time.sleep(2)

    # Start fresh Appium
    command = f"appium --address 127.0.0.1 --port {appium_port}"
    if not start_process(label, command):
        log(f"Failed to start Appium server", lane_name)
        return False

    # Wait for Appium to be ready
    appium_url = f"http://127.0.0.1:{appium_port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        if check_appium_health(appium_url):
            log(f"Appium server restarted successfully", lane_name)
            return True
        time.sleep(1)

    log(f"Appium failed to become ready after restart", lane_name)
    return False


def run_lane(
    lane_name: str,
    appium_url: str,
    system_port_base: int,
    accounts: List[str],
    videos: List[VideoJob],
    delay_between_posts: int = 10,
):
    """Run the single-lane posting loop"""
    from post_reel_smart import SmartInstagramPoster, AdbReadinessError, GloginReadinessError
    from geelark_client import GeelarkClient

    log(f"Starting lane: {lane_name}", lane_name)
    log(f"  Appium URL: {appium_url}", lane_name)
    log(f"  systemPort base: {system_port_base}", lane_name)
    log(f"  Accounts: {len(accounts)}", lane_name)
    log(f"  Videos: {len(videos)}", lane_name)

    # Extract Appium port from URL for restart capability
    appium_port = int(appium_url.split(':')[-1])

    # CRITICAL: Restart ADB server to clear ALL stale port forwards
    # This is the ONLY reliable way to clear forwards from disconnected devices
    restart_adb_server()

    # Also try to clear specific forwards for our port range
    clear_adb_forwards(system_port_base)

    # Check Appium is running (or restart it)
    if not check_appium_health(appium_url):
        log(f"Appium not responding at {appium_url}, attempting restart...", lane_name)
        if not restart_appium(lane_name, appium_port):
            log(f"ERROR: Could not start Appium. Exiting.", lane_name)
            return

    # Get already-posted accounts
    already_posted = get_already_posted_accounts()
    remaining_accounts = [a for a in accounts if a not in already_posted]
    log(f"Remaining accounts to post: {len(remaining_accounts)} (skipped {len(accounts) - len(remaining_accounts)})", lane_name)

    if not remaining_accounts:
        log("All accounts have already posted. Nothing to do.", lane_name)
        return

    if not videos:
        log("No videos to post. Nothing to do.", lane_name)
        return

    # systemPort for this lane (using base + 1 since we're single-worker)
    system_port = system_port_base + 1
    video_index = 0
    geelark = GeelarkClient()
    appium_restart_count = 0
    max_appium_restarts = 10  # Limit restarts to prevent infinite loop

    for account in remaining_accounts:
        # Check if account already posted (could have been done by another lane)
        if account in get_already_posted_accounts():
            log(f"Skipping {account} - already posted", lane_name)
            continue

        # Check Appium health before each account - restart if crashed
        if not check_appium_health(appium_url):
            log(f"Appium crashed! Restarting ADB and Appium ({appium_restart_count + 1}/{max_appium_restarts})...", lane_name)
            appium_restart_count += 1
            # Clear ADB forwards before restart
            restart_adb_server()
            clear_adb_forwards(system_port_base)
            if appium_restart_count > max_appium_restarts:
                log(f"ERROR: Too many Appium restarts ({max_appium_restarts}). Exiting.", lane_name)
                return
            if not restart_appium(lane_name, appium_port):
                log(f"ERROR: Could not restart Appium. Exiting.", lane_name)
                return
            # Give Appium a moment to stabilize
            time.sleep(3)

        # Get next video (round-robin)
        if video_index >= len(videos):
            video_index = 0
        video = videos[video_index]
        video_index += 1

        log(f"=== Starting job: {video.shortcode} -> {account} ===", lane_name)

        poster = None
        try:
            # Create poster with lane-specific Appium URL and systemPort
            poster = SmartInstagramPoster(
                phone_name=account,
                system_port=system_port,
                appium_url=appium_url
            )

            # Connect to device
            poster.connect()

            # Post the video (humanize=False to avoid UiAutomator2 crashes)
            success = poster.post(video.video_path, video.caption, humanize=False)

            if success:
                log(f"SUCCESS: {video.shortcode} posted to {account}", lane_name)
                write_result_to_csv(video.shortcode, account, "success")
            else:
                log(f"FAILED: {video.shortcode} on {account} - post returned False", lane_name)
                write_result_to_csv(video.shortcode, account, "failed", "post returned False")

        except AdbReadinessError as e:
            log(f"ADB READINESS ERROR: {account} - {e}", lane_name)
            write_result_to_csv(video.shortcode, account, "error", f"AdbReadinessError: {e}")

        except GloginReadinessError as e:
            log(f"GLOGIN READINESS ERROR: {account} - {e}", lane_name)
            write_result_to_csv(video.shortcode, account, "error", f"GloginReadinessError: {e}")

        except Exception as e:
            error_msg = str(e)[:200]
            log(f"ERROR: {account} - {error_msg}", lane_name)
            write_result_to_csv(video.shortcode, account, "error", error_msg)

        finally:
            # Always try to clean up
            if poster:
                try:
                    if poster.appium_driver:
                        poster.appium_driver.quit()
                except:
                    pass

                try:
                    if poster.phone_id:
                        geelark.stop_phone(poster.phone_id)
                        log(f"Stopped phone: {account}", lane_name)
                except:
                    pass

        # Delay between posts
        if delay_between_posts > 0:
            log(f"Waiting {delay_between_posts}s before next post...", lane_name)
            time.sleep(delay_between_posts)

    log(f"Lane {lane_name} completed!", lane_name)


def main():
    parser = argparse.ArgumentParser(
        description='Single-Lane Posting Script',
        epilog='''
Examples:
  # Using lane config:
  python posting_lane.py --lane-name lane1 --accounts-file accounts.txt --add-folder chunk_01c

  # Explicit config:
  python posting_lane.py --appium-url http://127.0.0.1:4723 --system-port-base 8200 \\
                        --accounts-file accounts.txt --add-folder chunk_01c
''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--lane-name', type=str, default='lane1',
                       help='Lane name (uses lane_config.py settings)')
    parser.add_argument('--appium-url', type=str,
                       help='Override Appium URL (e.g., http://127.0.0.1:4723)')
    parser.add_argument('--system-port-base', type=int,
                       help='Override systemPort base (e.g., 8200)')
    parser.add_argument('--accounts-file', type=str, required=True,
                       help='File with account names, one per line')
    parser.add_argument('--add-folder', type=str, required=True,
                       help='Folder with videos and CSV captions')
    parser.add_argument('--delay', type=int, default=10,
                       help='Delay between posts in seconds (default: 10)')

    args = parser.parse_args()

    # Load lane config (use explicit args or fall back to lane_config.py)
    if args.appium_url and args.system_port_base:
        appium_url = args.appium_url
        system_port_base = args.system_port_base
        lane_name = args.lane_name
    else:
        # Load from lane_config.py
        try:
            from lane_config import get_lane_config
            lane_config = get_lane_config(args.lane_name)
            appium_url = args.appium_url or lane_config['appium_url']
            system_port_base = args.system_port_base or lane_config['system_port_base']
            lane_name = args.lane_name
        except Exception as e:
            print(f"Error loading lane config: {e}")
            print("Please provide --appium-url and --system-port-base explicitly")
            sys.exit(1)

    # Load accounts
    accounts = load_accounts_from_file(args.accounts_file)
    if not accounts:
        print(f"No accounts found in {args.accounts_file}")
        sys.exit(1)

    # Load videos
    videos = load_videos_from_folder(args.add_folder)
    if not videos:
        print(f"No videos found in {args.add_folder}")
        sys.exit(1)

    # Run the lane
    run_lane(
        lane_name=lane_name,
        appium_url=appium_url,
        system_port_base=system_port_base,
        accounts=accounts,
        videos=videos,
        delay_between_posts=args.delay
    )


if __name__ == '__main__':
    main()
