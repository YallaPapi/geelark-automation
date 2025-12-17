# Task ID: 25

**Title:** Create centralized config.py with all paths and settings

**Status:** done

**Dependencies:** 16 ✓

**Priority:** medium

**Description:** Consolidate ADB_PATH, ANDROID_HOME, and other configuration values into a single config.py module that all other modules import from, eliminating scattered hardcoded paths and providing a single source of truth.

**Details:**

## Current State Analysis

A `config.py` already exists (lines 1-186) with a well-structured `Config` class containing:
- `ANDROID_SDK_PATH`, `ADB_PATH`, `PROJECT_ROOT`
- Appium settings (`APPIUM_BASE_PORT`, `DEFAULT_APPIUM_URL`)
- Parallel execution settings (`DEFAULT_NUM_WORKERS`, `MAX_WORKERS`, `SYSTEM_PORT_BASE`)
- Job execution settings (`MAX_POSTS_PER_ACCOUNT_PER_DAY`, `DELAY_BETWEEN_JOBS`, `JOB_TIMEOUT`)
- Retry settings (`MAX_RETRY_ATTEMPTS`, `RETRY_DELAY_MINUTES`, `NON_RETRYABLE_ERRORS`)
- File paths (`PROGRESS_FILE`, `STATE_FILE`, `LOGS_DIR`, `ACCOUNTS_FILE`)
- Timeout constants (`ADB_TIMEOUT`, `ADB_READY_TIMEOUT`, `APPIUM_CONNECT_TIMEOUT`, `PHONE_BOOT_TIMEOUT`)
- Helper functions: `setup_environment()`, `get_adb_env()`, `_validate_config()`

**Files already using config.py correctly:**
- `post_reel_smart.py` (lines 18-38): imports `Config, setup_environment`
- `parallel_config.py` (lines 25-87): imports `Config` and uses its values as defaults
- `parallel_worker.py` (line 47): uses `ADB_PATH = Config.ADB_PATH`
- `parallel_orchestrator.py` (line 412): uses `Config.ADB_PATH`

**Files with hardcoded paths that need migration:**
1. `adb_controller.py` (line 9): `ADB_PATH = r"C:\Users\...\adb.exe"` (different path!)
2. `diagnose_adbkeyboard.py` (line 10): `ADB_PATH = r"C:\Users\...\adb.exe"`
3. `setup_adbkeyboard.py` (line 17): `ADB_PATH = r"C:\Users\...\adb.exe"`
4. `setup_clipboard_helper.py` (line 17): `ADB_PATH = r"C:\Users\...\adb.exe"`
5. `fix_adbkeyboard.py` (line 18): `ADB_PATH = r"C:\Users\...\adb.exe"`
6. `reprovision_phone.py` (line 21): `ADB_PATH = r"C:\Users\...\adb.exe"`
7. `test_typing.py` (line 17): `ADB_PATH = r"C:\Users\...\adb.exe"`
8. `posting_scheduler.py` (lines 17-19): directly sets `os.environ['ANDROID_HOME']`
9. `debug_page_source.py` (line 6): sets `os.environ['ANDROID_HOME']`
10. `test_appium.py` (line 15): sets `os.environ['ANDROID_HOME']`
11. `test_appium_typing.py` (line 10): sets `os.environ['ANDROID_HOME']`
12. `test_dump_ui_fix.py` (line 6): sets `os.environ['ANDROID_HOME']`
13. `test_full_flow_android15.py` (line 6): sets `os.environ['ANDROID_HOME']`

## Implementation Steps

### 1. Expand config.py if needed
The existing `config.py` is well-structured. Verify it contains all needed settings. Add if missing:
- `APK_DIR` for APK file locations (ADBKeyboard.apk, ClipboardHelper.apk)

```python
# Add to Config class:
APK_DIR: str = os.path.dirname(os.path.abspath(__file__))
ADBKEYBOARD_APK: str = os.path.join(APK_DIR, "ADBKeyboard.apk")
CLIPBOARD_HELPER_APK: str = os.path.join(APK_DIR, "ClipboardHelper.apk")
```

### 2. Migrate adb_controller.py
```python
# Replace line 9
# OLD: ADB_PATH = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
# NEW:
from config import Config
ADB_PATH = Config.ADB_PATH
```

### 3. Migrate utility scripts
For each of these files, add at the top:
```python
from config import Config, setup_environment
setup_environment()  # Only if they use Appium

ADB_PATH = Config.ADB_PATH
APK_PATH = Config.ADBKEYBOARD_APK  # or CLIPBOARD_HELPER_APK as appropriate
```

Files: `diagnose_adbkeyboard.py`, `setup_adbkeyboard.py`, `setup_clipboard_helper.py`, `fix_adbkeyboard.py`, `reprovision_phone.py`, `test_typing.py`

### 4. Migrate posting_scheduler.py
```python
# Replace lines 17-19
# OLD:
# os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'
# os.environ['ANDROID_SDK_ROOT'] = r'C:\Users\asus\Downloads\android-sdk'
# NEW:
from config import Config, setup_environment
setup_environment()
```

Also remove duplicate `get_appium_env()` function (lines 186-199) and use `get_adb_env()` from config.py instead.

### 5. Migrate test files
For `debug_page_source.py`, `test_appium.py`, `test_appium_typing.py`, `test_dump_ui_fix.py`, `test_full_flow_android15.py`:
```python
# Replace direct os.environ calls
from config import Config, setup_environment
setup_environment()
ADB_PATH = Config.ADB_PATH
```

### 6. Address the ADB_PATH discrepancy
Note: Some files use `C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe` while config.py uses `C:\Users\asus\Downloads\android-sdk\platform-tools\adb.exe`. Verify which is correct and update config.py if needed:
```python
# If the standalone platform-tools is preferred:
ADB_PATH: str = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
# OR keep deriving from ANDROID_SDK_PATH if SDK path is correct
```

### 7. Update CLAUDE.md documentation
Update the Key Files table to emphasize config.py as the single source of truth:
```markdown
| File | Purpose |
|------|---------|
| `config.py` | **SINGLE SOURCE OF TRUTH** - All paths, settings, timeouts |
```

## Important Considerations

1. **Import order matters**: `setup_environment()` must be called BEFORE any Appium imports
2. **Backward compatibility**: Keep the module-level `ADB_PATH` variable for files that use it
3. **Validation**: `_validate_config()` runs on import and warns about missing paths
4. **Environment propagation**: Use `get_adb_env()` when spawning subprocesses

**Test Strategy:**

## Test Strategy

### 1. Verify config.py loads without errors
```bash
python -c "from config import Config, setup_environment; setup_environment(); print('OK')"
```

### 2. Verify all migrated files import successfully
```bash
# Test each migrated file
python -c "import adb_controller; print('adb_controller OK')"
python -c "import diagnose_adbkeyboard; print('diagnose_adbkeyboard OK')"
python -c "import setup_adbkeyboard; print('setup_adbkeyboard OK')"
python -c "import setup_clipboard_helper; print('setup_clipboard_helper OK')"
python -c "import fix_adbkeyboard; print('fix_adbkeyboard OK')"
python -c "import reprovision_phone; print('reprovision_phone OK')"
python -c "import posting_scheduler; print('posting_scheduler OK')"
```

### 3. Verify ADB_PATH is consistent across all modules
```bash
python -c "
from config import Config
import adb_controller
import post_reel_smart
import parallel_worker

paths = [
    ('config', Config.ADB_PATH),
    ('adb_controller', adb_controller.ADB_PATH),
    ('post_reel_smart', post_reel_smart.ADB_PATH),
    ('parallel_worker', parallel_worker.ADB_PATH),
]
for name, path in paths:
    print(f'{name}: {path}')

# All should be identical
unique = set(p for _, p in paths)
assert len(unique) == 1, f'ADB_PATH mismatch: {unique}'
print('All ADB_PATH values match!')
"
```

### 4. Verify environment is set up correctly
```bash
python -c "
import os
from config import setup_environment
setup_environment()
print(f\"ANDROID_HOME={os.environ.get('ANDROID_HOME')}\")
print(f\"ANDROID_SDK_ROOT={os.environ.get('ANDROID_SDK_ROOT')}\")
assert 'ANDROID_HOME' in os.environ
assert 'ANDROID_SDK_ROOT' in os.environ
print('Environment setup OK')
"
```

### 5. Grep verification - no hardcoded paths remain
```bash
# Search for hardcoded ADB paths (should only find config.py)
grep -r "platform-tools-latest-windows" *.py --include="*.py" | grep -v "archived/" | grep -v "config.py"
# Expected: no output (empty)

# Search for direct ANDROID_HOME assignments (should only find config.py)
grep -rn "os.environ\['ANDROID_HOME'\]" *.py --include="*.py" | grep -v "archived/" | grep -v "config.py"
# Expected: no output (empty)
```

### 6. Integration test - run actual posting workflow
```bash
# Test parallel orchestrator starts correctly
python parallel_orchestrator.py --status

# Test posting scheduler loads state
python posting_scheduler.py --status
```

### 7. Verify subprocess environment propagation
```bash
python -c "
from config import get_adb_env
env = get_adb_env()
assert 'ANDROID_HOME' in env
assert 'ANDROID_SDK_ROOT' in env
assert 'platform-tools' in env.get('PATH', '')
print('Subprocess environment OK')
"
```
