# Campaign System Bug Analysis

## Status: FIXED ✅

All bugs identified below have been fixed as of 2025-12-15.

## Executive Summary

Analysis of the multi-campaign posting system (`--campaign` flag) to identify bugs preventing independent operation of podcast vs viral campaigns.

**Overall Finding:** The core file path wiring for `--campaign` is **mostly correct**, but there were several bugs and missing features that caused issues in practice. **All are now fixed.**

---

## Priority 1: Critical Bugs

### BUG 1: `stop_all_phones()` Stops ALL Geelark Phones (Not Campaign-Specific)

**File:** `parallel_orchestrator.py`
**Lines:** 376-395, called from `full_cleanup()` at line 552

**Problem:**
```python
def stop_all_phones() -> int:
    """Stop all running Geelark phones."""
    # ... iterates ALL phones and stops ANY with status == 1
    for phone in result.get('items', []):
        if phone.get('status') == 1:
            client.stop_phone(phone['id'])
```

This function is called:
- At startup in `full_cleanup()` (line 900 in `run_parallel_posting()`)
- On shutdown (line 990)
- On `--stop-all` command (line 1161)

**Impact:** Running `--campaign viral --run` will stop phones being used by VAs or other campaigns.

**Fix Required:**
1. Track which phones THIS orchestrator instance started
2. Only stop phones that were started by this session
3. Add `--stop-campaign-phones` flag for explicit campaign phone cleanup
4. Change `full_cleanup()` to accept optional `phones_to_stop` list

```python
# Proposed fix - add phone tracking
_started_phones: Set[str] = set()  # Track phone names started by this session

def stop_session_phones() -> int:
    """Stop only phones started by this orchestrator session."""
    global _started_phones
    # Only stop phones in _started_phones set
```

---

### BUG 2: Orchestrator Conflict Check Blocks Concurrent Campaigns

**File:** `parallel_orchestrator.py`
**Lines:** 70-131

**Problem:**
```python
def check_for_running_orchestrators() -> Tuple[bool, List[str]]:
    # Checks for ANY process with "parallel_orchestrator.py --run"
    if 'parallel_orchestrator.py' in line and '--run' in line:
        conflicts.append(...)
```

**Impact:** Cannot run `--campaign viral --run` and `--campaign podcast --run` simultaneously, even though they use different progress files and accounts.

**Fix Required:**
1. Make conflict check campaign-aware
2. Allow concurrent orchestrators IF they're running different campaigns
3. Only block if same campaign OR if no campaign specified

```python
def check_for_running_orchestrators(campaign_name: str = None) -> Tuple[bool, List[str]]:
    # If campaign specified, only conflict with same campaign
    # If no campaign, conflict with any non-campaign orchestrator
```

---

## Priority 2: File Path Issues

### BUG 3: `seed_from_campaign()` Caption Column Detection Is Fragile

**File:** `config.py`
**Lines:** 273-285 in `CampaignConfig.from_folder()`

**Problem:**
```python
# Detect CSV format by reading header
with open(captions_file, 'r', encoding='utf-8') as f:
    header = f.readline().strip().lower()
    # Handle podcast format: "Text,Image/Video link 1 (shortcode)"
    if "text" in header and "shortcode" in header:
        caption_column = "Text"
        filename_column = "shortcode"  # Special handling needed
```

The `filename_column = "shortcode"` comment says "Special handling needed" but the code in `progress_tracker.py` `seed_from_campaign()` doesn't implement this special handling.

**File:** `progress_tracker.py`
**Lines:** 495-499

```python
for row in reader:
    filename = row.get(filename_column, '').strip()  # Gets "shortcode" value, not filename!
    caption = row.get(caption_column, '').strip()
```

**Impact:** Podcast campaigns with "shortcode" format won't match videos correctly.

**Fix Required:**
Add logic in `seed_from_campaign()` to handle shortcode-to-filename conversion:
```python
if campaign_config.filename_column == "shortcode":
    # Convert shortcode to actual filename pattern
    filename = f"{shortcode}-*.mp4"  # or lookup logic
```

---

### BUG 4: Missing `pass_number` Column in Campaign Seeding

**File:** `progress_tracker.py`
**Lines:** 564-579 in `seed_from_campaign()`

**Problem:**
```python
new_jobs.append({
    'job_id': job_id,
    # ...
    'error_category': ''
    # MISSING: 'pass_number' column!
})
```

But `COLUMNS` at line 78-83 includes `pass_number`:
```python
COLUMNS = [
    'job_id', 'account', 'video_path', 'caption', 'status',
    'worker_id', 'claimed_at', 'completed_at', 'error',
    'attempts', 'max_attempts', 'retry_at', 'error_type',
    'error_category', 'pass_number'  # <-- This column exists
]
```

**Impact:** CSV schema mismatch could cause issues.

**Fix:** Add `'pass_number': ''` to the job dict in `seed_from_campaign()`.

---

## Priority 3: Missing Features / Improvements

### MISSING 1: No Campaign Context in Log Messages

**Problem:** When errors occur, log messages don't indicate which campaign is being processed.

**Files Affected:**
- `parallel_orchestrator.py`: All logger calls
- `parallel_worker.py`: Worker log messages

**Fix:** Add campaign name to logger format when campaign is active:
```python
if campaign_config:
    logging.basicConfig(
        format=f'%(asctime)s [ORCHESTRATOR:{campaign_config.name}] %(levelname)s %(message)s'
    )
```

---

### MISSING 2: No Campaign Name Passed to Workers

**File:** `parallel_orchestrator.py`
**Lines:** 632-663 in `start_worker_process()`

**Problem:**
```python
cmd = [
    sys.executable,
    'parallel_worker.py',
    '--worker-id', str(worker_id),
    '--num-workers', str(config.num_workers),
    '--progress-file', config.progress_file,
    '--delay', str(config.delay_between_jobs)
    # MISSING: --campaign-name for logging context
]
```

**Impact:** Worker logs don't indicate which campaign they're processing.

**Fix:** Add `--campaign-name` argument to worker subprocess.

---

### MISSING 3: Campaign Validation Could Be Stronger

**File:** `config.py`
**Lines:** 265-271 in `CampaignConfig.from_folder()`

**Current validation:**
```python
if not os.path.exists(accounts_file):
    raise ValueError(f"Campaign missing accounts.txt: {accounts_file}")
if captions_file is None or not os.path.exists(captions_file):
    raise ValueError(f"Campaign missing captions CSV in: {base_dir}")
if videos_dir is None:
    raise ValueError(f"Campaign missing videos folder in: {base_dir}")
```

**Missing validation:**
- No check for empty accounts.txt
- No check for empty captions CSV
- No validation that video files actually match caption entries

---

## What Works Correctly

After tracing through the code, these paths ARE correctly wired:

| Command | Progress File | Accounts | Status |
|---------|--------------|----------|--------|
| `--campaign X --status` | ✅ Uses campaign progress.csv | N/A | Works |
| `--campaign X --reset-day` | ✅ Uses campaign progress.csv | N/A | Works |
| `--campaign X --retry-all-failed` | ✅ Uses campaign progress.csv | N/A | Works |
| `--campaign X --seed-only` | ✅ Uses campaign progress.csv | ✅ Uses campaign accounts.txt | Works |
| `--campaign X --run` | ✅ Uses campaign progress.csv | ✅ Uses campaign accounts.txt | Works* |

*Works but has phone cleanup issues (BUG 1)

**Key correct wiring:**
1. Line 1119: `config.progress_file = campaign_config.progress_file`
2. Line 1120: `accounts_list = campaign_config.get_accounts()`
3. Line 863: `config.progress_file = campaign_config.progress_file` (in run_parallel_posting)

---

## Recommended Fix Priority

1. **HIGH:** BUG 1 - Stop only session phones (breaks VA workflows)
2. **HIGH:** BUG 3 - Fix shortcode/podcast caption matching
3. **MEDIUM:** BUG 2 - Allow concurrent campaign orchestrators
4. **MEDIUM:** BUG 4 - Add missing pass_number column
5. **LOW:** MISSING 1-3 - Logging and validation improvements

---

## Test Plan

After fixes, verify:

```bash
# Test 1: Campaign isolation
python parallel_orchestrator.py --campaign viral --seed-only
# Should ONLY write to campaigns/viral/progress.csv

# Test 2: Status shows campaign files
python parallel_orchestrator.py --campaign viral --status
# Should show campaigns/viral/progress.csv stats

# Test 3: Reset-day archives campaign file
python parallel_orchestrator.py --campaign viral --reset-day
# Should archive campaigns/viral/progress.csv

# Test 4: Run uses campaign files
python parallel_orchestrator.py --campaign viral --workers 2 --run
# Should only use viral accounts, viral progress, viral videos
# Should NOT stop phones from other campaigns/VAs

# Test 5: Concurrent campaigns (after BUG 2 fix)
# Terminal 1: python parallel_orchestrator.py --campaign viral --run
# Terminal 2: python parallel_orchestrator.py --campaign podcast --run
# Both should run without conflict
```
