# Claude Code Instructions

## CRITICAL: ALWAYS READ ENTIRE FILES

**When reviewing Python scripts, ALWAYS read the ENTIRE file.**
- Use `Read` tool WITHOUT offset/limit to get the whole file
- Scripts with 1000+ lines need FULL review to understand the logic
- NEVER read just 50-80 lines - that leads to wrong conclusions
- Be thorough, not lazy

---

## CRITICAL: LIVE TESTS OVER TEST SCRIPTS

**ALWAYS prioritize live tests with actual functionality over creating test scripts.**

### DO:
- Test directly with `python posting_scheduler.py --run` or `python parallel_orchestrator.py --run`
- Use real accounts, real videos, real captions
- Monitor logs in real-time
- Fix issues as they appear in production

### DO NOT:
- Create `test_*.py` scripts to test isolated functionality
- Pollute the project with debugging scripts
- Write unit tests when you could just run the actual code
- Add test files that won't be maintained

### Why:
- Test scripts get stale and don't reflect real behavior
- Live tests expose real integration issues
- The actual scripts ARE the tests

---

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

## CRITICAL: ACCOUNT MANAGEMENT

**ONLY USE ACCOUNTS FROM accounts.txt - NEVER USE RANDOM GEELARK ACCOUNTS**

### Single Source of Truth:
- **`accounts.txt`** - List of 82 approved accounts (one per line)
- **`scheduler_state.json`** - Tracks posting history per account (posts_today, last_post_date, failures, cooldowns)

### STRICT RULES:
1. **NEVER post to accounts not in accounts.txt** - even if they exist in Geelark
2. **NEVER post multiple times to the same account in one batch** - accounts will get BANNED
3. **ALWAYS check scheduler_state.json for posting history** before selecting accounts
4. **ALWAYS verify account exists in accounts.txt** before using it

### How Accounts Are Tracked:
```json
// scheduler_state.json -> accounts array
{
  "name": "podclipcrafters",
  "last_post_date": "2025-12-12",
  "posts_today": 1,
  "total_posts": 5,
  "total_failures": 2,
  "consecutive_failures": 0,
  "cooldown_until": ""
}
```

### Before Running ANY Batch:
```bash
# 1. Verify accounts.txt exists and has 82 accounts
wc -l accounts.txt

# 2. Check which accounts have been posted to today
python -c "
import json
from datetime import date
with open('scheduler_state.json', 'r') as f:
    state = json.load(f)
today = str(date.today())
posted_today = [a['name'] for a in state['accounts'] if a.get('last_post_date') == today]
print(f'Posted today ({len(posted_today)}): {posted_today}')
"
```

### DO NOT:
- Use the 173+ Geelark accounts (bubblegumlampspin, crookedwafflezing, etc.)
- Those are NOT our posting accounts
- Only the 82 accounts in accounts.txt are authorized for posting

---

## CRITICAL: PROGRESS FILE MANAGEMENT (parallel_progress.csv)

**NEVER DELETE THE PROGRESS FILE MANUALLY. EVER.**

### The Daily Ledger Rule:
- `parallel_progress.csv` is the **daily ledger** tracking all posts
- It tracks which accounts have successfully posted TODAY
- Deleting it = wiping the success history = accounts can get multiple posts
- This is how you get 6 posts on one account in one day

### Per-Account Daily Limits:
- Each account can have at most `max_posts_per_account_per_day` successful posts (default: 1)
- This is enforced at BOTH seeding time AND claim time (defense in depth)
- Once an account has N successes, it is EXCLUDED from all future jobs that day

### Starting a New Day:
```bash
# ONLY use --reset-day to start fresh for a new posting day
python parallel_orchestrator.py --reset-day
```
This will:
1. Check no orchestrators are running
2. Archive current progress to `parallel_progress_YYYYMMDD.csv`
3. Create a fresh empty progress file

### NEVER Do This:
```bash
# NEVER delete the progress file manually
rm parallel_progress.csv  # WRONG - NEVER DO THIS
del parallel_progress.csv  # WRONG - NEVER DO THIS

# NEVER delete mid-day to "fix" something
# NEVER delete because "it seems corrupt"
# NEVER delete to "start fresh" during the day
```

### Check Before Running Orchestrator:
```bash
# Always check for other running orchestrators first
python parallel_orchestrator.py --status
```
The orchestrator will automatically detect and refuse to start if another is running.

---

## CRITICAL: CODE REVIEW IMPLEMENTATION

**If conversation gets compacted, CHECK THESE FIRST:**
1. Run `task-master list --status pending` to see pending tasks
2. Read `reviews/review1.txt` for full implementation details
3. Tasks 21-24 contain the review implementation plan

**Review Tasks (in order of implementation):**
- Task 21: Port retry logic from PostingScheduler
- Task 22: Fix per-account daily cap enforcement
- Task 23: Add ADB/Appium lifecycle state machine
- Task 24: Enforce strict worker-phone-Appium bindings

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

Path: `C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe`

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
