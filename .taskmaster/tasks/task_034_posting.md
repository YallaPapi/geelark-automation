# Task ID: 34

**Title:** Fix hardcoded ANDROID_HOME in posting_scheduler.py

**Status:** done

**Dependencies:** 16 ✓, 32 ✓

**Priority:** high

**Description:** Replace hardcoded ANDROID_HOME paths at lines 17-19 and 193-197 in posting_scheduler.py with centralized config.py imports, using setup_environment() for early initialization and Config.ANDROID_SDK_PATH in get_android_env().

**Details:**

## Problem Statement

The `posting_scheduler.py` module has hardcoded ANDROID_HOME paths in two locations that should use the centralized `config.py`:

**Location 1: Lines 17-19 (module-level initialization)**
```python
# Current hardcoded:
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'
os.environ['ANDROID_SDK_ROOT'] = r'C:\Users\asus\Downloads\android-sdk'
```

**Location 2: Lines 193-197 (get_android_env function)**
```python
# Current hardcoded:
android_sdk = r'C:\Users\asus\Downloads\android-sdk'
env['ANDROID_HOME'] = android_sdk
env['ANDROID_SDK_ROOT'] = android_sdk
```

## Implementation Steps

### Step 1: Add import at the top of posting_scheduler.py

After `import sys` (line 15), add:
```python
from config import Config, setup_environment
```

### Step 2: Replace lines 17-19 with setup_environment() call

Remove:
```python
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'
os.environ['ANDROID_SDK_ROOT'] = r'C:\Users\asus\Downloads\android-sdk'
```

Replace with:
```python
# Set ANDROID_HOME early for Appium - MUST be before any Appium imports
setup_environment()
```

### Step 3: Update get_android_env() function (lines 185-204)

Replace the hardcoded path with Config.ANDROID_SDK_PATH:
```python
def get_android_env() -> dict:
    """Get environment with ANDROID_HOME/ANDROID_SDK_ROOT properly set.

    This ensures Appium can find the Android SDK regardless of how
    the parent process was started.
    """
    env = os.environ.copy()

    # Use centralized config for Android SDK path
    android_sdk = Config.ANDROID_SDK_PATH

    env['ANDROID_HOME'] = android_sdk
    env['ANDROID_SDK_ROOT'] = android_sdk

    # Add platform-tools to PATH if not already there
    platform_tools = os.path.join(android_sdk, 'platform-tools')
    if platform_tools not in env.get('PATH', ''):
        env['PATH'] = platform_tools + os.pathsep + env.get('PATH', '')

    return env
```

### Alternative: Use get_adb_env() directly

Note: `config.py` already provides `get_adb_env()` which does the same thing as `get_android_env()`. Consider whether to:
1. Keep `get_android_env()` but use Config.ANDROID_SDK_PATH (recommended for minimal change)
2. Replace calls to `get_android_env()` with `get_adb_env()` from config (more DRY but larger change)

Option 1 is recommended for this task to minimize scope and risk.

## Files Modified

- `posting_scheduler.py` - lines 15-19 and 185-204

## Dependencies on This Change

This aligns with Task 32 (ADB path centralization) and Task 16 (Appium SDK detection), ensuring all Android SDK references flow through config.py.

**Test Strategy:**

## Test Strategy

### 1. Import verification
```bash
python -c "from posting_scheduler import get_android_env; from config import Config; env = get_android_env(); assert env['ANDROID_HOME'] == Config.ANDROID_SDK_PATH, f'Mismatch: {env[\"ANDROID_HOME\"]} != {Config.ANDROID_SDK_PATH}'; print(f'SUCCESS: ANDROID_HOME = {env[\"ANDROID_HOME\"]}')"
```

Expected output: `SUCCESS: ANDROID_HOME = C:\Users\asus\Downloads\android-sdk`

### 2. Environment variable test
```bash
python -c "
import os
# Clear any existing values
os.environ.pop('ANDROID_HOME', None)
os.environ.pop('ANDROID_SDK_ROOT', None)

# Import should trigger setup_environment()
import posting_scheduler

# Verify environment was set
from config import Config
assert os.environ.get('ANDROID_HOME') == Config.ANDROID_SDK_PATH, 'ANDROID_HOME not set'
assert os.environ.get('ANDROID_SDK_ROOT') == Config.ANDROID_SDK_PATH, 'ANDROID_SDK_ROOT not set'
print('SUCCESS: Environment variables set correctly on import')
"
```

### 3. No hardcoded paths remaining
```bash
# Verify no hardcoded android-sdk paths remain in posting_scheduler.py
grep -n "android-sdk" posting_scheduler.py
# Expected: No matches or only matches in comments
```

### 4. Functional test - Appium startup
```bash
# Test that Appium can still find Android SDK after the change
python -c "
from posting_scheduler import get_android_env, restart_appium
env = get_android_env()
print(f'ANDROID_HOME: {env.get(\"ANDROID_HOME\")}')
print(f'ANDROID_SDK_ROOT: {env.get(\"ANDROID_SDK_ROOT\")}')
print(f'PATH includes platform-tools: {\"platform-tools\" in env.get(\"PATH\", \"\")}')
"
```

### 5. Full scheduler status test
```bash
python posting_scheduler.py --status
# Should work without errors, showing Appium health status
```

### 6. Config consistency check
```bash
python -c "
from config import Config, get_adb_env
from posting_scheduler import get_android_env

config_env = get_adb_env()
sched_env = get_android_env()

assert config_env['ANDROID_HOME'] == sched_env['ANDROID_HOME'], 'ANDROID_HOME mismatch'
assert config_env['ANDROID_SDK_ROOT'] == sched_env['ANDROID_SDK_ROOT'], 'ANDROID_SDK_ROOT mismatch'
print('SUCCESS: Both modules use consistent Android SDK path')
"
```
