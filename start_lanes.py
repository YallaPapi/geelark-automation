"""
Multi-Lane Startup Helper

Starts multiple Appium instances and lane processes for parallel posting.
Each lane has its own Appium server and port range - no cross-talk.

Usage:
    # Start 2 lanes (2 Appium servers + 2 posting processes):
    python start_lanes.py --lanes 2 --accounts-file accounts.txt --add-folder chunk_01c

    # Start 3 lanes with custom delay:
    python start_lanes.py --lanes 3 --accounts-file accounts.txt --add-folder chunk_01c --delay 15

    # Just start Appium servers (no posting):
    python start_lanes.py --lanes 2 --appium-only

    # Stop all lanes:
    python start_lanes.py --stop-all
"""

import os
import sys
import time
import argparse
import subprocess

# Set environment early
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'
os.environ['ANDROID_SDK_ROOT'] = r'C:\Users\asus\Downloads\android-sdk'

from lane_config import LANES, get_lane_config
from process_tracker import start_process, kill_process, list_processes, is_pid_running


def start_appium_for_lane(lane_name: str) -> bool:
    """Start Appium server for a specific lane"""
    lane = get_lane_config(lane_name)
    port = lane['appium_port']
    label = f"appium_{lane_name}"

    command = f"appium --address 127.0.0.1 --port {port}"
    print(f"Starting Appium for {lane_name} on port {port}...")

    return start_process(label, command)


def start_lane_process(lane_name: str, accounts_file: str, folder: str, delay: int) -> bool:
    """Start posting_lane.py for a specific lane"""
    label = f"lane_{lane_name}"
    command = f'python -u posting_lane.py --lane-name {lane_name} --accounts-file {accounts_file} --add-folder {folder} --delay {delay}'

    print(f"Starting posting lane: {lane_name}...")
    return start_process(label, command)


def check_appium_ready(port: int, timeout: int = 30) -> bool:
    """Wait for Appium to be ready"""
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:{port}/status"
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except:
            pass
        time.sleep(1)

    return False


def start_lanes(num_lanes: int, accounts_file: str = None, folder: str = None, delay: int = 10, appium_only: bool = False):
    """Start multiple lanes"""
    if num_lanes > len(LANES):
        print(f"Warning: Only {len(LANES)} lanes configured. Using {len(LANES)}.")
        num_lanes = len(LANES)

    # Start Appium servers for each lane
    print(f"\n=== Starting {num_lanes} Appium servers ===")
    for i in range(num_lanes):
        lane = LANES[i]
        start_appium_for_lane(lane['name'])
        time.sleep(2)  # Stagger starts

    # Wait for all Appium servers to be ready
    print("\n=== Waiting for Appium servers to be ready ===")
    all_ready = True
    for i in range(num_lanes):
        lane = LANES[i]
        port = lane['appium_port']
        print(f"  Checking {lane['name']} (port {port})...", end=" ")
        if check_appium_ready(port, timeout=30):
            print("READY")
        else:
            print("FAILED - not responding")
            all_ready = False

    if not all_ready:
        print("\nSome Appium servers failed to start. Check logs.")
        return False

    if appium_only:
        print("\n=== Appium servers started (--appium-only mode) ===")
        print("Use posting_lane.py manually to start posting.")
        return True

    # Validate required args for posting
    if not accounts_file or not folder:
        print("\n=== Appium servers started ===")
        print("To start posting, run posting_lane.py manually or provide --accounts-file and --add-folder")
        return True

    # Start lane posting processes
    print(f"\n=== Starting {num_lanes} lane processes ===")
    for i in range(num_lanes):
        lane = LANES[i]
        start_lane_process(lane['name'], accounts_file, folder, delay)
        time.sleep(3)  # Stagger starts to avoid race conditions

    print(f"\n=== All {num_lanes} lanes started! ===")
    print("Monitor with: python process_tracker.py list")
    print("Stop all with: python start_lanes.py --stop-all")

    return True


def stop_all_lanes():
    """Stop all Appium servers and lane processes"""
    print("Stopping all lanes...")

    # Stop lane processes first
    for lane in LANES:
        label = f"lane_{lane['name']}"
        kill_process(label)

    time.sleep(2)

    # Stop Appium servers
    for lane in LANES:
        label = f"appium_{lane['name']}"
        kill_process(label)

    # Also stop phones
    print("\nStopping all running phones...")
    try:
        from geelark_client import GeelarkClient
        client = GeelarkClient()
        for page in range(1, 20):
            result = client.list_phones(page=page, page_size=100)
            for phone in result.get('items', []):
                if phone.get('status') == 1:
                    client.stop_phone(phone['id'])
                    print(f"  Stopped: {phone.get('serialName', 'unknown')}")
            if len(result.get('items', [])) < 100:
                break
    except Exception as e:
        print(f"  Warning: Could not stop phones: {e}")

    print("\nAll lanes stopped.")


def main():
    parser = argparse.ArgumentParser(
        description='Multi-Lane Startup Helper',
        epilog='''
Examples:
  # Start 2 lanes with posting:
  python start_lanes.py --lanes 2 --accounts-file accounts_list.txt --add-folder chunk_01c

  # Start just Appium servers:
  python start_lanes.py --lanes 2 --appium-only

  # Stop everything:
  python start_lanes.py --stop-all
''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--lanes', type=int, default=2,
                       help='Number of lanes to start (default: 2)')
    parser.add_argument('--accounts-file', type=str,
                       help='Accounts file for posting')
    parser.add_argument('--add-folder', type=str,
                       help='Video folder for posting')
    parser.add_argument('--delay', type=int, default=10,
                       help='Delay between posts per lane (default: 10)')
    parser.add_argument('--appium-only', action='store_true',
                       help='Only start Appium servers, not posting processes')
    parser.add_argument('--stop-all', action='store_true',
                       help='Stop all lanes and phones')
    parser.add_argument('--status', action='store_true',
                       help='Show status of all processes')

    args = parser.parse_args()

    if args.stop_all:
        stop_all_lanes()
        return

    if args.status:
        list_processes()
        return

    start_lanes(
        num_lanes=args.lanes,
        accounts_file=args.accounts_file,
        folder=args.add_folder,
        delay=args.delay,
        appium_only=args.appium_only
    )


if __name__ == '__main__':
    main()
