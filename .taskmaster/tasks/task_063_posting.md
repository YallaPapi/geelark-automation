# Task ID: 63

**Title:** Create Comprehensive Test and Verification Plan for Multi-Campaign Posting System

**Status:** done

**Dependencies:** 25 ✓, 50 ✓, 52 ✓

**Priority:** medium

**Description:** Develop detailed CLI manual tests, log verification steps, and unit/integration test specifications for all multi-campaign CLI commands covering podcast and viral campaigns.

**Details:**

Create a new file `tests/multi_campaign_test_plan.md` in the docs/tests/ folder (extend from Task 50's docs structure) with comprehensive test coverage following best practices from testing frameworks like pytest for unit/integration and manual CLI verification patterns.

## 1. CLI Manual Test Procedures

### Test Environment Setup
```bash
# Create test campaigns
mkdir -p test_campaigns/podcast test_campaigns/viral

# Podcast campaign files
echo "account1\naccount2" > test_campaigns/podcast/accounts.txt
echo "job1,fail\njob2,success" > test_campaigns/podcast/progress.csv
touch test_campaigns/podcast/state.json

# Viral campaign files
echo "account3\naccount4" > test_campaigns/viral/accounts.txt
echo "job3,in_progress" > test_campaigns/viral/progress.csv
touch test_campaigns/viral/state.json
```

### CLI Command Tests (Run for both campaigns)

**1. `--list-campaigns`**
```bash
python main.py multi-campaign --list-campaigns
# EXPECTED: Lists 'podcast' and 'viral' campaigns with status, last_run, posts_today
```

**2. `--seed-only podcast`**
```bash
python main.py multi-campaign --seed-only podcast
# EXPECTED: Creates podcast/progress.csv and podcast/state.json with headers
# VERIFY: grep 'account_name,job_id,status' test_campaigns/podcast/progress.csv
```

**3. `--run podcast` / `--run viral`**
```bash
python main.py multi-campaign --run podcast --max-workers 1
# EXPECTED: LOGS show 'Using campaign: podcast', 'Loading accounts.txt from podcast/', progress updates
```

**4. `--status podcast`**
```bash
# EXPECTED: Shows campaign stats: accounts loaded, jobs pending/success/failed, last run time
```

**5. `--reset-day podcast`**
```bash
# EXPECTED: Resets daily counters in progress.csv, logs 'Daily counters reset for podcast'
```

**6. `--retry-all-failed podcast`**
```bash
# EXPECTED: Only failed jobs from progress.csv are retried, success markers preserved
```

## 2. Log Verification Steps
Create `verify_campaign_logs.py` script:
```python
import re, glob

def verify_campaign_logs(campaign_name):
    logs = glob.glob(f'logs/multi_campaign_{campaign_name}_*.log')
    for log in logs:
        with open(log) as f:
            content = f.read()
            # Verify correct paths used
            assert re.search(rf'{campaign_name}/accounts\.txt', content), 'Wrong accounts.txt path'
            assert re.search(rf'{campaign_name}/progress\.csv', content), 'Wrong progress.csv path'
            assert re.search(rf'{campaign_name}/state\.json', content), 'Wrong state file path'
            print(f'✓ {log} verified')

verify_campaign_logs('podcast')
verify_campaign_logs('viral')
```

## 3. Unit/Integration Test Suite (pytest)

**tests/test_campaign_path_selection.py**
```python
from multi_campaign_manager import get_campaign_paths

def test_podcast_paths():
    paths = get_campaign_paths('podcast')
    assert paths['accounts'] == 'test_campaigns/podcast/accounts.txt'
    assert paths['progress'] == 'test_campaigns/podcast/progress.csv'

def test_missing_accounts_file():
    with pytest.raises(FileNotFoundError):
        get_campaign_paths('missing')
```

**tests/test_campaign_operations.py**
```python
class TestCampaignIsolation:
    def test_podcast_operation_uses_podcast_progress(self):
        # Run podcast operation
        run_campaign('podcast')
        # Verify viral progress.csv unchanged
        assert not os.path.exists('test_campaigns/viral/progress.csv')

    def test_error_handling_missing_state(self, tmp_path):
        # Remove state.json, verify graceful fallback
        pass
```

## Best Practices Incorporated
- **Isolation**: Each test verifies campaign-specific file usage
- **Idempotency**: Operations don't corrupt other campaigns
- **Error Recovery**: Missing files handled gracefully
- **Logging Verification**: Structured logs confirm correct paths
- **pytest Patterns**: Fixtures for test campaigns, parametrize for campaign types

**Test Strategy:**

### 1. File Creation Verification
```bash
ls -la docs/tests/multi_campaign_test_plan.md
wc -l docs/tests/multi_campaign_test_plan.md  # Should be 200+ lines
ls -la tests/verify_campaign_logs.py
ls -la tests/test_campaign_*.py
```

### 2. CLI Manual Tests Execution
```bash
# Run full test suite
cd test_campaigns
python ../verify_campaign_logs.py

# Execute each CLI command and capture output
python main.py multi-campaign --list-campaigns > test_list.out
grep -E 'podcast|viral' test_list.out  # Should match both campaigns

# Test isolation
python main.py multi-campaign --run podcast
python main.py multi-campaign --status viral  # Should show unchanged viral state
```

### 3. pytest Unit/Integration Tests
```bash
pip install pytest
pytest tests/test_campaign_path_selection.py -v
pytest tests/test_campaign_operations.py -v

# Coverage
pytest --cov=multi_campaign_manager tests/ --cov-report=term-missing
# Target: 90%+ coverage of path selection and campaign isolation logic
```

### 4. End-to-End Verification
```bash
# 1. Seed both campaigns
python main.py multi-campaign --seed-only podcast
python main.py multi-campaign --seed-only viral

# 2. Run podcast only
python main.py multi-campaign --run podcast --max-workers=1

# 3. Verify viral untouched
python verify_campaign_logs.py viral  # Should confirm no viral logs
cat test_campaigns/viral/progress.csv  # Should be unchanged

# 4. Cross-verify logs
grep 'Using campaign: podcast' logs/*.log | wc -l  # Should match run count
```

### 5. Edge Case Tests
- Missing accounts.txt → Graceful error
- Corrupt progress.csv → Auto-reset option
- Concurrent runs → Proper locking
- Invalid campaign name → Helpful error message

**Success Criteria**: All manual CLI tests pass, pytest 95% coverage, log verification confirms isolation, no cross-campaign interference.
