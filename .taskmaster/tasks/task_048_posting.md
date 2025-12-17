# Task ID: 48

**Title:** Fix bare except clauses in core modules

**Status:** done

**Dependencies:** 37 ✓, 38 ✓

**Priority:** medium

**Description:** Replace bare 'except:' clauses in device_connection.py and post_reel_smart.py with 'except Exception:' and add optional debug logging to improve error traceability without changing runtime behavior.

**Details:**

## Current State Analysis

Found 4 bare except clauses across the two core modules:

### device_connection.py (3 occurrences):

**1. Line 448 - reconnect_appium() method:**
```python
try:
    if self.appium_driver:
        self.appium_driver.quit()
except:
    pass
```
Context: Cleanup during Appium reconnection - silently ignores driver quit failures.

**2. Line 482 - disconnect() method (Appium cleanup):**
```python
try:
    if self.appium_driver:
        self.appium_driver.quit()
        print("  Appium driver closed")
except:
    pass
```
Context: Cleanup during disconnect - silently ignores driver quit failures.

**3. Line 487 - disconnect() method (ADB cleanup):**
```python
try:
    self.client.disable_adb(self.phone_id)
except:
    pass
```
Context: Cleanup during disconnect - silently ignores ADB disable failures.

### post_reel_smart.py (1 occurrence):

**4. Line 897 - cleanup() method:**
```python
try:
    self.adb("rm -f /sdcard/Download/*.mp4")
except:
    pass
```
Context: Cleanup after posting - silently ignores video deletion failures.

## Implementation Steps

### Step 1: Add optional logging infrastructure to device_connection.py

Since device_connection.py doesn't currently import logging, add a minimal optional logger:

```python
# At top of file, after existing imports
import logging

# Create module-level logger (only used when explicitly configured)
_logger = logging.getLogger(__name__)
```

### Step 2: Fix bare except in reconnect_appium() (line 448)

```python
# Before
except:
    pass

# After
except Exception as e:
    _logger.debug("Appium driver quit during reconnect failed: %s", e)
```

### Step 3: Fix bare excepts in disconnect() (lines 482, 487)

```python
# Line 482 - Appium cleanup
except Exception as e:
    _logger.debug("Appium driver quit during disconnect failed: %s", e)

# Line 487 - ADB cleanup  
except Exception as e:
    _logger.debug("disable_adb during disconnect failed: %s", e)
```

### Step 4: Add optional logging to post_reel_smart.py cleanup() (line 897)

Since post_reel_smart.py also doesn't import logging at module level:

```python
# At top of file, after existing imports
import logging
_logger = logging.getLogger(__name__)

# Line 897 fix
except Exception as e:
    _logger.debug("Video cleanup rm command failed: %s", e)
```

## Why 'except Exception:' Instead of More Specific Types

1. **Preserves original behavior**: Catches the same errors (all exceptions except SystemExit, KeyboardInterrupt, GeneratorExit)
2. **Best practice**: PEP 8 recommends avoiding bare except; `except Exception:` is the standard broad catch
3. **Still catches everything needed**: Subprocess errors, Appium WebDriver exceptions, network errors, etc.
4. **Doesn't catch control flow exceptions**: Allows KeyboardInterrupt to propagate (important for Ctrl+C handling during cleanup)

## Why Optional Debug Logging

1. **Zero overhead in production**: Debug logging is disabled by default
2. **Helps debugging**: When issues occur, enabling debug logging reveals silently-swallowed errors
3. **No behavior change**: The pass statement is effectively preserved (exception is caught, logged at debug level, then continues)
4. **Consistent pattern**: Establishes a pattern for other cleanup code in the codebase

**Test Strategy:**

## Test Strategy

### 1. Syntax and Import Verification
```bash
# Verify files have no syntax errors after changes
python -c "from device_connection import DeviceConnectionManager; print('device_connection.py OK')"
python -c "from post_reel_smart import SmartInstagramPoster; print('post_reel_smart.py OK')"
```

### 2. Verify No Bare Except Clauses Remain
```bash
# Search for bare except patterns - should return nothing
grep -n "except:" device_connection.py post_reel_smart.py | grep -v "except Exception"

# Expected: No output (all bare excepts replaced)
```

### 3. Verify Logging Import Added
```bash
python -c "
import ast
with open('device_connection.py', 'r') as f:
    tree = ast.parse(f.read())
imports = [node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)]
assert 'logging' in imports, 'logging not imported in device_connection.py'
print('device_connection.py: logging import present')
"

python -c "
import ast
with open('post_reel_smart.py', 'r') as f:
    tree = ast.parse(f.read())
imports = [node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)]
assert 'logging' in imports, 'logging not imported in post_reel_smart.py'
print('post_reel_smart.py: logging import present')
"
```

### 4. Functional Test - Disconnect Cleanup Works
```bash
python -c "
from device_connection import DeviceConnectionManager

# Create manager with dummy phone name - will fail to connect but disconnect should work
mgr = DeviceConnectionManager('nonexistent_test_phone')
mgr.phone_id = 'fake_id'  # Set fake ID
mgr.appium_driver = None  # No driver

# Call disconnect - should not raise even though operations will fail
try:
    mgr.disconnect()
    print('SUCCESS: disconnect() completes without raising')
except Exception as e:
    print(f'FAILURE: disconnect() raised: {e}')
"
```

### 5. Verify Debug Logging Works When Enabled
```bash
python -c "
import logging

# Enable debug logging for device_connection module
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('device_connection')
logger.setLevel(logging.DEBUG)

from device_connection import DeviceConnectionManager

# Create manager and trigger cleanup path
mgr = DeviceConnectionManager('test_phone_for_logging')
mgr.phone_id = 'fake'
mgr.appium_driver = None

# This should produce debug log output about cleanup failures
print('--- Debug output should appear below if logging works ---')
mgr.disconnect()
print('--- End debug output ---')
"
```

### 6. Verify Original Behavior Preserved (Exceptions Still Swallowed)
```bash
python -c "
from device_connection import DeviceConnectionManager

# Create a mock driver that raises on quit
class MockDriverThatRaises:
    def quit(self):
        raise RuntimeError('Simulated driver failure')

mgr = DeviceConnectionManager('test_phone')
mgr.phone_id = 'fake'
mgr.appium_driver = MockDriverThatRaises()

# disconnect should NOT raise despite the driver raising
try:
    mgr.disconnect()
    print('SUCCESS: Exceptions still properly swallowed in cleanup')
except Exception as e:
    print(f'FAILURE: Exception escaped cleanup: {e}')
"
```
