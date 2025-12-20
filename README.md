# Geelark Instagram Automation

Automated Instagram Reel posting and account following on Geelark cloud phones using AI-driven UI navigation.

## Features

- **AI-Driven Navigation**: Claude analyzes UI and decides actions - no hardcoded coordinates
- **Parallel Workers**: Run 5+ simultaneous posting/following operations
- **Campaign System**: Manage multiple independent campaigns with separate accounts and content
- **Appium Integration**: Full Android 15+ support with Unicode/emoji captions
- **Smart Retry**: Automatic retry for infrastructure errors, skip account errors
- **Progress Tracking**: File-locked CSV tracking prevents duplicates and enables resume

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                              │
│  (parallel_orchestrator.py / follow_orchestrator.py)        │
│  - Spawns N worker processes                                 │
│  - Coordinates shutdown & phone cleanup                      │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┬───────────────┐
         │               │               │               │
    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
    │ Worker 0│    │ Worker 1│    │ Worker 2│    │ Worker 3│
    │ Port 4723│   │ Port 4725│   │ Port 4727│   │ Port 4729│
    └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘
         │               │               │               │
         └───────────────┴───────┬───────┴───────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   progress.csv          │
                    │   (file-locked)         │
                    │   Shared job queue      │
                    └─────────────────────────┘
```

## Quick Start

### Prerequisites

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Appium
npm install -g appium
appium driver install uiautomator2
```

### Environment Setup

Create `.env` file:
```bash
GEELARK_TOKEN=your_geelark_token
ANTHROPIC_API_KEY=your_claude_api_key
```

### Run Posting (5 Parallel Workers)

```bash
python parallel_orchestrator.py --workers 5 --run
```

### Run Following (5 Parallel Workers)

```bash
python follow_orchestrator.py --campaign podcast --workers 5 --run
```

## How It Works

### The AI Loop

Every action uses the same reliable pattern:

```python
for step in range(max_steps):
    # 1. Dump UI hierarchy via Appium
    elements = driver.page_source

    # 2. Ask Claude what to do
    action = claude.analyze(elements, current_state)

    # 3. Execute action
    if action == 'tap':
        driver.tap(coordinates)
    elif action == 'type':
        driver.send_keys(text)
    elif action == 'done':
        return success
```

### Posting Flow

1. Connect to Geelark phone via ADB
2. Upload video to phone's Downloads folder
3. Open Instagram
4. Navigate: Create → Reel → Select Video → Next → Caption → Share
5. AI handles each screen transition
6. Verify success, cleanup, disconnect

### Following Flow

1. Connect to Geelark phone via ADB
2. Open Instagram
3. Navigate: Search → Type Username → Enter → Tap Profile → Tap Follow
4. Verify "Following" button appears
5. Disconnect

## Project Structure

### Core Posting System

| File | Purpose |
|------|---------|
| `parallel_orchestrator.py` | **Main entry** - spawns parallel workers |
| `parallel_worker.py` | Individual worker process |
| `post_reel_smart.py` | Core posting logic with AI navigation |
| `progress_tracker.py` | File-locked CSV job tracking |

### Follow System

| File | Purpose |
|------|---------|
| `follow_orchestrator.py` | Spawn parallel follow workers |
| `follow_worker.py` | Individual follow worker |
| `follow_single.py` | Core follow logic with AI navigation |
| `follow_tracker.py` | File-locked follow job tracking |

### Infrastructure

| File | Purpose |
|------|---------|
| `config.py` | Centralized configuration |
| `geelark_client.py` | Geelark API wrapper |
| `appium_server_manager.py` | Appium lifecycle management |
| `claude_analyzer.py` | Claude AI for UI analysis |
| `flow_logger.py` | Step-by-step flow logging |

## Campaign Structure

```
campaigns/
├── podcast/
│   ├── accounts.txt           # Posting accounts (one per line)
│   ├── captions.csv           # Video data (shortcode, caption)
│   ├── followers.txt          # Target accounts to follow
│   ├── progress.csv           # Auto-created: posting jobs
│   ├── follow_progress.csv    # Auto-created: follow jobs
│   └── videos/
│       └── source_channel/
│           ├── ABC123-1.mp4
│           └── DEF456-1.mp4
│
└── viral/
    └── (same structure)
```

### CSV Formats

**Podcast Format:**
```csv
Text,Image/Video link 1 (shortcode)
"Caption text here",ABC123
"Another caption",DEF456
```

**Viral Format:**
```csv
filename,onscreen_text,post_caption
ABC123-1.mp4,"On-screen text","Post caption"
```

## Commands

### Posting

```bash
# Start parallel posting (recommended)
python parallel_orchestrator.py --workers 5 --run

# Check status
python parallel_orchestrator.py --status

# Stop all workers and phones
python parallel_orchestrator.py --stop-all

# Start new day (archive old progress)
python parallel_orchestrator.py --reset-day

# Legacy single-threaded mode
python posting_scheduler.py --add-folder chunk_01c --run

# Single post test
python post_reel_smart.py <phone_name> <video_path> "<caption>"
```

### Following

```bash
# Start parallel following
python follow_orchestrator.py --campaign podcast --workers 5 --run

# With custom settings
python follow_orchestrator.py --campaign podcast --workers 5 --max-follows 2 --delay 15 --run

# Check status
python follow_orchestrator.py --campaign podcast --status

# Reset progress
python follow_orchestrator.py --campaign podcast --reset

# Single follow test
python follow_single.py <phone_name> <target_username>
```

### Dashboard

```bash
# Start web dashboard
python dashboard.py
# Open http://localhost:5000
```

## Configuration

### config.py Settings

```python
class Config:
    # Paths
    ADB_PATH = r"C:\...\platform-tools\adb.exe"
    ANDROID_HOME = r"C:\...\android-sdk"

    # Appium
    DEFAULT_APPIUM_PORT = 4723
    APPIUM_TIMEOUT = 120

    # Execution
    MAX_WORKERS = 5
    MAX_STEPS = 30
    MAX_POSTS_PER_ACCOUNT_PER_DAY = 2

    # Retry
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 300
```

### Per-Account Daily Limits

Enforced at two levels:
1. **Seeding**: Only add jobs for accounts under limit
2. **Claiming**: Verify limit before claiming job

## State Files

| File | Purpose |
|------|---------|
| `scheduler_state.json` | Account posting history |
| `parallel_progress.csv` | Current posting jobs |
| `follow_progress.csv` | Current follow jobs |
| `all_followed_accounts.txt` | Accounts already followed (global) |
| `accounts.txt` | Approved posting accounts |

### scheduler_state.json Structure

```json
{
  "accounts": [
    {
      "name": "podclipcrafters",
      "last_post_date": "2025-12-20",
      "posts_today": 1,
      "total_posts": 150,
      "consecutive_failures": 0,
      "cooldown_until": ""
    }
  ]
}
```

## Error Handling

### Error Categories

| Category | Examples | Retry? |
|----------|----------|--------|
| **Account** | Suspended, logged out, captcha | No |
| **Infrastructure** | ADB timeout, Appium crash | Yes (3x) |

### Automatic Recovery

- **Stuck Detection**: If same action 3x, press back
- **App Crash**: Reopen Instagram
- **Wrong Screen**: Navigate back to expected state
- **Loop Detection**: Max 30 steps per operation

## Performance

### Posting (5 Workers)

- ~3-4 posts per minute across all workers
- ~60-90 seconds per post
- 85-95% success rate

### Following (5 Workers)

- ~3-4 follows per minute across all workers
- ~60-90 seconds per follow
- 92% success rate

## Appium Integration (Android 15+)

The project migrated from ADBKeyboard to Appium for Android 15+ compatibility:

| Feature | Old (ADBKeyboard) | New (Appium) |
|---------|-------------------|--------------|
| Text Input | Buggy on Android 15 | Native support |
| UI Dump | `uiautomator dump` | `driver.page_source` |
| Tap | `adb input tap` | `driver.tap()` |
| Unicode/Emoji | Encoding issues | Full support |

## Troubleshooting

### "Phone not found"
- Check phone name matches exactly (case-sensitive)
- Phone might be on different page in Geelark

### "ADB connection timeout"
- Phone might be slow to start
- Check Geelark dashboard for phone status

### "Max steps reached"
- AI got stuck - check flow logs in `flow_analysis/`
- Usually recovers on retry

### "Account error"
- Phone needs manual intervention
- Check for captcha, re-login required

### Appium Issues
- Ensure Appium server is running: `appium --address 127.0.0.1 --port 4723`
- Check driver installed: `appium driver list`

## Flow Analysis

All operations are logged to `flow_analysis/*.jsonl` for debugging:

```json
{"event": "step", "step": 1, "screen": "home_feed", "action": "tap", "element_index": 34}
{"event": "step", "step": 2, "screen": "explore_page", "action": "tap", "element_index": 24}
{"event": "success", "total_steps": 6, "duration_seconds": 67}
```

Analyze with:
```bash
python analyze_logs.py
```

## Critical Rules

### Phone Management
**Always stop phones when done** - they cost money while running.

```python
# Stop all phones
from geelark_client import GeelarkClient
client = GeelarkClient()
for page in range(1, 20):
    result = client.list_phones(page=page, page_size=100)
    for phone in result['items']:
        if phone['status'] == 1:
            client.stop_phone(phone['id'])
```

### Progress Files
- **Never delete** `parallel_progress.csv` manually
- Use `--reset-day` to start fresh
- File locking prevents duplicates

### Account Safety
- Only use accounts from `accounts.txt`
- Respect daily posting limits
- Don't run same account on multiple workers

## API Reference

### Geelark API (geelark_client.py)

```python
client = GeelarkClient()

# Phone management
client.list_phones(page=1, page_size=100)
client.start_phone(phone_id)
client.stop_phone(phone_id)

# ADB
client.enable_adb(phone_id)
client.get_adb_info(phone_id)  # Returns {ip, port, password}

# File upload
url = client.upload_file_to_geelark('video.mp4')
result = client.upload_file_to_phone(phone_id, url)
client.wait_for_upload(result['taskId'])
```

### Claude API (claude_analyzer.py)

```python
analyzer = ClaudeUIAnalyzer()
action = analyzer.analyze(
    elements=elements,
    caption="My caption",
    video_uploaded=True,
    caption_entered=False
)
# Returns: {"action": "tap", "element_index": 5, "reason": "..."}
```

## License

Private repository - all rights reserved.
