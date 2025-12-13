# Core Modules Reference

## SmartInstagramPoster

**File:** `post_reel_smart.py`

The main class for posting videos to Instagram Reels using Claude AI for navigation.

### Initialization

```python
from post_reel_smart import SmartInstagramPoster

poster = SmartInstagramPoster(
    phone_name="myphone1",      # Geelark phone name or ID
    system_port=8200,           # UiAutomator2 port (unique per worker)
    appium_url="http://127.0.0.1:4723"  # Appium server URL
)
```

### Methods

#### connect()

Establish connection to the phone.

```python
poster.connect()
```

This performs:
1. Find phone in Geelark
2. Start phone if stopped
3. Enable ADB
4. Connect ADB
5. Connect Appium driver

---

#### post(video_path, caption, max_steps=30, humanize=False)

Post a video to Instagram Reels.

```python
success = poster.post(
    video_path="/path/to/video.mp4",
    caption="Check this out! #reels",
    max_steps=30,      # Max navigation steps
    humanize=False     # Random actions before posting
)
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `video_path` | str | - | Path to video file |
| `caption` | str | - | Caption with hashtags |
| `max_steps` | int | 30 | Max UI navigation steps |
| `humanize` | bool | False | Add human-like actions |

**Returns:** `bool` - True if post succeeded

**Flow:**
1. Upload video to phone
2. Open Instagram
3. (Optional) Humanize actions
4. Vision-action loop with Claude AI
5. Verify upload completion

---

#### cleanup()

Clean up after posting.

```python
poster.cleanup()
```

This:
- Removes uploaded videos from phone
- Disconnects Appium
- Disables ADB
- Stops the phone (saves billing)

---

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `phone_id` | str | Geelark phone ID |
| `device` | str | ADB device string (ip:port) |
| `appium_driver` | WebDriver | Appium driver instance |
| `last_error_type` | str | Error type if failed |
| `last_error_message` | str | Error message if failed |

---

### Example Usage

```python
from post_reel_smart import SmartInstagramPoster

poster = SmartInstagramPoster("myphone1")

try:
    poster.connect()
    success = poster.post(
        "video.mp4",
        "Amazing content! #viral #reels",
        humanize=True
    )
    if success:
        print("Posted successfully!")
    else:
        print(f"Failed: {poster.last_error_message}")
finally:
    poster.cleanup()
```

---

## DeviceConnectionManager

**File:** `device_connection.py`

Manages the full device connection lifecycle.

### Initialization

```python
from device_connection import DeviceConnectionManager

conn = DeviceConnectionManager(
    phone_name="myphone1",
    system_port=8200,
    appium_url="http://127.0.0.1:4723",
    geelark_client=None  # Optional, creates one if not provided
)
```

### Methods

#### connect()

Full connection flow.

```python
conn.connect()  # Returns True on success
```

---

#### disconnect()

Clean disconnect.

```python
conn.disconnect()
```

Stops Appium, disables ADB, stops phone.

---

#### adb_command(cmd, timeout=30)

Run ADB shell command.

```python
output = conn.adb_command("pm list packages | grep instagram")
```

---

#### reconnect_appium()

Reconnect after UiAutomator2 crash.

```python
conn.reconnect_appium()
```

---

## ProgressTracker

**File:** `progress_tracker.py`

Process-safe job tracking with file locking for parallel workers.

### Initialization

```python
from progress_tracker import ProgressTracker

tracker = ProgressTracker(
    progress_file="parallel_progress.csv",
    lock_timeout=30.0  # Max seconds to wait for lock
)
```

### Methods

#### seed_from_scheduler_state(state_file)

Initialize progress file from scheduler state.

```python
tracker.seed_from_scheduler_state("scheduler_state.json")
```

---

#### claim_next_job(worker_id, max_posts_per_account_per_day=1)

Atomically claim the next available job.

```python
job = tracker.claim_next_job(worker_id=0, max_posts_per_account_per_day=1)
if job:
    print(f"Claimed: {job['job_id']} for {job['account']}")
```

**Returns:** `dict` or `None`
```python
{
    "job_id": "DMxxx123",
    "account": "myphone1",
    "video_path": "/path/to/video.mp4",
    "caption": "Caption text",
    "status": "claimed",
    "worker_id": "0"
}
```

---

#### update_job_status(job_id, status, worker_id, error=None, retry_delay_minutes=None)

Update job status after processing.

```python
# On success
tracker.update_job_status(job_id, "success", worker_id=0)

# On failure with retry
tracker.update_job_status(
    job_id, "failed", worker_id=0,
    error="Connection timeout",
    retry_delay_minutes=5
)
```

---

#### get_stats()

Get current progress statistics.

```python
stats = tracker.get_stats()
# Returns: {"pending": 10, "claimed": 2, "success": 5, "failed": 1, "total": 18}
```

---

### Job Statuses

| Status | Description |
|--------|-------------|
| `pending` | Ready to be claimed |
| `claimed` | Being processed by a worker |
| `success` | Completed successfully |
| `failed` | Failed permanently (non-retryable error) |
| `retrying` | Failed but will retry after delay |
| `skipped` | Skipped (account at daily limit) |

---

## ParallelConfig

**File:** `parallel_config.py`

Configuration for parallel worker execution.

```python
from parallel_config import get_config, ParallelConfig

config = get_config(num_workers=3)

# Access worker configuration
worker = config.get_worker(0)
print(f"Worker 0: port={worker.appium_port}, systemPort={worker.system_port}")
```

### WorkerConfig Attributes

| Attribute | Description |
|-----------|-------------|
| `worker_id` | Worker index (0-based) |
| `appium_port` | Appium server port (4723, 4725, ...) |
| `system_port` | UiAutomator2 port start |
| `appium_url` | Full Appium URL |
| `log_file` | Worker log file path |

---

## ClaudeUIAnalyzer

**File:** `claude_analyzer.py`

Handles Claude AI vision analysis for UI navigation.

```python
from claude_analyzer import ClaudeUIAnalyzer

analyzer = ClaudeUIAnalyzer()

# Analyze UI elements
action = analyzer.analyze_and_decide(
    elements=[...],      # Parsed UI elements
    caption="My caption",
    video_uploaded=False,
    caption_entered=False,
    share_clicked=False
)
# Returns: {"action": "tap", "element_index": 3, "reason": "Tap + button"}
```

---

## AppiumUIController

**File:** `appium_ui_controller.py`

Low-level Appium UI interactions.

```python
from appium_ui_controller import AppiumUIController

# Requires connected Appium driver
ui = AppiumUIController(driver)

ui.tap(360, 640)
ui.swipe(360, 900, 360, 400, 300)
ui.press_key("KEYCODE_BACK")
ui.type_text("Hello world!")

elements = ui.dump_ui()  # Parse UI hierarchy
```

### Methods

| Method | Description |
|--------|-------------|
| `tap(x, y)` | Tap at coordinates |
| `swipe(x1, y1, x2, y2, duration)` | Swipe gesture |
| `press_key(keycode)` | Press Android key |
| `type_text(text)` | Type text (supports Unicode) |
| `dump_ui()` | Parse UI XML to element list |
| `scroll_down()` / `scroll_up()` | Scroll the screen |
