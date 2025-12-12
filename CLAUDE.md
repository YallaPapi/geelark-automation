# Claude Code Instructions

## CRITICAL: ALWAYS STOP PHONES

**THIS IS THE MOST IMPORTANT RULE. PHONES COST MONEY WHEN RUNNING.**

### When to Stop Phones:
1. **EVERY TIME you kill a batch test** - IMMEDIATELY run the stop script
2. **After ANY test completes** - success or failure
3. **Before starting a new test** - verify no phones running
4. **When user interrupts** - FIRST thing to do is stop phones

### How to Stop ALL Running Phones:
```bash
cd /c/Users/asus/Desktop/projects/geelark-automation && python -c "
from geelark_client import GeelarkClient
client = GeelarkClient()
for page in range(1, 20):
    result = client.list_phones(page=page, page_size=100)
    for phone in result['items']:
        if phone['status'] == 1:
            client.stop_phone(phone['id'])
            print(f'STOPPED: {phone[\"serialName\"]}')
    if len(result['items']) < 100:
        break
"
```

**NEVER leave phones running. Check and stop phones PROACTIVELY.**

---

## MANDATORY DEBUGGING WORKFLOW - RESEARCH BEFORE FIXING

**USE TASK MASTER TO RESEARCH SOLUTIONS BEFORE IMPLEMENTING FIXES.**

### When errors occur, follow this sequence:

1. **Document the error** - note exact error messages and context
2. **Use Task Master research to find proper solutions**:
   ```bash
   task-master add-task --prompt="<describe the error and what you need to fix>" --research --priority=high
   ```
3. **Review the researched solution** - Task Master will provide detailed implementation guidance
4. **Implement the fix** based on the researched solution
5. **Test the fix** with a fresh run

### KEY RULES:
- **ALWAYS research before implementing** - use Task Master's `--research` flag
- **NO guessing** - don't make assumptions about what might fix the issue
- **ONE fix at a time** - implement the researched solution, then test
- **Task Master knows best** - trust the researched guidance over intuition

### Why This Matters:
- Task Master has access to Perplexity AI for real-time research
- Researched solutions are based on actual documentation and best practices
- Random fixes without research create more bugs
- This workflow has proven to work (see Task 25 and 26 fixes)

---

## CURRENT POSTING RUN - 92 ACCOUNT TARGET

**We are completing ONE FULL ROUND of posting to all 92 accounts in `accounts_list.txt`.**

### ONE-CLICK USAGE (Parallel Scheduler):
```bash
python posting_scheduler_parallel.py --accounts-file accounts_list.txt --add-folder chunk_01c --workers 3 --run
```

This automatically:
1. Loads accounts from file
2. **Skips accounts that already posted** (checks batch_results_*.csv)
3. Loads videos from folder
4. Runs until all remaining accounts have posted

### Tracking Files:
| File | Purpose |
|------|---------|
| `accounts_list.txt` | The 92 target accounts for this posting run |
| `batch_results_*.csv` | **PRIMARY TRACKING** - All post attempts with status (success/error/failed) |
| `scheduler_state_parallel.json` | Parallel scheduler state |

### CSV Format (batch_results_*.csv):
```
shortcode,phone,status,error,timestamp
```

### Rule:
- Each account gets EXACTLY 1 successful post in this run
- The scheduler AUTOMATICALLY checks batch_results_*.csv and skips already-posted accounts
- No manual checking needed - just run the one-click command

---

## RECOMMENDED: Multi-Lane Architecture (NEW)

**For stable parallel posting, use the lane-based architecture instead of shared Appium.**

### Why Lanes?
- Each lane has its own Appium server (no port collisions)
- Each lane uses isolated systemPort range (no cross-talk)
- Failures in one lane don't affect others
- Much more stable than multi-worker mode

### Quick Start - 2 Lanes:
```bash
# Start 2 Appium servers + 2 posting processes:
python start_lanes.py --lanes 2 --accounts-file accounts_list.txt --add-folder chunk_01c

# Stop everything:
python start_lanes.py --stop-all
```

### Manual Lane Setup:
```bash
# Terminal 1 - Start Appium for lane1 (port 4723):
appium --address 127.0.0.1 --port 4723

# Terminal 2 - Start Appium for lane2 (port 4725):
appium --address 127.0.0.1 --port 4725

# Terminal 3 - Run lane1:
python posting_lane.py --lane-name lane1 --accounts-file accounts_list.txt --add-folder chunk_01c

# Terminal 4 - Run lane2:
python posting_lane.py --lane-name lane2 --accounts-file accounts_list.txt --add-folder chunk_01c
```

### Lane Config (lane_config.py):
| Lane | Appium Port | systemPort Base |
|------|-------------|-----------------|
| lane1 | 4723 | 8200 |
| lane2 | 4725 | 8300 |
| lane3 | 4727 | 8400 |

### Key Files:
| File | Purpose |
|------|---------|
| `posting_lane.py` | Single-lane posting script |
| `lane_config.py` | Lane configuration (ports, URLs) |
| `start_lanes.py` | Helper to start multiple lanes |

---

## Task Master AI Instructions

**Import Task Master's development workflow commands and guidelines, treat as if import is in the main CLAUDE.md file.**
@./.taskmaster/CLAUDE.md

Always use taskmaster to research the best solution any time I ask you to do something. Do not use web search. Use taskmaster.

## MAIN SCRIPT: posting_scheduler.py

**ALWAYS use `posting_scheduler.py` for batch posting.**

### NEVER RUN THESE SCRIPTS:
- `batch_post.py` - **ARCHIVED** - No tracking, causes duplicate posts
- `batch_post_concurrent.py` - **ARCHIVED** - Same issues
- `batch_post_ARCHIVED.py` - Old version, DO NOT USE

### Why posting_scheduler.py:
- Tracks all posted videos in `scheduler_state.json`
- Loads from `batch_results_*.csv` to prevent duplicates across restarts
- Auto-retry failed posts (configurable attempts)
- Per-account daily limits
- Per-phase timeouts (connect: 90s, instagram_post: bounded by Appium timeouts)
- Full logging to `geelark_batch.log` with phase info

### Usage:
```bash
# Add videos and accounts, then run
python posting_scheduler.py --add-folder chunk_01c --add-accounts phone1 phone2 --run

# Check status
python posting_scheduler.py --status

# Retry all failed
python posting_scheduler.py --retry-all
```

### Tracking:
- **JSON state**: `scheduler_state.json` - jobs, accounts, settings
- **CSV logs**: `batch_results_*.csv` - historical record
- **Error log**: `geelark_batch.log` - full stack traces with phase info
- **API log**: `geelark_api.log` - Geelark API responses for debugging

---

## Key Files

| File | Purpose |
|------|---------|
| `posting_scheduler.py` | **MAIN SCRIPT** - scheduler with tracking, retry, state persistence |
| `post_reel_smart.py` | Core posting logic for single phone (Appium timeout: 60s) |
| `geelark_client.py` | Geelark API wrapper (upload timeout: 60s) |
| `dashboard.py` | Real-time web dashboard (http://localhost:5000) |
| `scheduler_state.json` | Persistent state (auto-generated) |
| `geelark_batch.log` | Execution log with phase info |
| `geelark_api.log` | API response log (for Geelark support) |

## Dashboard

Real-time monitoring at http://localhost:5000

```bash
# Start dashboard (in separate terminal)
python dashboard.py
```

Features:
- Live stats: success/active/pending/failed counts
- Account status with color-coded progress
- Recent activity feed
- Live log streaming (when scheduler uses TeeWriter)

---

## Setup Requirements

### 1. Appium Server (REQUIRED for Android 15+)

```bash
# Install
npm install -g appium
appium driver install uiautomator2

# Run (must be running before posting)
appium --address 127.0.0.1 --port 4723
```

### 2. Environment Variables

```bash
# Required in .env
GEELARK_ACCESS_KEY=your_access_key
GEELARK_ACCESS_SECRET=your_access_secret
ANTHROPIC_API_KEY=your_claude_key

# Set in code (post_reel_smart.py)
ANDROID_HOME=C:\Users\asus\Downloads\android-sdk
```

### 3. ADB Platform Tools

**CRITICAL: ALL SCRIPTS MUST USE THE SAME ADB PATH AS APPIUM**

The ADB path MUST match the one in ANDROID_HOME/ANDROID_SDK_ROOT:
```
ADB_PATH = r"C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe"
```

**WHY THIS MATTERS:**
- Appium uses ANDROID_HOME/platform-tools/adb.exe
- If your script uses a DIFFERENT adb.exe, they run SEPARATE ADB servers
- The device connected via script's ADB won't be visible to Appium's ADB
- This causes "Device not in list of connected devices" errors

**NEVER use:** `C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe`
**ALWAYS use:** `C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe`

## Appium Integration (Android 15 Fix)

The original ADBKeyboard approach broke on Android 15. We migrated to Appium for all UI operations:

### Key Changes Made (Dec 2024)

1. **`dump_ui()`** - Uses `driver.page_source` instead of `adb uiautomator dump`
   - CRITICAL: Uses `root.iter()` not `iter('node')` - Appium uses class names as XML tags

2. **`tap(x, y)`** - Uses `driver.tap([(x, y)])` instead of `adb input tap`

3. **`swipe()`** - Uses `driver.swipe()` instead of `adb input swipe`

4. **`press_key()`** - Uses `driver.press_keycode()` instead of `adb input keyevent`

5. **`type_text()`** - Uses Appium's `send_keys()` - supports Unicode/emojis on all Android versions

### Why Appium?

| Feature | ADBKeyboard | Appium |
|---------|-------------|--------|
| Android 15 support | No | Yes |
| Unicode/emoji | Buggy | Native |
| UI inspection | Conflicts with Appium | Unified |
| Reliability | Flaky | Stable |

## Usage

### Single Phone Post (for testing)
```bash
python post_reel_smart.py <phone_name> <video_path> <caption>

# Example
python post_reel_smart.py reelwisdompod_ video.mp4 "Check this out!"
```

### Batch Posting (ALWAYS USE THIS)
```bash
# Using posting_scheduler.py (the ONLY correct way)
python posting_scheduler.py --add-folder chunk_01c --add-accounts phone1 phone2 --run
```

## Chunk Data Format

```
chunk_01c/
├── chunk_01c_cleaned.csv    # Caption + video shortcode mapping
├── 2bears.1cave/            # Video folder by source
│   ├── DM6m1Econ4x-2.mp4
│   └── DMbMMftoiDC-2.mp4
├── alexjones.tv/
└── ...
```

CSV columns: `Text, Image/Video link 1 (shortcode)`

## Troubleshooting

### "No UI elements found"
- Ensure Appium server is running: `curl http://127.0.0.1:4723/status`
- Check `dump_ui()` uses `root.iter()` not `root.iter('node')`

### "Device offline" in Appium
- Re-run `adb connect <ip:port>` then `adb -s <device> shell glogin <password>`
- Restart Appium server

### Caption not typed
- Verify `caption_entered` flag is only set AFTER actual typing (not from Claude's analysis)

## Testing

```bash
# Quick connectivity test
python test_full_flow_android15.py

# Full posting test
python post_reel_smart.py reelwisdompod_ video.mp4 "Test caption"
```
