# Multi-Campaign Posting System Test Plan

## Status: READY FOR EXECUTION

This document provides a comprehensive test and verification plan for the multi-campaign posting system supporting both `podcast` and `viral` campaigns.

---

## 1. Test Environment Setup

### Prerequisites

```bash
# Ensure you're in the project root
cd /c/Users/asus/Desktop/projects/geelark-automation

# Verify campaign structure exists
ls -la campaigns/
```

### Required Campaign Structure

Each campaign folder must contain:
```
campaigns/
├── viral/
│   ├── accounts.txt          # One account per line
│   ├── captions.csv          # filename,post_caption columns
│   ├── progress.csv          # Auto-generated job tracking
│   └── grq/                   # Videos folder (or similar)
│       └── *.mp4
└── podcast/
    ├── accounts.txt
    ├── captions.csv
    ├── progress.csv
    └── videos/
        └── *.mp4
```

### Create Test Podcast Campaign (if not exists)

```bash
# Create podcast campaign structure for testing
mkdir -p campaigns/podcast/videos

# Create test accounts
cat > campaigns/podcast/accounts.txt << 'EOF'
testaccount1
testaccount2
testaccount3
EOF

# Create test captions CSV
cat > campaigns/podcast/captions.csv << 'EOF'
filename,post_caption
testvideo1.mp4,Test caption for podcast video 1
testvideo2.mp4,Test caption for podcast video 2
EOF

# Create dummy video files for testing
touch campaigns/podcast/videos/testvideo1.mp4
touch campaigns/podcast/videos/testvideo2.mp4
```

---

## 2. CLI Manual Test Procedures

### Test 2.1: List Campaigns (`--list-campaigns`)

**Command:**
```bash
python parallel_orchestrator.py --list-campaigns
```

**Expected Output:**
```
============================================================
AVAILABLE CAMPAIGNS
============================================================

  viral [ENABLED]
    Accounts:     20
    Videos:       .../campaigns/viral/grq
    Captions:     .../campaigns/viral/captions.csv
    Progress:     .../campaigns/viral/progress.csv
    Daily limit:  1 posts/account

  podcast [ENABLED]
    Accounts:     3
    Videos:       .../campaigns/podcast/videos
    ...

============================================================
Usage: python parallel_orchestrator.py --campaign <name> --run
============================================================
```

**Verification:**
- [ ] Both campaigns listed
- [ ] Correct account counts displayed
- [ ] Correct file paths shown

---

### Test 2.2: Campaign Status (`--campaign <name> --status`)

#### 2.2.1 Viral Campaign Status

**Command:**
```bash
python parallel_orchestrator.py --campaign viral --status
```

**Expected Output:**
```
============================================================
PARALLEL POSTING STATUS - campaign 'viral'
============================================================

Progress (.../campaigns/viral/progress.csv):
  Total jobs:  X
  Pending:     X
  ...

Campaign Info:
  Name: viral
  Videos: .../campaigns/viral/grq
  Accounts: 20
```

**Verification:**
- [ ] Title shows `campaign 'viral'`
- [ ] Progress file path is `campaigns/viral/progress.csv`
- [ ] Campaign Info section shows campaign details
- [ ] Accounts loaded from `campaigns/viral/accounts.txt`

#### 2.2.2 Podcast Campaign Status

**Command:**
```bash
python parallel_orchestrator.py --campaign podcast --status
```

**Verification:**
- [ ] Title shows `campaign 'podcast'`
- [ ] Progress file path is `campaigns/podcast/progress.csv`
- [ ] Accounts loaded from `campaigns/podcast/accounts.txt`

#### 2.2.3 Legacy Mode Status (No Campaign)

**Command:**
```bash
python parallel_orchestrator.py --status
```

**Verification:**
- [ ] Title shows `legacy mode (root files)`
- [ ] Progress file is `parallel_progress.csv` (root level)
- [ ] No Campaign Info section

---

### Test 2.3: Seed Only (`--campaign <name> --seed-only`)

#### 2.3.1 Seed Viral Campaign

**Pre-condition:** Backup or archive existing progress file
```bash
# Optional: Archive existing progress
cp campaigns/viral/progress.csv campaigns/viral/progress_backup.csv
```

**Command:**
```bash
python parallel_orchestrator.py --campaign viral --seed-only
```

**Verification:**
- [ ] Log shows: `Seeding progress file for campaign 'viral'`
- [ ] Jobs seeded from `campaigns/viral/captions.csv`
- [ ] Accounts used from `campaigns/viral/accounts.txt`
- [ ] Progress file written to `campaigns/viral/progress.csv`
- [ ] Root `parallel_progress.csv` is UNCHANGED

```bash
# Verify campaign progress file was created/updated
head -5 campaigns/viral/progress.csv

# Verify root progress file unchanged (compare timestamps)
ls -la parallel_progress.csv
```

#### 2.3.2 Seed Podcast Campaign

**Command:**
```bash
python parallel_orchestrator.py --campaign podcast --seed-only
```

**Verification:**
- [ ] Progress file created at `campaigns/podcast/progress.csv`
- [ ] Viral progress file UNCHANGED
- [ ] Root progress file UNCHANGED

---

### Test 2.4: Reset Day (`--campaign <name> --reset-day`)

#### 2.4.1 Reset Viral Campaign Day

**Command:**
```bash
python parallel_orchestrator.py --campaign viral --reset-day
```

**Expected Output:**
```
============================================================
DAILY RESET - Archiving progress file for campaign 'viral'
============================================================
... Archived to campaigns/viral/progress_YYYYMMDD.csv
... Reset complete for campaign 'viral'
```

**Verification:**
- [ ] Archive created: `campaigns/viral/progress_YYYYMMDD.csv`
- [ ] Fresh progress file created: `campaigns/viral/progress.csv`
- [ ] Only headers in new progress file
- [ ] Podcast campaign UNCHANGED
- [ ] Root files UNCHANGED

```bash
# Verify archive was created
ls -la campaigns/viral/progress_*.csv

# Verify fresh progress file has only headers
wc -l campaigns/viral/progress.csv  # Should be 1 (header only)
```

#### 2.4.2 Reset Podcast Campaign Day

**Command:**
```bash
python parallel_orchestrator.py --campaign podcast --reset-day
```

**Verification:**
- [ ] Only affects `campaigns/podcast/progress.csv`
- [ ] Viral campaign UNCHANGED

---

### Test 2.5: Retry All Failed (`--campaign <name> --retry-all-failed`)

#### Pre-condition: Ensure there are failed jobs
```bash
# Check for failed jobs in viral campaign
grep ',failed,' campaigns/viral/progress.csv | wc -l
```

#### 2.5.1 Retry Viral Failed Jobs

**Command:**
```bash
python parallel_orchestrator.py --campaign viral --retry-all-failed
```

**Expected Behavior:**
- Only failed jobs in `campaigns/viral/progress.csv` are reset to `retrying`
- Podcast campaign UNCHANGED
- Root files UNCHANGED

**Verification:**
```bash
# Check failed jobs converted to retrying
grep ',retrying,' campaigns/viral/progress.csv | wc -l

# Verify podcast unchanged
diff campaigns/podcast/progress.csv campaigns/podcast/progress.csv.bak 2>/dev/null || echo "No changes to podcast"
```

#### 2.5.2 Retry Podcast Failed Jobs

**Command:**
```bash
python parallel_orchestrator.py --campaign podcast --retry-all-failed
```

**Verification:**
- [ ] Only affects `campaigns/podcast/progress.csv`

---

### Test 2.6: Run Campaign (`--campaign <name> --run`)

**WARNING:** This test actually starts phones and posts. Use with caution.

#### 2.6.1 Dry Run Verification (Check Logs Only)

**Command:**
```bash
python parallel_orchestrator.py --campaign viral --workers 1 --run
# Press Ctrl+C after seeing initial logs
```

**Verification in Logs:**
- [ ] `Loaded campaign 'viral'`
- [ ] `Progress: campaigns/viral/progress.csv`
- [ ] `Accounts: 20` (or correct count)
- [ ] `Starting posting for campaign 'viral'`
- [ ] Workers use campaign-specific files

#### 2.6.2 Campaign Isolation Test

Run viral campaign, then verify podcast is unchanged:

```bash
# Run viral
python parallel_orchestrator.py --campaign viral --workers 1 --run

# After completion, verify podcast unchanged
python parallel_orchestrator.py --campaign podcast --status
# Should show original state, not affected by viral run
```

---

### Test 2.7: Error Handling Tests

#### 2.7.1 Non-Existent Campaign

**Command:**
```bash
python parallel_orchestrator.py --campaign nonexistent --status
```

**Expected:**
- Exit code 1
- Error message: `Campaign folder not found: ...`
- Lists available campaigns

#### 2.7.2 Missing Accounts File

**Setup:**
```bash
mv campaigns/podcast/accounts.txt campaigns/podcast/accounts.txt.bak
```

**Command:**
```bash
python parallel_orchestrator.py --campaign podcast --status
```

**Expected:**
- Clear error about missing accounts.txt

**Cleanup:**
```bash
mv campaigns/podcast/accounts.txt.bak campaigns/podcast/accounts.txt
```

#### 2.7.3 Missing Captions File

**Setup:**
```bash
mv campaigns/podcast/captions.csv campaigns/podcast/captions.csv.bak
```

**Command:**
```bash
python parallel_orchestrator.py --campaign podcast --seed-only
```

**Expected:**
- Clear error about missing captions CSV

**Cleanup:**
```bash
mv campaigns/podcast/captions.csv.bak campaigns/podcast/captions.csv
```

---

## 3. Log Verification Procedures

### 3.1 Verify Campaign-Specific File Usage

After running any campaign command, check logs for correct file paths:

```bash
# Pattern: Should see campaign-specific paths, NOT root paths
grep -E "(progress|accounts|captions)" logs/orchestrator*.log | tail -20

# Should see:
# - campaigns/viral/progress.csv (NOT parallel_progress.csv)
# - campaigns/viral/accounts.txt (NOT accounts.txt)
# - campaigns/viral/captions.csv (NOT root captions file)
```

### 3.2 Automated Log Verification Script

```python
#!/usr/bin/env python3
"""verify_campaign_logs.py - Verify campaign isolation in logs"""

import re
import sys
from pathlib import Path

def verify_campaign_logs(campaign_name: str, log_content: str) -> list:
    """Check log content for correct campaign file usage."""
    errors = []

    # Should see campaign-specific paths
    campaign_path = f"campaigns/{campaign_name}/"
    if campaign_path not in log_content:
        errors.append(f"Missing campaign path: {campaign_path}")

    # Should NOT see root-level files when campaign is active
    root_patterns = [
        (r"parallel_progress\.csv(?!/)", "Root progress file used instead of campaign"),
        (r"(?<!/campaigns/\w+/)accounts\.txt", "Root accounts file used"),
    ]

    for pattern, msg in root_patterns:
        if re.search(pattern, log_content):
            errors.append(msg)

    return errors

if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else "viral"

    # Read most recent log
    log_files = sorted(Path("logs").glob("*.log"), key=lambda p: p.stat().st_mtime)
    if log_files:
        content = log_files[-1].read_text()
        errors = verify_campaign_logs(campaign, content)

        if errors:
            print(f"FAIL: {campaign} campaign")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print(f"PASS: {campaign} campaign uses correct files")
    else:
        print("No log files found")
```

---

## 4. Unit/Integration Test Specifications

### 4.1 Path Selection Tests (`tests/test_campaign_paths.py`)

```python
"""Unit tests for campaign path selection."""
import pytest
from config import CampaignConfig, PostingContext, Config

class TestCampaignPathSelection:
    """Test correct path selection with and without --campaign."""

    def test_campaign_mode_uses_campaign_progress_file(self):
        """When campaign specified, use campaign progress file."""
        campaign = CampaignConfig.from_folder("campaigns/viral")
        ctx = PostingContext.from_campaign(campaign)

        assert "campaigns/viral/progress.csv" in ctx.progress_file
        assert "parallel_progress.csv" not in ctx.progress_file

    def test_campaign_mode_uses_campaign_accounts(self):
        """When campaign specified, use campaign accounts file."""
        campaign = CampaignConfig.from_folder("campaigns/viral")
        ctx = PostingContext.from_campaign(campaign)

        assert "campaigns/viral/accounts.txt" in ctx.accounts_file

    def test_legacy_mode_uses_root_files(self):
        """When no campaign, use root-level files."""
        ctx = PostingContext.legacy()

        assert ctx.progress_file == Config.PROGRESS_FILE
        assert ctx.accounts_file == Config.ACCOUNTS_FILE

    def test_is_campaign_mode_true_for_campaigns(self):
        """is_campaign_mode() returns True for campaign context."""
        campaign = CampaignConfig.from_folder("campaigns/viral")
        ctx = PostingContext.from_campaign(campaign)

        assert ctx.is_campaign_mode() is True

    def test_is_campaign_mode_false_for_legacy(self):
        """is_campaign_mode() returns False for legacy context."""
        ctx = PostingContext.legacy()

        assert ctx.is_campaign_mode() is False


class TestCampaignErrorHandling:
    """Test error handling for missing campaign files."""

    def test_missing_campaign_folder_raises_error(self):
        """FileNotFoundError when campaign folder doesn't exist."""
        with pytest.raises(FileNotFoundError) as exc:
            CampaignConfig.from_folder("campaigns/nonexistent")

        assert "not found" in str(exc.value).lower()

    def test_missing_accounts_file_raises_error(self, tmp_path):
        """ValueError when accounts.txt missing."""
        # Create campaign folder without accounts.txt
        campaign_dir = tmp_path / "test_campaign"
        campaign_dir.mkdir()
        (campaign_dir / "captions.csv").write_text("filename,caption\n")
        (campaign_dir / "videos").mkdir()

        with pytest.raises(ValueError) as exc:
            CampaignConfig.from_folder(str(campaign_dir))

        assert "accounts" in str(exc.value).lower()

    def test_missing_captions_file_raises_error(self, tmp_path):
        """ValueError when captions CSV missing."""
        campaign_dir = tmp_path / "test_campaign"
        campaign_dir.mkdir()
        (campaign_dir / "accounts.txt").write_text("account1\n")
        (campaign_dir / "videos").mkdir()

        with pytest.raises(ValueError) as exc:
            CampaignConfig.from_folder(str(campaign_dir))

        assert "captions" in str(exc.value).lower()


class TestCampaignIsolation:
    """Test that operations only affect active campaign."""

    def test_retry_all_failed_only_affects_campaign(self):
        """retry_all_failed_ctx only modifies campaign's progress file."""
        from parallel_orchestrator import retry_all_failed_ctx

        # Create contexts for both campaigns
        viral = CampaignConfig.from_folder("campaigns/viral")
        viral_ctx = PostingContext.from_campaign(viral)

        # Get initial state of podcast (if exists)
        podcast_progress_before = None
        try:
            podcast = CampaignConfig.from_folder("campaigns/podcast")
            with open(podcast.progress_file) as f:
                podcast_progress_before = f.read()
        except FileNotFoundError:
            pass

        # Run retry on viral
        retry_all_failed_ctx(viral_ctx, include_non_retryable=False)

        # Verify podcast unchanged
        if podcast_progress_before:
            with open(podcast.progress_file) as f:
                assert f.read() == podcast_progress_before

    def test_reset_day_only_affects_campaign(self):
        """reset_day_ctx only archives campaign's progress file."""
        # This test would verify campaign isolation for reset
        pass  # Implementation depends on test fixtures
```

### 4.2 Integration Test: Full Campaign Workflow

```python
"""Integration tests for campaign workflow."""
import pytest
import subprocess
from pathlib import Path

class TestCampaignWorkflow:
    """End-to-end campaign workflow tests."""

    @pytest.fixture
    def test_campaign(self, tmp_path):
        """Create a temporary test campaign."""
        campaign_dir = tmp_path / "test_campaign"
        campaign_dir.mkdir()

        (campaign_dir / "accounts.txt").write_text("test_account1\ntest_account2\n")
        (campaign_dir / "captions.csv").write_text("filename,post_caption\nvid1.mp4,Caption 1\n")
        (campaign_dir / "videos").mkdir()
        (campaign_dir / "videos" / "vid1.mp4").touch()

        return campaign_dir

    def test_list_campaigns_includes_all(self):
        """--list-campaigns shows all valid campaigns."""
        result = subprocess.run(
            ["python", "parallel_orchestrator.py", "--list-campaigns"],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "viral" in result.stdout

    def test_campaign_status_shows_correct_info(self):
        """--campaign viral --status shows campaign-specific info."""
        result = subprocess.run(
            ["python", "parallel_orchestrator.py", "--campaign", "viral", "--status"],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "campaign 'viral'" in result.stdout
        assert "campaigns/viral/progress.csv" in result.stdout or "Campaign Info" in result.stdout

    def test_invalid_campaign_returns_error(self):
        """--campaign invalid --status returns error."""
        result = subprocess.run(
            ["python", "parallel_orchestrator.py", "--campaign", "invalid123", "--status"],
            capture_output=True, text=True
        )

        assert result.returncode != 0
```

---

## 5. Test Execution Checklist

### Quick Smoke Test (5 minutes)

- [ ] `python parallel_orchestrator.py --list-campaigns` - Lists campaigns
- [ ] `python parallel_orchestrator.py --campaign viral --status` - Shows viral status
- [ ] `python parallel_orchestrator.py --status` - Shows legacy status
- [ ] `python parallel_orchestrator.py --campaign nonexistent --status` - Shows error

### Full Test Suite (30 minutes)

1. [ ] Test 2.1: List Campaigns
2. [ ] Test 2.2: Status (viral, podcast, legacy)
3. [ ] Test 2.3: Seed Only (viral, podcast)
4. [ ] Test 2.4: Reset Day (viral)
5. [ ] Test 2.5: Retry All Failed
6. [ ] Test 2.7: Error Handling
7. [ ] Section 3: Log Verification
8. [ ] Run pytest unit tests

### Campaign Isolation Verification

After any test:
- [ ] Viral operations don't modify podcast files
- [ ] Podcast operations don't modify viral files
- [ ] Campaign operations don't modify root files
- [ ] Legacy operations don't modify campaign files

---

## 6. Success Criteria

| Test Category | Criteria |
|---------------|----------|
| CLI Commands | All 6 commands work for both campaigns |
| File Isolation | Each campaign uses only its own files |
| Error Handling | Clear errors for missing campaigns/files |
| Legacy Mode | Root files used when no --campaign |
| Log Verification | Logs show correct campaign paths |
| Unit Tests | All pytest tests pass |

---

## Appendix: Quick Reference Commands

```bash
# List all campaigns
python parallel_orchestrator.py --list-campaigns

# Viral campaign commands
python parallel_orchestrator.py --campaign viral --status
python parallel_orchestrator.py --campaign viral --seed-only
python parallel_orchestrator.py --campaign viral --reset-day
python parallel_orchestrator.py --campaign viral --retry-all-failed
python parallel_orchestrator.py --campaign viral --workers 3 --run

# Podcast campaign commands
python parallel_orchestrator.py --campaign podcast --status
python parallel_orchestrator.py --campaign podcast --seed-only
python parallel_orchestrator.py --campaign podcast --reset-day
python parallel_orchestrator.py --campaign podcast --retry-all-failed
python parallel_orchestrator.py --campaign podcast --workers 3 --run

# Legacy mode (no campaign)
python parallel_orchestrator.py --status
python parallel_orchestrator.py --seed-only
python parallel_orchestrator.py --reset-day
python parallel_orchestrator.py --retry-all-failed
python parallel_orchestrator.py --workers 3 --run
```
