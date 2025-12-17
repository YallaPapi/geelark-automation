# Task ID: 36

**Title:** Fix hardcoded ADB paths in utility scripts

**Status:** done

**Dependencies:** 25 ✓, 32 ✓

**Priority:** low

**Description:** Replace hardcoded ADB_PATH constants in 8 utility scripts with imports from config.py, using Config.ADB_PATH for the ADB executable and setup_environment() for ANDROID_HOME initialization where needed.

**Details:**

## Problem Statement

Eight utility scripts have hardcoded ADB paths that differ from the centralized `config.py`:

**Hardcoded path in utility scripts:**
```python
ADB_PATH = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
```

**Centralized config.py path (lines 35-38):**
```python
ANDROID_SDK_PATH: str = r"C:\Users\asus\Downloads\android-sdk"
ADB_PATH: str = os.path.join(ANDROID_SDK_PATH, "platform-tools", "adb.exe")
```

The hardcoded path points to a different location than the centralized config, which could cause issues if the ADB location changes.

## Files to Update

| File | ADB_PATH Line | ANDROID_HOME Line | Changes Needed |
|------|---------------|-------------------|----------------|
| debug_page_source.py | 12 | 6 | Replace both |
| fix_adbkeyboard.py | 18 | N/A | Replace ADB_PATH only |
| diagnose_adbkeyboard.py | 10 | N/A | Replace ADB_PATH only |
| setup_adbkeyboard.py | 17 | N/A | Replace ADB_PATH only |
| reprovision_phone.py | 21 | N/A | Replace ADB_PATH only |
| setup_clipboard_helper.py | 17 | N/A | Replace ADB_PATH only |
| test_full_flow_android15.py | 70 | 6 | Replace both |
| test_typing.py | 17 | N/A | Replace ADB_PATH only |

## Implementation Steps

### 1. Files with both ANDROID_HOME and ADB_PATH (2 files)

**debug_page_source.py:**
```python
# BEFORE (lines 5-12):
import os
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'
...
ADB_PATH = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"

# AFTER:
import os
from config import Config, setup_environment
setup_environment()
...
# Remove ADB_PATH constant, use Config.ADB_PATH directly in subprocess calls
```

**test_full_flow_android15.py:**
```python
# BEFORE (lines 5-6, 70):
import os
os.environ['ANDROID_HOME'] = r'C:\Users\asus\Downloads\android-sdk'
...
ADB = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"

# AFTER:
import os
from config import Config, setup_environment
setup_environment()
...
# Replace ADB variable with Config.ADB_PATH
```

### 2. Files with ADB_PATH only (6 files)

For each file, add the import and replace the constant:

```python
# BEFORE:
ADB_PATH = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"

# AFTER:
from config import Config
ADB_PATH = Config.ADB_PATH  # Or use Config.ADB_PATH directly
```

The files and their specific changes:

**fix_adbkeyboard.py (line 18):**
- Add `from config import Config` after line 16 (after geelark_client import)
- Replace line 18 with `ADB_PATH = Config.ADB_PATH`

**diagnose_adbkeyboard.py (line 10):**
- Add `from config import Config` after line 8 (after geelark_client import)
- Replace line 10 with `ADB_PATH = Config.ADB_PATH`

**setup_adbkeyboard.py (line 17):**
- Add `from config import Config` after line 15 (after geelark_client import)
- Replace line 17 with `ADB_PATH = Config.ADB_PATH`

**reprovision_phone.py (line 21):**
- Add `from config import Config` after line 19 (after geelark_client import)
- Replace line 21 with `ADB_PATH = Config.ADB_PATH`

**setup_clipboard_helper.py (line 17):**
- Add `from config import Config` after line 15 (after geelark_client import)
- Replace line 17 with `ADB_PATH = Config.ADB_PATH`

**test_typing.py (line 17):**
- Add `from config import Config` after line 15 (after geelark_client import)
- Replace line 17 with `ADB_PATH = Config.ADB_PATH`

## Alternative Approach: Direct Config.ADB_PATH Usage

Instead of aliasing `ADB_PATH = Config.ADB_PATH`, you could use `Config.ADB_PATH` directly in all subprocess calls. This is more explicit but requires more changes:

```python
# Instead of:
subprocess.run([ADB_PATH, "-s", device, "shell", cmd], ...)

# Use:
subprocess.run([Config.ADB_PATH, "-s", device, "shell", cmd], ...)
```

The alias approach (`ADB_PATH = Config.ADB_PATH`) minimizes code changes while still achieving centralization.

## Notes

- The hardcoded path (`platform-tools-latest-windows`) differs from config.py's path (`android-sdk/platform-tools`), indicating these files may have been using a different ADB installation
- After this change, all ADB operations will use the same ADB binary as the rest of the codebase
- The `setup_environment()` function should be called early (before Appium imports) in files that need ANDROID_HOME set

**Test Strategy:**

## Test Strategy

### 1. Import Verification for All Files
```bash
# Verify each file imports successfully after changes
python -c "import debug_page_source; print('debug_page_source OK')"
python -c "import fix_adbkeyboard; print('fix_adbkeyboard OK')"
python -c "import diagnose_adbkeyboard; print('diagnose_adbkeyboard OK')"
python -c "import setup_adbkeyboard; print('setup_adbkeyboard OK')"
python -c "import reprovision_phone; print('reprovision_phone OK')"
python -c "import setup_clipboard_helper; print('setup_clipboard_helper OK')"
python -c "import test_full_flow_android15; print('test_full_flow_android15 OK')"
python -c "import test_typing; print('test_typing OK')"
```

### 2. Verify ADB_PATH Resolution
```bash
# For files using ADB_PATH alias
python -c "
from config import Config
from fix_adbkeyboard import ADB_PATH
assert ADB_PATH == Config.ADB_PATH, f'Mismatch: {ADB_PATH} != {Config.ADB_PATH}'
print(f'SUCCESS: ADB_PATH = {ADB_PATH}')
"

# Repeat for other files with ADB_PATH
python -c "from diagnose_adbkeyboard import ADB_PATH; from config import Config; assert ADB_PATH == Config.ADB_PATH; print('diagnose_adbkeyboard OK')"
python -c "from setup_adbkeyboard import ADB_PATH; from config import Config; assert ADB_PATH == Config.ADB_PATH; print('setup_adbkeyboard OK')"
python -c "from reprovision_phone import ADB_PATH; from config import Config; assert ADB_PATH == Config.ADB_PATH; print('reprovision_phone OK')"
python -c "from setup_clipboard_helper import ADB_PATH; from config import Config; assert ADB_PATH == Config.ADB_PATH; print('setup_clipboard_helper OK')"
python -c "from test_typing import ADB_PATH; from config import Config; assert ADB_PATH == Config.ADB_PATH; print('test_typing OK')"
```

### 3. Verify ANDROID_HOME Environment Variable
```bash
# For files that call setup_environment()
python -c "
import os
# Clear any existing value
if 'ANDROID_HOME' in os.environ:
    del os.environ['ANDROID_HOME']

from config import Config, setup_environment
setup_environment()

assert os.environ.get('ANDROID_HOME') == Config.ANDROID_SDK_PATH, \
    f\"ANDROID_HOME mismatch: {os.environ.get('ANDROID_HOME')} != {Config.ANDROID_SDK_PATH}\"
print(f'SUCCESS: ANDROID_HOME = {os.environ[\"ANDROID_HOME\"]}')
"
```

### 4. Grep Verification - No Hardcoded Paths Remain
```bash
# Verify no hardcoded ADB paths remain in utility scripts
grep -l "platform-tools-latest-windows" debug_page_source.py fix_adbkeyboard.py diagnose_adbkeyboard.py setup_adbkeyboard.py reprovision_phone.py setup_clipboard_helper.py test_full_flow_android15.py test_typing.py

# Expected: No output (no files contain the hardcoded path)
```

### 5. Functional Smoke Test
```bash
# Test that ADB commands still work (requires a connected device)
python -c "
import subprocess
from config import Config

result = subprocess.run([Config.ADB_PATH, 'devices'], capture_output=True, text=True)
print('ADB devices output:')
print(result.stdout)
assert result.returncode == 0, 'ADB command failed'
print('SUCCESS: ADB command executed successfully')
"
```

### 6. Optional: Run Utility Script Help/Usage
```bash
# Verify scripts don't crash on startup
python fix_adbkeyboard.py --help 2>/dev/null || python fix_adbkeyboard.py 2>&1 | head -5
python diagnose_adbkeyboard.py --help 2>/dev/null || python diagnose_adbkeyboard.py 2>&1 | head -5
python setup_adbkeyboard.py --help 2>/dev/null || python setup_adbkeyboard.py 2>&1 | head -5
python reprovision_phone.py --help 2>/dev/null || python reprovision_phone.py 2>&1 | head -5
python setup_clipboard_helper.py --help 2>/dev/null || python setup_clipboard_helper.py 2>&1 | head -5
python test_typing.py --help 2>/dev/null || python test_typing.py 2>&1 | head -5
```
