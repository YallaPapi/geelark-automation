# Follow Campaign System

Automated Instagram follow campaigns using Geelark cloud phones with 100% rule-based navigation.

## Overview

The follow system allows you to run follow campaigns across multiple Instagram accounts in parallel. It uses the same infrastructure as the posting system (Geelark + Appium) but with a dedicated hybrid navigation system optimized for the follow flow.

### Key Features

- **Hybrid Navigation**: 100% rule-based screen detection (zero AI API calls)
- **Parallel Execution**: Multiple workers following targets simultaneously
- **Global Deduplication**: Prevents following the same account twice across all campaigns
- **Campaign Isolation**: Each campaign tracks its own progress independently
- **Retry Logic**: Automatic retry for transient failures

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    follow_orchestrator.py                        │
│                                                                  │
│  • Loads campaign configuration                                  │
│  • Seeds progress tracker with jobs                              │
│  • Spawns worker subprocesses                                    │
│  • Handles graceful shutdown                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ follow_worker   │ │ follow_worker   │ │ follow_worker   │
│   (Worker 0)    │ │   (Worker 1)    │ │   (Worker 2)    │
│                 │ │                 │ │                 │
│ • Appium:4723   │ │ • Appium:4725   │ │ • Appium:4727   │
│ • Claims jobs   │ │ • Claims jobs   │ │ • Claims jobs   │
│ • Executes      │ │ • Executes      │ │ • Executes      │
│   follows       │ │   follows       │ │   follows       │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│       campaigns/<campaign>/follow_progress.csv (file-locked)    │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Create Campaign Directory

```bash
mkdir -p campaigns/mycampaign
```

### 2. Create Target List

Create `campaigns/mycampaign/targets.txt` with one username per line:

```
user_to_follow_1
user_to_follow_2
user_to_follow_3
```

### 3. Run Campaign

```bash
python follow_orchestrator.py --campaign mycampaign --workers 5 --run
```

### 4. Monitor Progress

```bash
python follow_orchestrator.py --campaign mycampaign --status
```

## Command Reference

### follow_orchestrator.py

```bash
# Start campaign with N workers
python follow_orchestrator.py --campaign <name> --workers 5 --run

# Check campaign status
python follow_orchestrator.py --campaign <name> --status

# Stop all workers and phones
python follow_orchestrator.py --stop-all

# Seed progress file only (no workers)
python follow_orchestrator.py --campaign <name> --seed-only
```

**Options:**

| Flag | Description |
|------|-------------|
| `--campaign <name>` | Campaign directory name |
| `--workers N` | Number of parallel workers (default: 5) |
| `--run` | Start the workers |
| `--status` | Show current progress |
| `--stop-all` | Kill workers and stop phones |
| `--seed-only` | Initialize progress file |

## Campaign Structure

```
campaigns/
└── mycampaign/
    ├── follow_progress.csv    # Job tracking (auto-created)
    ├── targets.txt            # Target usernames to follow
    └── accounts.txt           # (Optional) Source accounts for this campaign
```

### targets.txt

One username per line (no @ symbol):

```
targetuser1
targetuser2
targetuser3
```

### follow_progress.csv

Auto-created with columns:

```csv
job_id,source_account,target_account,status,worker_id,claimed_at,completed_at,error,attempts
```

**Statuses:**
| Status | Description |
|--------|-------------|
| `pending` | Ready to be claimed |
| `claimed` | Being processed by a worker |
| `success` | Follow completed |
| `failed` | Failed permanently |
| `skipped` | Target already followed globally |

## Global Deduplication

The file `all_followed_accounts.txt` tracks all accounts ever followed across all campaigns. Before following a target:

1. Check if target exists in `all_followed_accounts.txt`
2. If yes, skip (mark as `skipped`)
3. If no, proceed with follow
4. On success, append target to `all_followed_accounts.txt`

This prevents following the same account from multiple campaigns or accounts.

## Hybrid Navigation

The follow system uses 100% rule-based navigation with zero AI API calls.

### Screen Detection

The `FollowScreenDetector` identifies the current screen:

```python
class FollowScreenType(Enum):
    HOME_FEED = "home_feed"           # Instagram home feed
    EXPLORE_PAGE = "explore_page"     # Search/explore grid
    SEARCH_INPUT = "search_input"     # Search bar focused
    SEARCH_RESULTS = "search_results" # Search results showing
    TARGET_PROFILE = "target_profile" # Target user's profile
    FOLLOW_SUCCESS = "follow_success" # Following confirmed
    ABOUT_ACCOUNT_PAGE = "about_page" # "About this account" page
    REELS_SCREEN = "reels_screen"     # Watching reels
    POPUP_DISMISSIBLE = "popup"       # Dismissible popup
    UNKNOWN = "unknown"               # Unrecognized screen
```

### Action Engine

The `FollowActionEngine` returns the action based on screen type:

| Screen | Action |
|--------|--------|
| HOME_FEED | Tap search tab |
| EXPLORE_PAGE | Tap search bar |
| SEARCH_INPUT | Type target username |
| SEARCH_RESULTS | Tap target in results |
| TARGET_PROFILE | Tap follow button |
| FOLLOW_SUCCESS | Complete |
| POPUP_DISMISSIBLE | Dismiss popup |

### Flow Example

```
1. HOME_FEED → tap search tab
2. EXPLORE_PAGE → tap search bar
3. SEARCH_INPUT → type "targetuser"
4. SEARCH_RESULTS → tap @targetuser row
5. TARGET_PROFILE → tap Follow button
6. FOLLOW_SUCCESS → done!
```

## Progress Tracking

### File Locking

`follow_progress.csv` uses file locking for process-safe access:

```python
from follow_tracker import FollowTracker

tracker = FollowTracker("campaigns/mycampaign")

# Claim next job (atomic)
job = tracker.claim_next_job(worker_id=0)

# Update status (atomic)
tracker.update_job_status(job_id, "success", worker_id=0)
```

### Stats

```python
stats = tracker.get_stats()
# Returns: {"pending": 50, "claimed": 2, "success": 45, "failed": 3, "skipped": 10}
```

## Error Handling

### Retryable Errors

- Network timeout
- Appium session crash
- Phone boot failure

These get `retry_at` timestamp and are picked up again later.

### Non-Retryable Errors

- Account suspended
- Target doesn't exist
- Rate limited (action blocked)

These are marked `failed` immediately.

## Troubleshooting

### "Could not find @username in search results"

1. Check if username exists on Instagram
2. Check if account is private/blocked
3. Verify search bar text detection is working

### Workers Not Claiming Jobs

1. Check `follow_progress.csv` has `pending` jobs
2. Verify file lock isn't stuck (delete `.lock` file)
3. Check worker logs in `logs/follow_worker_N.log`

### Phone Not Stopping

```bash
# Force stop all phones
python -c "
from geelark_client import GeelarkClient
client = GeelarkClient()
for page in range(1, 20):
    result = client.list_phones(page=page, page_size=100)
    for phone in result['items']:
        if phone['status'] == 1:
            client.stop_phone(phone['id'])
            print(f'Stopped: {phone[\"serialName\"]}')
    if len(result['items']) < 100:
        break
"
```

## File Reference

| File | Purpose |
|------|---------|
| `follow_orchestrator.py` | Main entry point, spawns workers |
| `follow_worker.py` | Worker process, claims and executes jobs |
| `follow_single.py` | Single follow execution logic |
| `follow_tracker.py` | CSV-based progress tracking |
| `hybrid_follow_navigator.py` | Hybrid navigation coordinator |
| `follow_screen_detector.py` | Screen type detection |
| `follow_action_engine.py` | Rule-based action decisions |
| `all_followed_accounts.txt` | Global follow deduplication |

## Performance

Typical performance with 5 workers:

- ~15-20 seconds per follow (including phone boot)
- ~180-240 follows per hour
- Zero AI API costs (100% rule-based)
