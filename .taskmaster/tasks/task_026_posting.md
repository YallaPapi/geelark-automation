# Task ID: 26

**Title:** Archive deprecated files to archived/ folder

**Status:** done

**Dependencies:** 25 ✓

**Priority:** medium

**Description:** Move all .backup.py files, batch_post_ARCHIVED.py, batch_post_concurrent_ARCHIVED.py, post_to_instagram.py, and post_reel.py to an archived/ directory to clean up the main codebase while preserving historical code.

**Details:**

## Current State Analysis

Based on codebase analysis, the deprecated files have already been moved to `archived/`:
- `archived/batch_post_ARCHIVED.py` (8,988 bytes)
- `archived/batch_post_concurrent_ARCHIVED.py` (7,743 bytes)
- `archived/post_reel.py` (14,372 bytes)
- `archived/post_reel_smart.backup.py` (29,764 bytes)
- `archived/post_to_instagram.py` (7,420 bytes)
- `archived/setup_adbkeyboard.backup.py` (4,993 bytes)
- `archived/setup_clipboard_helper.backup.py` (5,071 bytes)

Git status shows these files as deleted from the main directory (marked with `D`), indicating they've been moved but not yet committed.

## Implementation Details

### 1. Verify No Active Imports

Grep analysis confirms no active Python files import from the deprecated modules:
- No `from batch_post` imports found
- No `from post_reel` (excluding `post_reel_smart`) imports found  
- No `from post_to_instagram` imports found

### 2. Update .gitignore (Optional)

Consider whether to track `archived/` in git:
- **Option A (Recommended)**: Keep `archived/` tracked in git for historical reference
- **Option B**: Add `archived/` to `.gitignore` if disk space is a concern

Current `.gitignore` does not exclude `archived/`, which is the correct default.

### 3. Update Documentation References

The following documentation files reference deprecated files and may need updates:
- `reviews/coupling_cohesion_analysis.md` (lines 163, 300, 308, 516) - References `post_to_instagram.py` in historical context
- These references are acceptable as they document the evolution of the codebase

### 4. Add README to archived/ Folder

Create `archived/README.md` to document why these files were archived:

```markdown
# Archived Files

This directory contains deprecated scripts that are no longer in active use.
These files are preserved for historical reference only.

## Why Archived

- **batch_post_ARCHIVED.py** - Replaced by `posting_scheduler.py` with better state management
- **batch_post_concurrent_ARCHIVED.py** - Replaced by `parallel_orchestrator.py` 
- **post_reel.py** - Original posting script, replaced by `post_reel_smart.py` with Appium support
- **post_to_instagram.py** - Early implementation using ADBController, deprecated in favor of Appium-based `post_reel_smart.py`
- **setup_adbkeyboard.backup.py** - Backup of ADB keyboard setup before Android 15 migration
- **setup_clipboard_helper.backup.py** - Backup of clipboard helper setup
- **post_reel_smart.backup.py** - Pre-Appium version of smart posting script

## DO NOT USE

These scripts are NOT maintained and should NOT be used for any purpose other than historical reference.
The current production scripts are:
- `parallel_orchestrator.py` - Main batch posting entry point
- `posting_scheduler.py` - Single-threaded alternative
- `post_reel_smart.py` - Core posting logic (used by both)
```

### 5. Stage and Commit Changes

The files have been moved but the git changes need to be staged and committed:

```bash
git add archived/
git add -A  # Stage deletions from root
git status  # Verify changes
git commit -m "chore: archive deprecated posting scripts to archived/ folder"
```

### 6. Verify No Broken References

After archiving, verify the main scripts still work:
- `python -c "import posting_scheduler"` should succeed
- `python -c "import parallel_orchestrator"` should succeed
- `python -c "import post_reel_smart"` should succeed

**Test Strategy:**

## Test Strategy

### 1. Verify Archive Directory Contents

```bash
# List all files in archived/
ls -la archived/

# Expected: 7 Python files + optional README.md
# - batch_post_ARCHIVED.py
# - batch_post_concurrent_ARCHIVED.py
# - post_reel.py
# - post_reel_smart.backup.py
# - post_to_instagram.py
# - setup_adbkeyboard.backup.py
# - setup_clipboard_helper.backup.py
```

### 2. Verify Main Directory is Clean

```bash
# Check no .backup.py files remain in root
ls *.backup.py 2>/dev/null && echo "ERROR: backup files still in root" || echo "OK: no backup files in root"

# Check deprecated scripts are gone from root
ls batch_post_ARCHIVED.py batch_post_concurrent_ARCHIVED.py post_reel.py post_to_instagram.py 2>/dev/null && echo "ERROR: deprecated files in root" || echo "OK: deprecated files moved"
```

### 3. Verify No Broken Imports

```bash
# Test all main scripts can be imported
python -c "import posting_scheduler; print('posting_scheduler: OK')"
python -c "import parallel_orchestrator; print('parallel_orchestrator: OK')"
python -c "import post_reel_smart; print('post_reel_smart: OK')"
python -c "import parallel_worker; print('parallel_worker: OK')"
python -c "import progress_tracker; print('progress_tracker: OK')"
python -c "import geelark_client; print('geelark_client: OK')"
```

### 4. Verify Git Status

```bash
# Check git status shows clean working directory after commit
git status

# Expected output after commit:
# "nothing to commit, working tree clean" (or only untracked files)
```

### 5. Verify No Import References to Archived Files

```bash
# Search for any imports of archived modules in active code
grep -r "from batch_post" --include="*.py" --exclude-dir=archived || echo "No batch_post imports found"
grep -r "from post_reel\b" --include="*.py" --exclude-dir=archived || echo "No post_reel imports found"
grep -r "from post_to_instagram" --include="*.py" --exclude-dir=archived || echo "No post_to_instagram imports found"
grep -r "import batch_post" --include="*.py" --exclude-dir=archived || echo "No batch_post imports found"
grep -r "import post_reel\b" --include="*.py" --exclude-dir=archived || echo "No post_reel imports found"
```

### 6. Run Smoke Test of Main Entry Points

```bash
# Verify main scripts can show their help/usage
python posting_scheduler.py --status
python parallel_orchestrator.py --status
```

### 7. Verify README Exists in archived/ (if created)

```bash
test -f archived/README.md && echo "README exists" || echo "README missing (optional)"
```
