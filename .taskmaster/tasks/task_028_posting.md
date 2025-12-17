# Task ID: 28

**Title:** Update CLAUDE.md documentation with parallel orchestrator architecture

**Status:** done

**Dependencies:** 25 ✓, 26 ✓

**Priority:** medium

**Description:** Document the parallel_orchestrator.py as the primary entry point for batch posting, explain the worker architecture (separate processes with dedicated Appium servers), document progress tracking via parallel_progress.csv, and update the Key Files table with new modules.

**Details:**

## Current State Analysis

The CLAUDE.md file (399 lines) has basic parallel orchestrator documentation at lines 199-239, but it is outdated and incomplete. The following areas need updating:

### 1. Key Files Table Update (Lines 263-274)

**Current Table (missing new modules):**
```markdown
| File | Purpose |
|------|---------|
| `posting_scheduler.py` | **MAIN SCRIPT** - scheduler with tracking, retry, state persistence |
| `post_reel_smart.py` | Core posting logic for single phone (Appium timeout: 60s) |
| `geelark_client.py` | Geelark API wrapper (upload timeout: 60s) |
| `dashboard.py` | Real-time web dashboard (http://localhost:5000) |
| `scheduler_state.json` | Persistent state (auto-generated) |
| `geelark_batch.log` | Execution log with phase info |
| `geelark_api.log` | API response log (for Geelark support) |
```

**Add these new modules to the table:**
- `parallel_orchestrator.py` - **PRIMARY ENTRY POINT** for parallel batch posting
- `parallel_worker.py` - Individual worker process (one per Appium server)
- `parallel_config.py` - Worker configuration (ports, systemPorts, log files)
- `progress_tracker.py` - File-locked CSV progress tracking with retry support
- `config.py` - Centralized configuration (all paths, timeouts, constants)
- `parallel_progress.csv` - Daily job ledger (file-locked, NEVER delete manually)

### 2. Parallel Orchestrator Architecture Section Update (Lines 199-239)

Expand the architecture documentation to include:

**Worker Architecture Details:**
```
parallel_orchestrator.py (main process)
    │
    ├── Worker 0 ──► Appium:4723 ──► systemPort:8200-8209 ──► Phone
    ├── Worker 1 ──► Appium:4725 ──► systemPort:8210-8219 ──► Phone
    ├── Worker 2 ──► Appium:4727 ──► systemPort:8220-8229 ──► Phone
    └── Worker N ──► Appium:472X ──► systemPort:82X0-82X9 ──► Phone

    Coordination: Workers communicate via file-locked parallel_progress.csv
    Logs: logs/worker_N.log, logs/appium_N.log per worker
```

**Key Implementation Details to Document:**
- Each worker is a SEPARATE PROCESS (subprocess.Popen), not a thread
- Port allocation: Appium on odd ports (4723, 4725, ...), systemPorts in 10-port ranges
- Workers coordinate via ProgressTracker using portalocker file locking
- Config from config.py: MAX_POSTS_PER_ACCOUNT_PER_DAY=1, MAX_RETRY_ATTEMPTS=3
- State machine states in parallel_worker.py: STARTING → ADB_PENDING → ADB_READY → APPIUM_READY → JOB_RUNNING

### 3. Progress Tracking Documentation (New Section)

Add detailed documentation about the progress tracking system:

```markdown
## Progress Tracking (parallel_progress.csv)

The daily job ledger that tracks ALL posting jobs. Uses file locking (portalocker)
to ensure only one worker can claim a job at a time.

### CSV Columns:
- job_id, account, video_path, caption
- status: pending/claimed/success/failed/skipped/retrying
- worker_id, claimed_at, completed_at, error
- attempts, max_attempts, retry_at, error_type

### Status Transitions:
pending → claimed (worker claims job)
claimed → success (post succeeded)
claimed → retrying (post failed, will retry)
retrying → claimed (worker claims retry job)
retrying → failed (max attempts reached or non-retryable error)

### Non-Retryable Errors:
suspended, captcha, loggedout, actionblocked, banned
```

### 4. Config.py Documentation (New Section)

Document the centralized configuration:

```markdown
## Centralized Configuration (config.py)

All paths and settings are defined in config.py. NEVER hardcode paths elsewhere.

Key Settings:
- ANDROID_SDK_PATH: C:\Users\asus\Downloads\android-sdk
- ADB_PATH: {SDK}\platform-tools\adb.exe
- MAX_POSTS_PER_ACCOUNT_PER_DAY: 1
- MAX_RETRY_ATTEMPTS: 3
- RETRY_DELAY_MINUTES: 5
- JOB_TIMEOUT: 300s
```

### 5. Update MAIN ENTRY POINTS Section (Lines 185-195)

Emphasize parallel_orchestrator.py as the PRIMARY method:

```markdown
## MAIN ENTRY POINTS

### For Parallel Posting (PRIMARY - RECOMMENDED):
```bash
python parallel_orchestrator.py --workers 5 --run
```

### For Single-Threaded Posting (Legacy):
```bash
python posting_scheduler.py --add-folder chunk_01c --run
```
```

### Implementation Notes

1. Update the Key Files table to include all new modules with accurate descriptions
2. Expand the worker architecture diagram with systemPort allocations
3. Add a new "Progress Tracking" section explaining the CSV ledger
4. Add a new "Centralized Configuration" section documenting config.py
5. Update the "MAIN ENTRY POINTS" section to emphasize parallel_orchestrator
6. Ensure worker stagger timing (60s between starts) is documented
7. Document the retry system (attempts, delay, non-retryable errors)

**Test Strategy:**

## Test Strategy

### 1. Documentation Accuracy Verification

**Verify Key Files table matches actual files:**
```bash
# Check all documented files exist
ls -la parallel_orchestrator.py parallel_worker.py parallel_config.py progress_tracker.py config.py

# Verify CSV columns match ProgressTracker.COLUMNS
python -c "from progress_tracker import ProgressTracker; print(ProgressTracker.COLUMNS)"
```

**Verify port allocations match code:**
```bash
python -c "
from config import Config
print(f'Base Appium: {Config.APPIUM_BASE_PORT}')
print(f'System port base: {Config.SYSTEM_PORT_BASE}')
for i in range(3):
    print(f'Worker {i}: Appium {Config.get_worker_appium_port(i)}, systemPort {Config.get_worker_system_port_range(i)}')
"
```

### 2. Documentation Completeness Check

**Ensure all CLI flags are documented:**
```bash
python parallel_orchestrator.py --help
```

Compare output against CLAUDE.md documentation for completeness.

**Verify config values match documentation:**
```bash
python -c "
from config import Config
print(f'MAX_POSTS_PER_ACCOUNT_PER_DAY: {Config.MAX_POSTS_PER_ACCOUNT_PER_DAY}')
print(f'MAX_RETRY_ATTEMPTS: {Config.MAX_RETRY_ATTEMPTS}')
print(f'RETRY_DELAY_MINUTES: {Config.RETRY_DELAY_MINUTES}')
print(f'JOB_TIMEOUT: {Config.JOB_TIMEOUT}')
"
```

### 3. Code-Documentation Consistency

**Verify worker architecture matches implementation:**
```bash
# Check worker startup in orchestrator
grep -n "start_worker_process\|Popen\|stagger" parallel_orchestrator.py

# Check state machine states in worker
grep -n "WorkerState\|STARTING\|ADB_PENDING\|ADB_READY" parallel_worker.py
```

**Verify status values match code:**
```bash
python -c "
from progress_tracker import ProgressTracker
print('Statuses:', [s for s in dir(ProgressTracker) if s.startswith('STATUS_')])
print('Non-retryable:', ProgressTracker.NON_RETRYABLE_ERRORS)
"
```

### 4. Functional Verification

**Test that documented commands work:**
```bash
# Test status command
python parallel_orchestrator.py --status

# Test reset-day (dry run - just verify it parses)
python parallel_orchestrator.py --help | grep reset-day
```

### 5. Cross-Reference Check

Verify all CRITICAL sections in CLAUDE.md reference the correct files:
- "PROGRESS FILE MANAGEMENT" → parallel_progress.csv
- "ACCOUNT MANAGEMENT" → accounts.txt, scheduler_state.json
- "STOP PHONES" → stop script uses GeelarkClient correctly

### 6. Markdown Rendering Test

Open CLAUDE.md in a markdown viewer or VS Code preview to ensure:
- Tables render correctly
- Code blocks have proper syntax highlighting
- Architecture diagrams are properly formatted
- All links (if any) are valid
