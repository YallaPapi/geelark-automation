"""
Process Tracker - Track background processes started by automation scripts.

Usage:
    python process_tracker.py start "appium" "appium --address 127.0.0.1 --port 4723"
    python process_tracker.py list
    python process_tracker.py kill appium
    python process_tracker.py kill-all
"""
import os
import sys
import json
import subprocess
from datetime import datetime

TRACKER_FILE = "background_processes.json"

def load_tracker():
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, 'r') as f:
            return json.load(f)
    return {"processes": []}

def save_tracker(data):
    with open(TRACKER_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def is_pid_running(pid):
    """Check if a PID is still running on Windows"""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except:
        return False

def start_process(label, command):
    """Start a labeled background process"""
    tracker = load_tracker()

    # Check if label already exists and is running
    for proc in tracker["processes"]:
        if proc["label"] == label and is_pid_running(proc["pid"]):
            print(f"[ERROR] Process '{label}' already running (PID {proc['pid']})")
            return False

    # Start the process with inherited environment + Android SDK paths
    env = os.environ.copy()
    env['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'
    env['ANDROID_SDK_ROOT'] = r'C:\Users\asus\Downloads\android-sdk'

    # Log output to file instead of DEVNULL so we can debug
    log_file = f"{label}_output.log"
    log_handle = open(log_file, 'w')

    if sys.platform == 'win32':
        # Use CREATE_NO_WINDOW to prevent new terminal windows
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=CREATE_NO_WINDOW
        )
    else:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True
        )

    # Record it
    tracker["processes"].append({
        "label": label,
        "pid": proc.pid,
        "command": command,
        "started": datetime.now().isoformat()
    })
    save_tracker(tracker)
    print(f"[STARTED] {label} (PID {proc.pid})")
    return True

def list_processes():
    """List all tracked processes"""
    tracker = load_tracker()

    print("=== TRACKED BACKGROUND PROCESSES ===")
    if not tracker["processes"]:
        print("  (none)")
        return

    for proc in tracker["processes"]:
        status = "RUNNING" if is_pid_running(proc["pid"]) else "STOPPED"
        print(f"  [{status}] {proc['label']} (PID {proc['pid']})")
        print(f"           Command: {proc['command'][:60]}...")
        print(f"           Started: {proc['started']}")

def kill_process(label):
    """Kill a tracked process by label"""
    tracker = load_tracker()

    for proc in tracker["processes"]:
        if proc["label"] == label:
            pid = proc["pid"]
            if is_pid_running(pid):
                try:
                    os.kill(pid, 9)
                    print(f"[KILLED] {label} (PID {pid})")
                except Exception as e:
                    # Try taskkill on Windows
                    os.system(f"taskkill /F /PID {pid} 2>nul")
                    print(f"[KILLED] {label} (PID {pid})")
            else:
                print(f"[ALREADY STOPPED] {label} (PID {pid})")

            # Remove from tracker
            tracker["processes"] = [p for p in tracker["processes"] if p["label"] != label]
            save_tracker(tracker)
            return True

    print(f"[NOT FOUND] No process with label '{label}'")
    return False

def kill_all():
    """Kill all tracked processes"""
    tracker = load_tracker()

    for proc in tracker["processes"]:
        pid = proc["pid"]
        label = proc["label"]
        if is_pid_running(pid):
            try:
                os.kill(pid, 9)
            except:
                os.system(f"taskkill /F /PID {pid} 2>nul")
            print(f"[KILLED] {label} (PID {pid})")
        else:
            print(f"[ALREADY STOPPED] {label} (PID {pid})")

    tracker["processes"] = []
    save_tracker(tracker)
    print("[DONE] All tracked processes cleared")

def cleanup_stale():
    """Remove entries for processes that are no longer running"""
    tracker = load_tracker()
    original_count = len(tracker["processes"])
    tracker["processes"] = [p for p in tracker["processes"] if is_pid_running(p["pid"])]
    removed = original_count - len(tracker["processes"])
    save_tracker(tracker)
    if removed > 0:
        print(f"[CLEANUP] Removed {removed} stale entries")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "start" and len(sys.argv) >= 4:
        start_process(sys.argv[2], sys.argv[3])
    elif cmd == "list":
        cleanup_stale()
        list_processes()
    elif cmd == "kill" and len(sys.argv) >= 3:
        kill_process(sys.argv[2])
    elif cmd == "kill-all":
        kill_all()
    else:
        print(__doc__)
