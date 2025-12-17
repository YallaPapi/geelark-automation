# Task ID: 59

**Title:** Fix Campaign System Bugs for Isolated Campaign Operations

**Status:** done

**Dependencies:** 57 ✓, 58 ✓

**Priority:** high

**Description:** Fix critical bugs in the multi-campaign posting system that prevent independent operation of concurrent campaigns, including: (1) stop_all_phones() stopping VA phones, (2) orchestrator conflict check blocking concurrent campaigns, (3) shortcode-to-filename mapping for podcast campaigns, (4) missing pass_number column in seed_from_campaign, and (5) campaign context in log messages.

**Details:**

## Implementation Details

Based on the bug analysis in `reviews/CAMPAIGN_SYSTEM_BUG_ANALYSIS.md`, the following fixes are required:

### Priority 1: Critical Bugs

#### BUG 1: Make stop_all_phones() Only Stop Session Phones (parallel_orchestrator.py)

**Current Problem (lines 376-395):**
`stop_all_phones()` iterates ALL Geelark phones and stops any with `status == 1`. This breaks VA workflows when running campaign posts.

**Fix:**
1. Add a module-level Set to track phones started by this session:
```python
# Line ~64-67 (after global state variables)
_started_phones: Set[str] = set()  # Track phone names started by this session
```

2. Create a helper function to register phones when started (modify `execute_posting_job` flow or add tracking in worker):
```python
def register_started_phone(phone_name: str) -> None:
    """Register a phone as started by this session."""
    global _started_phones
    _started_phones.add(phone_name)
```

3. Create `stop_session_phones()` function that only stops tracked phones:
```python
def stop_session_phones() -> int:
    """Stop only phones started by this orchestrator session."""
    global _started_phones
    if not _started_phones:
        logger.info("No session phones to stop")
        return 0
    
    logger.info(f"Stopping {len(_started_phones)} session phone(s)...")
    client = GeelarkClient()
    stopped = 0
    
    for page in range(1, 20):
        result = client.list_phones(page=page, page_size=100)
        for phone in result.get('items', []):
            if phone.get('serialName') in _started_phones and phone.get('status') == 1:
                client.stop_phone(phone['id'])
                logger.info(f"  Stopped session phone: {phone.get('serialName')}")
                stopped += 1
        if len(result.get('items', [])) < 100:
            break
    
    _started_phones.clear()
    logger.info(f"Stopped {stopped} session phone(s)")
    return stopped
```

4. Modify `full_cleanup()` (line 531-580) to use `stop_session_phones()` instead of `stop_all_phones()`.

5. Keep `stop_all_phones()` available for explicit `--stop-all` command but add warning.

#### BUG 2: Allow Concurrent Orchestrators for Different Campaigns (parallel_orchestrator.py)

**Current Problem (lines 70-131):**
`check_for_running_orchestrators()` blocks ANY other orchestrator with `--run`, even if running a different campaign.

**Fix:**
1. Modify function signature to accept campaign_name:
```python
def check_for_running_orchestrators(campaign_name: str = None) -> Tuple[bool, List[str]]:
```

2. Modify the conflict detection logic to be campaign-aware:
```python
# Inside the loop checking process command lines:
if 'parallel_orchestrator.py' in line and '--run' in line:
    # Extract campaign from command line if present
    other_campaign = None
    if '--campaign' in line:
        # Parse: --campaign viral or -c viral
        parts = line.split()
        for i, part in enumerate(parts):
            if part in ('--campaign', '-c') and i + 1 < len(parts):
                other_campaign = parts[i + 1]
                break
    
    # Only conflict if:
    # 1. Both have no campaign (root-level)
    # 2. Both have same campaign name
    if campaign_name is None and other_campaign is None:
        conflicts.append(...)  # Both root-level
    elif campaign_name and campaign_name == other_campaign:
        conflicts.append(...)  # Same campaign
    # Otherwise: different campaigns, no conflict
```

3. Update call sites to pass campaign_name (line 875, line 441).

### Priority 2: File Path Issues

#### BUG 3: Fix Shortcode-to-Filename Mapping (progress_tracker.py, config.py)

**Current Problem (progress_tracker.py lines 495-499):**
For podcast campaigns with "shortcode" format CSV, the code reads the shortcode value directly but doesn't convert it to actual filename.

**Fix in progress_tracker.py `seed_from_campaign()` (around line 528-538):**
```python
for video_path in video_files:
    video_filename = os_module.path.basename(video_path)
    video_base = os_module.path.splitext(video_filename)[0]
    
    # Find caption for this video
    caption = None
    
    if campaign_config.filename_column == "shortcode":
        # Podcast format: shortcode in CSV (e.g., "DM6m1Econ4x")
        # Video filename format: "DM6m1Econ4x-2.mp4" or "DM6m1Econ4x.mp4"
        # Match by checking if video filename STARTS with the shortcode
        for shortcode, cap in video_to_caption.items():
            if video_base.startswith(shortcode) or video_filename.startswith(shortcode):
                caption = cap
                break
    else:
        # Standard format: exact filename match
        caption = video_to_caption.get(video_filename, '')
        if not caption:
            caption = video_to_caption.get(video_base, '')
    
    if not caption:
        continue  # Skip videos without captions
```

#### BUG 4: Add Missing pass_number Column (progress_tracker.py)

**Current Problem (lines 564-579):**
`seed_from_campaign()` creates job dicts without `pass_number` column, but `COLUMNS` (line 78-83) includes it.

**Fix:** Add `'pass_number': ''` to the job dict in `seed_from_campaign()`:
```python
new_jobs.append({
    'job_id': job_id,
    'account': assigned_account,
    'video_path': video_path,
    'caption': caption,
    'status': self.STATUS_PENDING,
    'worker_id': '',
    'claimed_at': '',
    'completed_at': '',
    'error': '',
    'attempts': '0',
    'max_attempts': str(self.DEFAULT_MAX_ATTEMPTS),
    'retry_at': '',
    'error_type': '',
    'error_category': '',
    'pass_number': ''  # ADD THIS LINE
})
```

### Priority 3: Logging Improvements

#### MISSING 1: Add Campaign Context to Log Messages

**parallel_orchestrator.py:**
1. Add campaign_name to the module-level state (line ~67):
```python
_active_campaign_name: Optional[str] = None
```

2. Modify logging setup (around line 57-62) to be configurable:
```python
def configure_logging(campaign_name: str = None):
    """Configure logging with optional campaign context."""
    if campaign_name:
        format_str = f'%(asctime)s [ORCHESTRATOR:{campaign_name}] %(levelname)s %(message)s'
    else:
        format_str = '%(asctime)s [ORCHESTRATOR] %(levelname)s %(message)s'
    
    logging.basicConfig(
        level=logging.INFO,
        format=format_str,
        force=True  # Override existing config
    )
```

3. Call `configure_logging(campaign_config.name)` after loading campaign in main() (around line 1113).

**parallel_worker.py:**
1. Add `--campaign-name` argument to worker subprocess (parallel_orchestrator.py line 632-663):
```python
cmd = [
    sys.executable,
    'parallel_worker.py',
    '--worker-id', str(worker_id),
    '--num-workers', str(config.num_workers),
    '--progress-file', config.progress_file,
    '--delay', str(config.delay_between_jobs),
]
if campaign_name:
    cmd.extend(['--campaign-name', campaign_name])
```

2. Add argument parsing in parallel_worker.py:
```python
parser.add_argument('--campaign-name', default=None, help='Campaign name for logging')
```

3. Modify `setup_worker_logging()` to include campaign name:
```python
def setup_worker_logging(worker_config: WorkerConfig, campaign_name: str = None) -> logging.Logger:
    """Set up logging for this worker."""
    # ... existing code ...
    
    # Update format string
    if campaign_name:
        prefix = f'W{worker_config.worker_id}:{campaign_name}'
    else:
        prefix = f'W{worker_config.worker_id}'
    
    fh.setFormatter(logging.Formatter(
        f'%(asctime)s [{prefix}] %(levelname)s %(message)s'
    ))
```

## Files to Modify

1. **parallel_orchestrator.py**: BUG 1, BUG 2, campaign logging, worker subprocess args
2. **progress_tracker.py**: BUG 3 (shortcode mapping), BUG 4 (pass_number column)
3. **parallel_worker.py**: Campaign name argument and logging

## Backward Compatibility

- Keep `stop_all_phones()` for `--stop-all` command (explicit user request)
- Root-level orchestrator (no `--campaign`) still blocks other root-level runs
- Existing campaigns without `filename_column="shortcode"` work unchanged

**Test Strategy:**

## Test Strategy

### 1. BUG 1 - Session Phone Tracking

```bash
# Test 1.1: Verify session phone tracking doesn't affect VAs
# Start a VA phone manually, then run campaign
python -c "
from geelark_client import GeelarkClient
client = GeelarkClient()
# Note a running VA phone name
result = client.list_phones(page_size=10)
va_phone = [p for p in result['items'] if p['status'] == 1][0]['serialName'] if any(p['status'] == 1 for p in result['items']) else None
print(f'VA phone running: {va_phone}')
"

# Run campaign with 1 worker
python parallel_orchestrator.py --campaign viral --workers 1 --seed-only
python parallel_orchestrator.py --campaign viral --workers 1 --run
# Kill after 1 job completes

# Verify VA phone still running
python -c "
from geelark_client import GeelarkClient
client = GeelarkClient()
result = client.list_phones(page_size=10)
running = [p['serialName'] for p in result['items'] if p['status'] == 1]
print(f'Still running: {running}')
# VA phone should still be in this list
"

# Test 1.2: stop_session_phones() only stops tracked phones
python -c "
import parallel_orchestrator as po
# Register fake phones
po._started_phones = {'test_phone_1', 'test_phone_2'}
print(f'Tracked phones: {po._started_phones}')
# stop_session_phones should only target these
"
```

### 2. BUG 2 - Concurrent Campaign Orchestrators

```bash
# Test 2.1: Same campaign should conflict
# Terminal 1:
python parallel_orchestrator.py --campaign viral --seed-only
python parallel_orchestrator.py --campaign viral --workers 1 --run

# Terminal 2 (while Terminal 1 running):
python parallel_orchestrator.py --campaign viral --workers 1 --run
# Should show: "CONFLICT: Other orchestrator processes are running!"

# Test 2.2: Different campaigns should NOT conflict
# Terminal 1:
python parallel_orchestrator.py --campaign viral --workers 1 --run

# Terminal 2 (while Terminal 1 running):
python parallel_orchestrator.py --campaign podcast --workers 1 --run
# Should start without conflict (after BUG fix)

# Test 2.3: Root-level should still conflict with root-level
# Terminal 1 (no campaign):
python parallel_orchestrator.py --workers 1 --run

# Terminal 2 (no campaign):
python parallel_orchestrator.py --workers 1 --run
# Should conflict
```

### 3. BUG 3 - Shortcode Matching

```bash
# Test 3.1: Create test podcast campaign structure
mkdir -p campaigns/test_podcast/videos
echo "podclipcrafters" > campaigns/test_podcast/accounts.txt
cat > campaigns/test_podcast/captions.csv << 'EOF'
Text,Image/Video link 1 (shortcode)
"Test caption 1",DM6m1Econ4x
"Test caption 2",DMbMMftoiDC
EOF
# Create dummy videos with shortcode-based names
echo "fake" > campaigns/test_podcast/videos/DM6m1Econ4x-2.mp4
echo "fake" > campaigns/test_podcast/videos/DMbMMftoiDC-1.mp4

# Test 3.2: Verify seeding matches shortcodes to files
python -c "
from config import CampaignConfig
from progress_tracker import ProgressTracker

campaign = CampaignConfig.from_folder('campaigns/test_podcast')
print(f'filename_column: {campaign.filename_column}')  # Should be 'shortcode'

tracker = ProgressTracker('campaigns/test_podcast/progress.csv')
count = tracker.seed_from_campaign(campaign)
print(f'Seeded {count} jobs')

# Verify jobs have correct video paths
import csv
with open('campaigns/test_podcast/progress.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        print(f'Job: {row[\"job_id\"]} -> {row[\"video_path\"]} -> caption length: {len(row[\"caption\"])}')
"

# Clean up
rm -rf campaigns/test_podcast
```

### 4. BUG 4 - pass_number Column

```bash
# Test 4.1: Verify pass_number column exists after seeding
python -c "
import csv
from config import CampaignConfig
from progress_tracker import ProgressTracker

# Use existing viral campaign or create test
campaign = CampaignConfig.from_folder('campaigns/viral')
tracker = ProgressTracker('campaigns/viral/test_progress.csv')
count = tracker.seed_from_campaign(campaign)

# Check columns
with open('campaigns/viral/test_progress.csv') as f:
    reader = csv.DictReader(f)
    row = next(reader)
    print(f'Columns: {list(row.keys())}')
    assert 'pass_number' in row, 'pass_number column missing!'
    print('✓ pass_number column present')

# Clean up
import os
os.remove('campaigns/viral/test_progress.csv')
os.remove('campaigns/viral/test_progress.csv.lock')
"
```

### 5. Priority 3 - Campaign Logging

```bash
# Test 5.1: Verify orchestrator logs include campaign name
python parallel_orchestrator.py --campaign viral --status 2>&1 | head -5
# Should show: [ORCHESTRATOR:viral] in log prefix

# Test 5.2: Verify worker logs include campaign name
# Check log file after running:
python parallel_orchestrator.py --campaign viral --workers 1 --run
# Then:
head -5 logs/worker_0.log
# Should show: [W0:viral] in log prefix
```

### 6. Integration Test

```bash
# Full integration test with campaign isolation
# Requires two terminal windows

# Setup
python parallel_orchestrator.py --campaign viral --reset-day
python parallel_orchestrator.py --campaign podcast --reset-day

# Terminal 1:
python parallel_orchestrator.py --campaign viral --workers 2 --run

# Terminal 2 (wait 30s for T1 to start):
python parallel_orchestrator.py --campaign podcast --workers 2 --run

# Both should run concurrently without:
# - Stopping each other's phones
# - Conflicting on orchestrator check
# - Mixing up progress files
```
