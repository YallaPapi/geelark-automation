# Instagram Follow Feature PRD

## Overview

Build a following feature for Instagram automation that mirrors the posting feature's architecture EXACTLY. This feature will follow target accounts from `followers.txt` using the podcast campaign accounts.

**CRITICAL CONSTRAINT**: Do NOT modify any existing files. Only create NEW files.

## Requirements

### Functional Requirements

1. Load target accounts from `campaigns/podcast/followers.txt` (315 accounts)
2. Distribute targets evenly across podcast campaign accounts
3. Each campaign account follows X targets per day (configurable, default 1-2)
4. Track followed accounts to prevent re-following (like `all_posted_videos.txt` for posts)
5. Use AI-driven navigation with Claude to navigate Instagram UI
6. Run in parallel with multiple workers (matching posting architecture)

### Non-Functional Requirements

1. **Architecture parity**: Must mirror the posting system exactly
2. **No modifications**: Create only NEW files - never modify existing ones
3. **Reuse imports**: Import and use existing modules (don't copy/modify them)

## Files to Create

### 1. follow_tracker.py (mirrors progress_tracker.py)

Purpose: Track follow progress using file-locked CSV.

Key patterns to copy from `progress_tracker.py`:
- File locking with portalocker
- Atomic writes via temp file + rename
- Job claiming with worker_id tracking
- Status transitions: pending -> claimed -> success/failed/retrying
- Error classification (account vs infrastructure)
- Non-retryable error categories (suspended, captcha, logged_out, action_blocked)

CSV columns for `campaigns/{campaign}/follow_progress.csv`:
- `job_id`: Unique identifier (e.g., `{account}_{target}`)
- `account`: Campaign account doing the following
- `target`: Target username to follow
- `status`: pending/claimed/success/failed/retrying
- `worker_id`: Which worker processed this
- `claimed_at`: Timestamp when claimed
- `completed_at`: Timestamp when completed
- `error`: Error message if failed
- `attempts`: Retry attempt count
- `max_attempts`: Max retry attempts (default 3)
- `retry_at`: When to retry
- `error_type`: Classification (suspended, adb_timeout, etc.)
- `error_category`: account or infrastructure

Track already-followed accounts in `all_followed_accounts.txt` (one per line) to prevent re-following.

Methods to implement (mirror progress_tracker.py):
- `__init__(progress_file, followed_file, lock_timeout=30.0)`
- `seed_from_targets(targets_file, accounts, max_follows_per_account)` - Distribute targets across accounts
- `_load_followed_accounts()` - Load from all_followed_accounts.txt
- `claim_next_job(worker_id, max_follows_per_account)` - Claim a pending job
- `update_job_status(job_id, status, worker_id, error=None, ...)` - Update job status
- `_classify_error(error)` - Same classification as progress_tracker
- `get_stats()` - Return pending/claimed/success/failed counts
- `is_already_followed(target)` - Check if target already followed
- `mark_followed(target)` - Add to followed accounts file

### 2. follow_single.py (mirrors post_reel_smart.py)

Purpose: Core follow logic using AI-driven navigation.

Key patterns to copy from `post_reel_smart.py`:
- Use `DeviceConnectionManager` for all connection lifecycle (import, don't modify)
- Use `ClaudeUIAnalyzer` for AI analysis (import, don't modify)
- Use `AppiumUIController` for UI interactions (import, don't modify)
- Expose properties: `phone_id`, `device`, `appium_driver`, `system_port`, `appium_url`
- `connect()` method that delegates to `self._conn.connect()`
- `cleanup()` method that delegates to `self._conn.disconnect()`
- `dump_ui()` method same as posting
- `detect_error_state(elements)` - Same error patterns

Class structure:
```python
class SmartInstagramFollower:
    def __init__(self, phone_name, system_port=8200, appium_url=None):
        self._conn = DeviceConnectionManager(...)
        self.client = self._conn.client
        self._analyzer = ClaudeUIAnalyzer()
        # State tracking
        self.search_opened = False
        self.username_typed = False
        self.profile_opened = False
        self.follow_clicked = False
        # Error tracking
        self.last_error_type = None
        self.last_error_message = None

    def connect(self):
        """Delegates to DeviceConnectionManager.connect()"""
        return self._conn.connect()

    def follow_account(self, target_username, max_steps=30):
        """Main follow loop - navigate to target and follow.
        NOTE: connect() must be called BEFORE this method.
        """
        # 1. Open Instagram
        # 2. Tap Search icon
        # 3. Tap search bar
        # 4. Type target username
        # 5. Tap matching account
        # 6. Tap Follow button
        # 7. Verify success (button changed to Following/Requested)

    def cleanup(self):
        """Delegates to DeviceConnectionManager.disconnect()"""
        self._conn.disconnect()
```

Follow flow (AI-driven):
1. Open Instagram: `am force-stop`, `monkey -p com.instagram.android 1`
2. Tap Search icon (magnifying glass at bottom)
3. Tap search bar at top
4. Type target username (no @)
5. Tap matching account from results
6. Tap Follow button
7. Verify: button should change to "Following" or "Requested"

Handle variations:
- Already following: detect "Following" button, return success
- Private account: "Requested" is success
- Rate limit: detect "try again later", classify as action_blocked
- No results: scroll/search again or fail
- Popups: dismiss with back or tap dismiss button

### 3. follow_worker.py (mirrors parallel_worker.py EXACTLY)

Purpose: Worker process that spawns Appium and processes follow jobs.

Key patterns to copy from `parallel_worker.py`:
- Import `AppiumServerManager` (don't modify)
- Import `DeviceConnectionManager` helpers (don't modify)
- Signal handlers for clean shutdown
- `setup_worker_logging(worker_config)` - Same pattern
- `kill_appium_sessions(appium_url, logger)` - COPY this function exactly
- `stop_phone_by_name(phone_name, logger)` - COPY this function exactly

Worker flow (must match parallel_worker.py EXACTLY):
```python
def execute_follow_job(job, worker_config, config, logger, tracker=None, worker_id=None):
    # 1. Kill orphaned Appium sessions
    kill_appium_sessions(worker_config.appium_url, logger)

    # 2. Verify job is still valid (if tracker provided)
    if tracker and worker_id is not None:
        is_valid, error = tracker.verify_job_before_follow(job_id, worker_id)
        if not is_valid:
            return False, error, 'infrastructure', 'verification_failed'

    # 3. Create follower with worker's Appium URL and systemPort
    follower = SmartInstagramFollower(
        phone_name=account,
        system_port=worker_config.system_port,
        appium_url=worker_config.appium_url
    )

    # 4. Connect to device FIRST (same pattern as posting)
    follower.connect()

    # 5. Execute the follow
    success = follower.follow_account(target)

    # 6. Cleanup and return
    finally:
        follower.cleanup()
        stop_phone_by_name(account, logger)

def run_worker(worker_id, config, campaign, progress_file, ...):
    # 1. Setup logging
    # 2. Initialize FollowTracker
    # 3. Start Appium via AppiumServerManager
    # 4. Main loop:
    #    - Check for remaining jobs
    #    - Ensure Appium healthy
    #    - Release stale claims
    #    - Claim job
    #    - Execute job
    #    - Update status
    #    - Delay between jobs
    # 5. Cleanup
```

### 4. follow_orchestrator.py (mirrors parallel_orchestrator.py)

Purpose: Orchestrate batch following with multiple workers.

Key patterns to copy from `parallel_orchestrator.py`:
- Use `ParallelConfig` and `get_config()` from parallel_config (import, don't modify)
- Use `CampaignConfig.from_folder()` to load campaign (import, don't modify)
- Spawn worker subprocesses with staggered starts
- Signal handlers for clean shutdown
- Process monitoring and restart logic

Orchestrator flow:
```python
def run_orchestrator(campaign, workers, max_follows_per_account, ...):
    # 1. Load campaign config
    campaign_config = CampaignConfig.from_folder(f"campaigns/{campaign}")

    # 2. Get campaign accounts
    accounts = campaign_config.get_accounts()

    # 3. Load targets from followers.txt
    targets = load_targets(targets_file)

    # 4. Initialize FollowTracker
    tracker = FollowTracker(progress_file, followed_file)

    # 5. Seed jobs if needed
    if not tracker.exists():
        tracker.seed_from_targets(targets, accounts, max_follows_per_account)

    # 6. Create parallel config
    config = get_config(num_workers=workers)

    # 7. Spawn workers (staggered start)
    for worker_id in range(workers):
        spawn_worker(worker_id, ...)
        time.sleep(60)  # Stagger by 60s

    # 8. Monitor workers and handle shutdown
```

Command-line interface:
```bash
python follow_orchestrator.py --campaign podcast --workers 5 --max-follows 2 --run
python follow_orchestrator.py --campaign podcast --status
python follow_orchestrator.py --campaign podcast --reset
```

## Integration Points

### Existing modules to IMPORT (never modify):
- `config.py` - `Config`, `CampaignConfig`, `setup_environment`
- `parallel_config.py` - `ParallelConfig`, `WorkerConfig`, `get_config`
- `appium_server_manager.py` - `AppiumServerManager`, `AppiumServerError`
- `device_connection.py` - `DeviceConnectionManager`, `wait_for_adb_device`, etc.
- `geelark_client.py` - `GeelarkClient`
- `claude_analyzer.py` - `ClaudeUIAnalyzer`
- `appium_ui_controller.py` - `AppiumUIController`

### Campaign structure:
```
campaigns/podcast/
  accounts.txt          # Campaign accounts (one per line)
  followers.txt         # Target accounts to follow (one per line)
  follow_progress.csv   # Progress tracking (created by follow_tracker)
  logs/                 # Worker logs
    follow_worker_0.log
    follow_worker_1.log
    ...
```

### Global tracking:
- `all_followed_accounts.txt` - All accounts ever followed (prevents re-following)

## AI Prompt for Follow Navigation

Use similar structure to `claude_analyzer.py` but for follow flow:

```
You are automating Instagram to follow a target account.

TARGET USERNAME TO FOLLOW: {target_username}

CURRENT STATE:
- Search opened: {search_opened}
- Username typed: {username_typed}
- Profile opened: {profile_opened}
- Follow clicked: {follow_clicked}

UI ELEMENTS:
{elements_str}

FOLLOW FLOW:
1. From home feed, tap Search icon (magnifying glass at bottom)
2. On search/explore screen, tap the search bar at top
3. Type the target username
4. From search results, tap on the exact matching account
5. On profile page, tap the "Follow" button
6. Verify: button should change to "Following" or "Requested"

YOUR TASK:
Analyze the current screen and decide the next action.

RESPOND IN THIS JSON FORMAT ONLY:
{
    "screen": "description of current screen",
    "action": "tap" | "type" | "back" | "scroll_down" | "wait" | "done" | "error",
    "element_index": <index if tapping>,
    "text": "<text if typing>",
    "reason": "why this action",
    "search_opened": true/false,
    "username_typed": true/false,
    "profile_opened": true/false,
    "follow_clicked": true/false
}

IMPORTANT:
- Use "done" when you see "Following" or "Requested" button (success!)
- Use "error" if you detect action blocked, logged out, etc.
- When typing username, type ONLY the username without @
```

## Error Classification

Mirror `progress_tracker.py` error classification:

Account errors (non-retryable):
- terminated, suspended, disabled
- verification, logged_out
- action_blocked, banned

Infrastructure errors (retryable):
- adb_timeout, appium_crash
- connection_dropped, claude_stuck
- glogin_expired, phone_error

## Testing

1. After implementation, verify posting still works:
```bash
python parallel_orchestrator.py --status
```

2. Test follow feature:
```bash
# Start with 5 workers, 2 follows per account
python follow_orchestrator.py --campaign podcast --workers 5 --max-follows 2 --run

# Check status
python follow_orchestrator.py --campaign podcast --status
```

## Success Criteria

1. Follow feature runs without modifying any existing files
2. Posting feature continues to work unchanged
3. Workers correctly spawn Appium servers
4. Workers correctly connect to devices
5. AI navigation successfully follows target accounts
6. Progress tracking works with file locking
7. Error classification matches posting system
8. Clean shutdown on Ctrl+C stops all workers and phones
