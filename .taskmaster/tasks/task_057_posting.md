# Task ID: 57

**Title:** Implement Multi-Campaign Support for Separate Posting Campaigns

**Status:** done

**Dependencies:** 2 ✓, 9 ✓, 19 ✓, 20 ✓, 54 ✓

**Priority:** high

**Description:** Create a simplified sequential campaign system that allows running separate posting campaigns (podcast, viral, etc.) with different videos, captions, accounts, and progress files. Campaigns run one at a time using the same Appium ports - no parallel campaign execution.

**Details:**

## Simplified Implementation Overview

Create a sequential campaign architecture that extends the existing parallel orchestrator to support running campaigns with isolated configuration files. Campaigns share Appium infrastructure and run one at a time - no concurrent campaign execution.

## Core Components to Create/Modify

### 1. Campaign Folder Structure

Define a standard campaign folder layout:

```
campaigns/
├── podcast/
│   ├── campaign.json               # Campaign metadata (name, settings)
│   ├── accounts.txt                # Campaign-specific accounts (subset of main)
│   ├── scheduler_state.json        # Campaign job queue
│   ├── progress.csv                # Campaign progress tracking
│   └── videos/                     # Video content (or symlinks to chunk_*)
│       └── chunk_01c/
│           ├── chunk_01c_cleaned.csv
│           └── 2bears.1cave/
├── viral/
│   ├── campaign.json
│   ├── accounts.txt
│   ├── scheduler_state.json
│   ├── progress.csv
│   └── videos/
└── memes/
    └── ...
```

### 2. campaign.json Schema

Minimal campaign metadata:

```json
{
  "name": "podcast",
  "description": "Podcast clip reposting campaign",
  "enabled": true,
  "max_posts_per_account_per_day": 1,
  "video_folders": ["videos/chunk_01c"]
}
```

### 3. CampaignConfig Dataclass (New in `config.py`)

Add a simple CampaignConfig dataclass to config.py:

```python
@dataclass
class CampaignConfig:
    """Configuration for a single posting campaign."""
    name: str                              # e.g., "podcast", "viral", "memes"
    base_dir: str                          # Campaign folder path (campaigns/podcast)
    accounts_file: str                     # Path to accounts.txt within campaign
    state_file: str                        # Path to scheduler_state.json within campaign  
    progress_file: str                     # Path to progress.csv within campaign
    max_posts_per_account_per_day: int = 1 # Can vary per campaign
    enabled: bool = True
    
    @classmethod
    def from_folder(cls, campaign_folder: str) -> 'CampaignConfig':
        """Load campaign config from folder structure."""
        campaign_json = os.path.join(campaign_folder, 'campaign.json')
        with open(campaign_json, 'r') as f:
            data = json.load(f)
        
        return cls(
            name=data.get('name', os.path.basename(campaign_folder)),
            base_dir=campaign_folder,
            accounts_file=os.path.join(campaign_folder, 'accounts.txt'),
            state_file=os.path.join(campaign_folder, 'scheduler_state.json'),
            progress_file=os.path.join(campaign_folder, 'progress.csv'),
            max_posts_per_account_per_day=data.get('max_posts_per_account_per_day', 1),
            enabled=data.get('enabled', True)
        )
    
    def validate(self) -> tuple:
        """Validate campaign files exist. Returns (is_valid, errors)."""
        errors = []
        if not os.path.exists(self.accounts_file):
            errors.append(f"accounts.txt not found: {self.accounts_file}")
        if not os.path.exists(self.state_file):
            errors.append(f"scheduler_state.json not found: {self.state_file}")
        return len(errors) == 0, errors
```

### 4. Add Campaign Constants to Config Class

Add to existing Config class in config.py:

```python
# Campaign directory
CAMPAIGNS_DIR: str = "campaigns"
CAMPAIGN_CONFIG_FILE: str = "campaign.json"
```

### 5. Modify `parallel_orchestrator.py`

Add campaign CLI flags:

```python
def main():
    parser.add_argument('--campaign', '-c', type=str, default=None,
                        help='Campaign name to run (e.g., "podcast", "viral")')
    parser.add_argument('--list-campaigns', action='store_true',
                        help='List all available campaigns')
```

Modify `seed_progress_file()` to accept campaign config:

```python
def seed_progress_file(
    config: ParallelConfig,
    state_file: str = "scheduler_state.json",
    accounts_file: str = "accounts.txt",  # NEW: campaign-specific accounts
    accounts_filter: List[str] = None
) -> int:
```

Modify `run_parallel_posting()` to accept campaign:

```python
def run_parallel_posting(
    num_workers: int = 3,
    state_file: str = "scheduler_state.json",
    progress_file: str = None,  # NEW: override progress file path
    accounts_file: str = "accounts.txt",  # NEW: override accounts file
    ...
) -> Dict:
```

Add helper function to load campaign and run:

```python
def load_campaign(campaign_name: str) -> CampaignConfig:
    """Load campaign config by name from campaigns/ directory."""
    campaign_dir = os.path.join(Config.CAMPAIGNS_DIR, campaign_name)
    if not os.path.exists(campaign_dir):
        raise ValueError(f"Campaign '{campaign_name}' not found in {Config.CAMPAIGNS_DIR}/")
    return CampaignConfig.from_folder(campaign_dir)

def list_campaigns() -> List[CampaignConfig]:
    """List all campaigns in campaigns/ directory."""
    campaigns = []
    campaigns_dir = Config.CAMPAIGNS_DIR
    if not os.path.exists(campaigns_dir):
        return campaigns
    for name in os.listdir(campaigns_dir):
        campaign_json = os.path.join(campaigns_dir, name, 'campaign.json')
        if os.path.exists(campaign_json):
            try:
                campaigns.append(CampaignConfig.from_folder(os.path.join(campaigns_dir, name)))
            except Exception as e:
                logger.warning(f"Error loading campaign {name}: {e}")
    return campaigns
```

### 6. Modify `progress_tracker.py`

Add optional campaign_name parameter for logging (no functional change):

```python
class ProgressTracker:
    def __init__(self, progress_file: str, campaign_name: str = "default", lock_timeout: float = 30.0):
        self.campaign_name = campaign_name
        # ... existing code ...
```

## CLI Usage Examples

```bash
# List available campaigns
python parallel_orchestrator.py --list-campaigns

# Run a specific campaign (uses campaign's accounts, state, progress files)
python parallel_orchestrator.py --campaign podcast --workers 3 --run

# Check campaign status
python parallel_orchestrator.py --campaign podcast --status

# Reset campaign for new day
python parallel_orchestrator.py --campaign podcast --reset-day

# Default behavior (no --campaign) uses root-level files as before
python parallel_orchestrator.py --workers 3 --run
```

## Migration Path for Existing Setup

1. Existing CLI without --campaign flag continues to work (uses root-level accounts.txt, scheduler_state.json, parallel_progress.csv)

2. To create a campaign:
   ```bash
   mkdir -p campaigns/podcast/videos
   # Copy subset of accounts
   head -20 accounts.txt > campaigns/podcast/accounts.txt
   # Create campaign.json
   echo '{"name": "podcast", "max_posts_per_account_per_day": 1}' > campaigns/podcast/campaign.json
   # Initialize scheduler_state.json (empty template)
   echo '{"jobs": [], "accounts": []}' > campaigns/podcast/scheduler_state.json
   ```

3. Gradual adoption - users can create campaigns for specific content types while keeping existing workflow

## Key Simplifications (vs Original Task)

1. **NO parallel campaign execution** - campaigns run sequentially using same Appium ports
2. **NO port offset management** - removed appium_port_offset, CAMPAIGN_PORT_OFFSET_STRIDE
3. **NO CampaignManager class** - simple functions in orchestrator instead
4. **NO account isolation validation** - single campaign runs at a time, no conflicts possible
5. **NO port conflict checking** - same ports used for all campaigns
6. **Minimal new code** - CampaignConfig dataclass + CLI changes only

**Test Strategy:**

## Test Strategy

### 1. Unit Test - CampaignConfig Loading

```bash
# Test CampaignConfig.from_folder() loads correctly
python -c "
import tempfile, os, json
from config import CampaignConfig

# Create temp campaign folder
temp_dir = tempfile.mkdtemp()
campaign_dir = os.path.join(temp_dir, 'test_campaign')
os.makedirs(campaign_dir)

# Create campaign.json
with open(os.path.join(campaign_dir, 'campaign.json'), 'w') as f:
    json.dump({'name': 'test', 'max_posts_per_account_per_day': 2}, f)

# Create accounts.txt
with open(os.path.join(campaign_dir, 'accounts.txt'), 'w') as f:
    f.write('account1\\naccount2\\n')

# Create scheduler_state.json
with open(os.path.join(campaign_dir, 'scheduler_state.json'), 'w') as f:
    json.dump({'jobs': [], 'accounts': []}, f)

# Test loading
config = CampaignConfig.from_folder(campaign_dir)
assert config.name == 'test'
assert config.max_posts_per_account_per_day == 2
assert config.accounts_file.endswith('accounts.txt')

# Test validation
is_valid, errors = config.validate()
assert is_valid, f'Validation failed: {errors}'
print('CampaignConfig test PASSED')
"
```

### 2. Unit Test - Campaign Validation Fails on Missing Files

```bash
python -c "
import tempfile, os, json
from config import CampaignConfig

# Create campaign without accounts.txt
temp_dir = tempfile.mkdtemp()
campaign_dir = os.path.join(temp_dir, 'broken_campaign')
os.makedirs(campaign_dir)

with open(os.path.join(campaign_dir, 'campaign.json'), 'w') as f:
    json.dump({'name': 'broken'}, f)

config = CampaignConfig.from_folder(campaign_dir)
is_valid, errors = config.validate()
assert not is_valid, 'Should fail validation'
assert any('accounts.txt' in e for e in errors)
print('Validation test PASSED')
"
```

### 3. CLI Test - --list-campaigns

```bash
# Create test campaign
mkdir -p campaigns/cli_test
echo '{"name": "cli_test"}' > campaigns/cli_test/campaign.json
touch campaigns/cli_test/accounts.txt
echo '{"jobs": [], "accounts": []}' > campaigns/cli_test/scheduler_state.json

# Test list command
python parallel_orchestrator.py --list-campaigns
# Should show cli_test in output

# Cleanup
rm -rf campaigns/cli_test
```

### 4. CLI Test - --campaign with Invalid Name

```bash
# Test error handling for missing campaign
python parallel_orchestrator.py --campaign nonexistent --status 2>&1 | grep -q "not found"
echo "Invalid campaign test PASSED"
```

### 5. Integration Test - Campaign Status Check

```bash
# Create real test campaign
mkdir -p campaigns/integration_test
echo '{"name": "integration_test", "max_posts_per_account_per_day": 1}' > campaigns/integration_test/campaign.json
head -3 accounts.txt > campaigns/integration_test/accounts.txt
echo '{"jobs": [], "accounts": []}' > campaigns/integration_test/scheduler_state.json

# Run status check (non-destructive)
python parallel_orchestrator.py --campaign integration_test --status

# Verify output shows campaign-specific paths
# Should NOT show root-level parallel_progress.csv
```

### 6. Backward Compatibility Test

```bash
# Verify existing commands still work without --campaign flag
python parallel_orchestrator.py --status
# Should show root-level parallel_progress.csv stats

python parallel_orchestrator.py --workers 3 --help
# Should show --campaign option in help
```

### 7. Full Campaign Flow Test (Manual)

```bash
# 1. Create campaign
mkdir -p campaigns/test_flow/videos
head -5 accounts.txt > campaigns/test_flow/accounts.txt
echo '{"name": "test_flow"}' > campaigns/test_flow/campaign.json

# 2. Initialize scheduler_state.json with jobs
# (Use posting_scheduler.py --add-folder with modified paths)

# 3. Run campaign
python parallel_orchestrator.py --campaign test_flow --workers 1 --run

# 4. Check campaign progress
python parallel_orchestrator.py --campaign test_flow --status
# Should show campaigns/test_flow/progress.csv stats

# 5. Stop
python parallel_orchestrator.py --campaign test_flow --stop-all
```

## Subtasks

### 57.1. Add CampaignConfig dataclass and campaign directory constants to config.py

**Status:** pending  
**Dependencies:** None  

Create a new CampaignConfig dataclass in config.py that can load campaign configuration from a campaign folder structure, and add campaign-related constants to the existing Config class.

**Details:**

Add to config.py:

1. Add campaign constants to Config class:
   - CAMPAIGNS_DIR: str = "campaigns"
   - CAMPAIGN_CONFIG_FILE: str = "campaign.json"

2. Create CampaignConfig dataclass with:
   - name: str (campaign name like 'podcast', 'viral')
   - base_dir: str (campaign folder path)
   - accounts_file: str (path to accounts.txt within campaign)
   - state_file: str (path to scheduler_state.json within campaign)
   - progress_file: str (path to progress.csv within campaign)
   - max_posts_per_account_per_day: int = 1
   - enabled: bool = True
   - video_folders: List[str] = field(default_factory=list)

3. Implement class methods:
   - @classmethod from_folder(cls, campaign_folder: str) -> 'CampaignConfig' - loads campaign.json and constructs paths
   - validate(self) -> tuple[bool, List[str]] - checks accounts_file and state_file exist

The CampaignConfig should use dataclasses.field for mutable defaults and properly handle relative paths within the campaign folder. Import json and add the new dataclass after the existing Config class.

### 57.2. Add campaign CLI arguments and helper functions to parallel_orchestrator.py

**Status:** pending  
**Dependencies:** 57.1  

Add --campaign and --list-campaigns CLI arguments to parallel_orchestrator.py along with helper functions to load and list campaigns from the campaigns/ directory.

**Details:**

Modify parallel_orchestrator.py:

1. Add imports at top:
   - from config import CampaignConfig (after existing config imports)

2. Add helper functions after existing functions:
   - load_campaign(campaign_name: str) -> CampaignConfig:
     * Constructs path: os.path.join(Config.CAMPAIGNS_DIR, campaign_name)
     * Raises ValueError if folder doesn't exist
     * Returns CampaignConfig.from_folder(campaign_dir)
   
   - list_campaigns() -> List[CampaignConfig]:
     * Returns empty list if campaigns/ doesn't exist
     * Iterates os.listdir(Config.CAMPAIGNS_DIR)
     * For each subfolder with campaign.json, loads CampaignConfig.from_folder()
     * Catches and logs exceptions for malformed campaigns
     * Returns list of valid campaign configs

3. Add CLI arguments in main():
   - parser.add_argument('--campaign', '-c', type=str, default=None, help='Campaign name to run')
   - parser.add_argument('--list-campaigns', action='store_true', help='List all available campaigns')

4. Add --list-campaigns handler in main() (before other elif blocks):
   - Call list_campaigns()
   - Print each campaign: name, enabled status, accounts file path
   - Exit after listing

### 57.3. Integrate campaign selection into run_parallel_posting and seed_progress_file

**Status:** pending  
**Dependencies:** 57.1, 57.2  

Modify seed_progress_file() and run_parallel_posting() to accept campaign-specific file paths, and update the --run handler to load and use campaign config when --campaign is specified.

**Details:**

Modify parallel_orchestrator.py:

1. Update seed_progress_file() signature:
   - Add accounts_file: str = Config.ACCOUNTS_FILE parameter
   - Currently reads from state_file for jobs, but accounts come from account_list parameter
   - No change needed to seeding logic - it already accepts accounts_filter

2. Update run_parallel_posting() signature:
   - Add progress_file: str = None parameter (overrides config.progress_file)
   - Add state_file parameter already exists
   - In function body: if progress_file is not None, set config.progress_file = progress_file before using

3. Modify --run handler in main():
   - If args.campaign is specified:
     * Call load_campaign(args.campaign)
     * campaign.validate() and print errors if invalid
     * Load accounts from campaign.accounts_file into accounts_list
     * Set args.state_file = campaign.state_file
     * Set progress_file override = campaign.progress_file
     * Log: 'Running campaign: {campaign.name}'
   - Pass progress_file to run_parallel_posting()

4. Update show_status() to accept optional progress_file path:
   - Currently uses config.progress_file
   - Add parameter to override when viewing campaign status

5. Update --status and --reset-day handlers to respect --campaign flag:
   - If --campaign specified, use campaign's progress_file path
