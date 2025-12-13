# Configuration Reference

## Config Class

**File:** `config.py`

Centralized configuration for all modules. This is the single source of truth for paths, timeouts, and constants.

### Usage

```python
from config import Config, setup_environment

# Call early in your script
setup_environment()

# Access configuration
adb_path = Config.ADB_PATH
timeout = Config.ADB_TIMEOUT
```

---

## Path Configuration

| Constant | Default | Description |
|----------|---------|-------------|
| `ANDROID_SDK_PATH` | `C:\Users\asus\Downloads\android-sdk` | Android SDK location |
| `ADB_PATH` | `{SDK}/platform-tools/adb.exe` | ADB executable |
| `PROJECT_ROOT` | Auto-detected | Project root directory |

---

## Appium Configuration

| Constant | Default | Description |
|----------|---------|-------------|
| `APPIUM_BASE_PORT` | 4723 | First Appium port |
| `DEFAULT_APPIUM_URL` | `http://127.0.0.1:4723` | Default Appium URL |

### Port Allocation

Workers use sequential odd ports:
- Worker 0: 4723
- Worker 1: 4725
- Worker 2: 4727
- ...

```python
port = Config.get_worker_appium_port(worker_id)
url = Config.get_worker_appium_url(worker_id)
```

---

## Parallel Execution

| Constant | Default | Description |
|----------|---------|-------------|
| `DEFAULT_NUM_WORKERS` | 3 | Default parallel workers |
| `MAX_WORKERS` | 10 | Maximum allowed workers |
| `SYSTEM_PORT_BASE` | 8200 | UiAutomator2 port base |
| `SYSTEM_PORT_RANGE` | 10 | Ports per worker |

### systemPort Allocation

Each worker gets a range for UiAutomator2:
- Worker 0: 8200-8209
- Worker 1: 8210-8219
- Worker 2: 8220-8229

```python
start, end = Config.get_worker_system_port_range(worker_id)
```

---

## Job Execution

| Constant | Default | Description |
|----------|---------|-------------|
| `MAX_POSTS_PER_ACCOUNT_PER_DAY` | 1 | Limit per account |
| `DELAY_BETWEEN_JOBS` | 10 | Seconds between jobs |
| `JOB_TIMEOUT` | 300 | Max job duration (5 min) |
| `SHUTDOWN_TIMEOUT` | 60 | Graceful shutdown wait |

---

## Retry Settings

| Constant | Default | Description |
|----------|---------|-------------|
| `MAX_RETRY_ATTEMPTS` | 3 | Retry attempts for failed jobs |
| `RETRY_DELAY_MINUTES` | 5 | Wait between retries |
| `NON_RETRYABLE_ERRORS` | `{'suspended', 'captcha', ...}` | Errors that skip retry |

### Non-Retryable Error Types

These errors indicate the account/job cannot succeed:
- `suspended` - Account suspended
- `captcha` - Verification required
- `loggedout` - Session expired
- `actionblocked` - Rate limited
- `banned` - Account disabled

---

## Timeouts

| Constant | Default | Description |
|----------|---------|-------------|
| `ADB_TIMEOUT` | 30 | ADB command timeout (seconds) |
| `ADB_READY_TIMEOUT` | 90 | Wait for ADB device |
| `APPIUM_CONNECT_TIMEOUT` | 60 | Appium connection timeout |
| `PHONE_BOOT_TIMEOUT` | 120 | Phone startup timeout |

---

## File Paths

| Constant | Default | Description |
|----------|---------|-------------|
| `PROGRESS_FILE` | `parallel_progress.csv` | Job tracking file |
| `STATE_FILE` | `scheduler_state.json` | Scheduler state |
| `LOGS_DIR` | `logs` | Log file directory |
| `ACCOUNTS_FILE` | `accounts.txt` | Approved accounts list |

---

## Screen Coordinates

For Geelark cloud phones (720x1280 resolution):

| Constant | Value | Description |
|----------|-------|-------------|
| `SCREEN_CENTER_X` | 360 | Horizontal center |
| `SCREEN_CENTER_Y` | 640 | Vertical center |
| `FEED_TOP_Y` | 400 | Feed scroll top |
| `FEED_BOTTOM_Y` | 900 | Feed scroll bottom |
| `REELS_TOP_Y` | 300 | Reels scroll top |
| `REELS_BOTTOM_Y` | 1000 | Reels scroll bottom |
| `NOTIFICATIONS_TOP_Y` | 800 | Notifications area |
| `STORY_NEXT_TAP_X` | 650 | Story navigation tap |
| `SWIPE_DURATION_FAST` | 300 | Fast swipe (ms) |
| `SWIPE_DURATION_SLOW` | 200 | Slow swipe (ms) |
| `SWIPE_DURATION_MAX` | 400 | Max for randomization |

---

## Environment Setup

The `setup_environment()` function configures:

```python
from config import setup_environment

setup_environment()
# Sets:
# - ANDROID_HOME
# - ANDROID_SDK_ROOT
# - Adds platform-tools to PATH
```

Call this before any Appium imports.

---

## Subprocess Environment

For spawning processes that need ADB:

```python
from config import get_adb_env

env = get_adb_env()
subprocess.run(["adb", "devices"], env=env)
```

---

## Customization

To customize configuration, edit `config.py` directly. All modules import from this single source.

**Example: Change SDK path**
```python
# In config.py
ANDROID_SDK_PATH: str = r"D:\Android\sdk"
```

**Example: Increase retries**
```python
MAX_RETRY_ATTEMPTS: int = 5
RETRY_DELAY_MINUTES: int = 10
```
