# Task ID: 50

**Title:** Generate comprehensive codebase documentation in docs/ folder

**Status:** done

**Dependencies:** 28 ✓, 48 ✓, 49 ✓

**Priority:** medium

**Description:** Create a structured docs/ folder containing README.md (project overview, setup, usage), API.md (GeelarkClient methods), MODULES.md (SmartInstagramPoster, DeviceConnectionManager, ProgressTracker, ParallelOrchestrator), and CONFIG.md (Config class reference).

**Details:**

## Implementation Plan

### 1. Create docs/ folder structure:
```
docs/
├── README.md              # Project overview, setup, quick start
├── API.md                 # GeelarkClient API reference
├── MODULES.md             # Core module documentation
├── CONFIG.md              # Configuration reference
└── ARCHITECTURE.md        # System architecture diagram (optional)
```

### 2. docs/README.md - Project Overview
Include:
- **Project Description**: AI-driven Instagram Reel posting automation for Geelark cloud phones
- **Core Concept**: The UI dump → Claude analysis → tap execution loop (from existing README.md:7-17)
- **Quick Start**: 
  - Prerequisites (Python 3.8+, Node.js for Appium, Geelark API access, Anthropic API key)
  - Environment setup (.env file with GEELARK_TOKEN, ANTHROPIC_API_KEY)
  - Install dependencies (pip, npm for appium)
- **Usage Examples**:
  - Parallel posting: `python parallel_orchestrator.py --workers 5 --run`
  - Single post: `python post_reel_smart.py <phone> <video> <caption>`
  - Status check: `python parallel_orchestrator.py --status`
- **Key Files Table**: Reference parallel_orchestrator.py, parallel_worker.py, post_reel_smart.py, geelark_client.py, device_connection.py, progress_tracker.py, config.py
- **Chunk Data Format**: CSV + video folder structure

### 3. docs/API.md - GeelarkClient API Reference
Document each method from geelark_client.py (lines 111-285):
- **Authentication**: `__init__(token)` - credential validation, connection pooling
- **Phone Management**:
  - `list_phones(page, page_size, group_name)` → Returns {total, items[{id, serialName, status}]}
  - `get_phone_status(phone_ids)` → Returns {successDetails[{id, status}]}
  - `start_phone(phone_id)` → Returns {successAmount, successDetails}
  - `stop_phone(phone_id)` → Stops cloud phone
- **ADB Control**:
  - `enable_adb(phone_id)` → Enables ADB on phone
  - `disable_adb(phone_id)` → Disables ADB
  - `get_adb_info(phone_id)` → Returns {ip, port, pwd}
- **File Operations**:
  - `get_upload_url(file_type)` → Returns {uploadUrl, resourceUrl}
  - `upload_file_to_geelark(local_path)` → Returns resourceUrl
  - `upload_file_to_phone(phone_id, file_url)` → Returns {taskId}
  - `wait_for_upload(task_id, timeout)` → Polls until complete
- **Utilities**:
  - `screenshot(phone_id)`, `wait_for_screenshot(phone_id, timeout)`
  - `set_root_status(phone_id, enable)`
  - `one_click_new_device(phone_id, change_brand_model)` - WARNING: Resets phone!
- **Error Handling**: GeelarkCredentialError, DEFAULT_HTTP_TIMEOUT=30s
- **Response Format Examples**: Show JSON structure for each endpoint

### 4. docs/MODULES.md - Core Component Documentation

#### 4.1 SmartInstagramPoster (post_reel_smart.py)
- **Purpose**: AI-powered Instagram posting orchestration
- **Composition Pattern**: Uses DeviceConnectionManager, ClaudeUIAnalyzer, AppiumUIController
- **Key Methods**:
  - `connect()` → Full connection flow (find phone, start, ADB, Appium)
  - `post(video_path, caption, max_steps, humanize)` → Main posting workflow
  - `dump_ui()` → Returns (elements[], xml_str) via Appium page_source
  - `analyze_ui(elements, caption)` → Claude decides next action
  - `cleanup()` → Stop phone, disable ADB
- **State Machine**: video_uploaded → caption_entered → share_clicked
- **Action Dispatch Table** (lines 583-595): home, open_instagram, tap, back, scroll_down, scroll_up
- **Error Detection** (lines 390-452): suspended, captcha, action_blocked, logged_out, app_update, rate_limited
- **Humanization**: _humanize_scroll_feed, _humanize_view_story, _humanize_scroll_reels

#### 4.2 DeviceConnectionManager (device_connection.py)
- **Purpose**: Encapsulates phone connection lifecycle
- **Initialization**: `__init__(phone_name, system_port, appium_url, geelark_client)`
- **Connection Flow**:
  1. `find_phone()` → Search Geelark API for phone by name
  2. `start_phone_if_needed(phone)` → Boot if status != 0
  3. `enable_adb_with_retry(max_retries=3)` → Enable ADB with verification
  4. `connect_adb(adb_info)` → ADB connect + glogin authentication
  5. `connect_appium(retries=3)` → Create Appium WebDriver session
- **Static Helpers** (lines 27-127): wait_for_adb_device(), is_adb_device_alive(), reconnect_adb_device()
- **Reconnection**: reconnect_appium(), is_uiautomator2_crash() detection

#### 4.3 ProgressTracker (progress_tracker.py)
- **Purpose**: Process-safe CSV job tracking with file locking
- **CSV Schema** (lines 78-82): job_id, account, video_path, caption, status, worker_id, claimed_at, completed_at, error, attempts, max_attempts, retry_at, error_type
- **Status Values**: pending, claimed, success, failed, skipped, retrying
- **Key Methods**:
  - `seed_from_scheduler_state(state_file, accounts, redistribute, max_posts_per_account_per_day)` → Initialize jobs
  - `claim_next_job(worker_id, max_posts_per_account_per_day)` → Atomic job claiming with account-level locking
  - `update_job_status(job_id, status, worker_id, error)` → Automatic retry logic
  - `claim_retry_job(worker_id)` → Claim jobs ready for retry
  - `retry_all_failed(include_non_retryable)` → Bulk reset failed jobs
- **Error Classification** (lines 97-103): ERROR_PATTERNS dict for suspended, captcha, loggedout, actionblocked, banned
- **Defense in Depth**: Daily limit enforced at seeding AND claim time

#### 4.4 ParallelOrchestrator (parallel_orchestrator.py)
- **Purpose**: Main entry point for parallel batch posting
- **Architecture** (lines 23-31): ASCII diagram showing orchestrator → workers → Appium → phones
- **CLI Commands**:
  - `--workers N --run` → Start N parallel workers
  - `--status` → Show progress and Appium status
  - `--stop-all` → Full cleanup (phones, ports, ADB)
  - `--reset-day` → Archive progress file for new day
  - `--seed-only` → Seed progress without running
- **Safety Features**:
  - `check_for_running_orchestrators()` → Prevent duplicate orchestrators
  - `full_cleanup()` → Stop phones, kill ports, disconnect ADB
  - `validate_progress_file()` → Detect empty/corrupt files (no auto-delete)
- **Worker Lifecycle**: start_all_workers() staggers by 60s, monitor_workers() with periodic status

### 5. docs/CONFIG.md - Configuration Reference
Document Config class from config.py (lines 23-155):

#### 5.1 Paths
- `ANDROID_SDK_PATH`: r"C:\Users\asus\Downloads\android-sdk"
- `ADB_PATH`: Derived from SDK path
- `PROJECT_ROOT`: Script directory

#### 5.2 Appium Settings
- `APPIUM_BASE_PORT`: 4723 (workers use 4723, 4725, 4727...)
- `DEFAULT_APPIUM_URL`: "http://127.0.0.1:4723"

#### 5.3 Parallel Execution
- `DEFAULT_NUM_WORKERS`: 3
- `MAX_WORKERS`: 10
- `SYSTEM_PORT_BASE`: 8200 (ranges: 8200-8209, 8210-8219...)

#### 5.4 Job Execution
- `MAX_POSTS_PER_ACCOUNT_PER_DAY`: 1
- `DELAY_BETWEEN_JOBS`: 10 seconds
- `JOB_TIMEOUT`: 300 seconds
- `SHUTDOWN_TIMEOUT`: 60 seconds

#### 5.5 Retry Settings
- `MAX_RETRY_ATTEMPTS`: 3
- `RETRY_DELAY_MINUTES`: 5
- `NON_RETRYABLE_ERRORS`: frozenset{'suspended', 'captcha', 'loggedout', 'actionblocked', 'banned'}

#### 5.6 Files
- `PROGRESS_FILE`: "parallel_progress.csv"
- `STATE_FILE`: "scheduler_state.json"
- `LOGS_DIR`: "logs"
- `ACCOUNTS_FILE`: "accounts.txt"

#### 5.7 Timeouts
- `ADB_TIMEOUT`: 30s
- `ADB_READY_TIMEOUT`: 90s
- `APPIUM_CONNECT_TIMEOUT`: 60s
- `PHONE_BOOT_TIMEOUT`: 120s

#### 5.8 Screen Coordinates (720x1280 Geelark phones)
- `SCREEN_CENTER_X`: 360, `SCREEN_CENTER_Y`: 640
- `FEED_TOP_Y`: 400, `FEED_BOTTOM_Y`: 900
- `REELS_TOP_Y`: 300, `REELS_BOTTOM_Y`: 1000
- `STORY_NEXT_TAP_X`: 650
- `SWIPE_DURATION_FAST`: 300ms, `SWIPE_DURATION_SLOW`: 200ms

#### 5.9 Helper Functions
- `setup_environment()` → Set ANDROID_HOME, update PATH
- `get_adb_env()` → Get env dict for subprocesses
- `get_worker_appium_port(worker_id)` → Calculate port
- `get_worker_system_port_range(worker_id)` → Calculate port range

### 6. Cross-references
- Link between docs (e.g., "See CONFIG.md for timeout values")
- Reference existing CLAUDE.md for operational guidelines
- Link to reviews/documentation_coverage_analysis.md for improvement tracking

**Test Strategy:**

## Verification Steps

### 1. File Creation Verification
```bash
# Verify docs/ folder structure exists
ls -la docs/
# Expected: README.md, API.md, MODULES.md, CONFIG.md

# Verify all files have content
wc -l docs/*.md
# Each file should have substantial content (100+ lines)
```

### 2. Content Completeness Checks

#### 2.1 README.md Verification
```bash
# Check for key sections
grep -c "Quick Start\|Prerequisites\|Usage\|Installation" docs/README.md
# Expected: 4+ matches

# Verify code examples are present
grep -c "python parallel_orchestrator.py" docs/README.md
# Expected: 2+ matches
```

#### 2.2 API.md Verification
```bash
# Check all GeelarkClient methods are documented
grep -c "list_phones\|start_phone\|stop_phone\|enable_adb\|upload_file" docs/API.md
# Expected: 5+ matches for each method name

# Verify return value documentation
grep -c "Returns:" docs/API.md
# Expected: 10+ matches
```

#### 2.3 MODULES.md Verification
```bash
# Check all core components are documented
grep -c "SmartInstagramPoster\|DeviceConnectionManager\|ProgressTracker\|ParallelOrchestrator" docs/MODULES.md
# Expected: Each component mentioned 3+ times

# Verify method documentation
grep -c "def \|Args:\|Returns:" docs/MODULES.md
# Expected: Multiple matches for documented methods
```

#### 2.4 CONFIG.md Verification
```bash
# Check all config categories are documented
grep -c "PATHS\|APPIUM\|PARALLEL\|TIMEOUTS\|SCREEN" docs/CONFIG.md
# Expected: 5+ section headers

# Verify all key constants are documented
grep -c "APPIUM_BASE_PORT\|MAX_WORKERS\|ADB_TIMEOUT\|SCREEN_CENTER" docs/CONFIG.md
# Expected: 4+ matches
```

### 3. Markdown Validation
```bash
# Install and run markdown linter
npm install -g markdownlint-cli
markdownlint docs/*.md --config .markdownlint.json 2>/dev/null || echo "Linting complete"

# Check for broken internal links
grep -o '\[.*\](.*\.md)' docs/*.md | while read link; do
  target=$(echo "$link" | sed 's/.*(\(.*\))/\1/')
  if [ ! -f "docs/$target" ] && [ ! -f "$target" ]; then
    echo "Broken link: $link"
  fi
done
```

### 4. Cross-Reference Integrity
```bash
# Verify links between documentation files work
grep -l "CONFIG.md\|API.md\|MODULES.md" docs/*.md
# Expected: Multiple files linking to each other

# Check references to actual code files
grep -o '[a-z_]*\.py' docs/*.md | sort -u | while read pyfile; do
  if [ ! -f "$pyfile" ]; then
    echo "Referenced but missing: $pyfile"
  fi
done
```

### 5. Accuracy Verification
```python
# Python script to verify documented methods exist
import ast
import re

def check_documented_methods(md_file, py_file):
    """Verify methods documented in md_file exist in py_file."""
    with open(md_file) as f:
        md_content = f.read()
    
    with open(py_file) as f:
        tree = ast.parse(f.read())
    
    # Extract method names from Python file
    actual_methods = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            actual_methods.add(node.name)
    
    # Extract documented method names from markdown
    documented = set(re.findall(r'`(\w+)\(`', md_content))
    
    # Check for undocumented methods (public only)
    public_methods = {m for m in actual_methods if not m.startswith('_')}
    missing = public_methods - documented
    if missing:
        print(f"Undocumented in {md_file}: {missing}")
    
    return len(missing) == 0

# Run checks
check_documented_methods('docs/API.md', 'geelark_client.py')
check_documented_methods('docs/MODULES.md', 'progress_tracker.py')
```

### 6. User Experience Test
```bash
# Simulate new developer onboarding
# 1. Read README.md - should understand project purpose
# 2. Follow Quick Start - should be able to run basic command
# 3. Look up API method - should find in API.md
# 4. Configure settings - should find in CONFIG.md

# Test: Can a developer find how to start parallel posting?
grep -A5 "parallel posting" docs/README.md
# Expected: Clear instructions with command example
```
