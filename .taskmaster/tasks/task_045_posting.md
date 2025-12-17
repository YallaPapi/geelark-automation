# Task ID: 45

**Title:** Consolidate ADB helper functions into DeviceConnectionManager

**Status:** done

**Dependencies:** 40 ✓, 25 ✓, 37 ✓

**Priority:** medium

**Description:** Move the standalone ADB helper functions (wait_for_adb, ensure_device_alive, reconnect_adb) from parallel_worker.py into DeviceConnectionManager as class methods, providing a single source for all ADB-related operations and eliminating ~105 lines of duplicated code.

**Details:**

## Current State Analysis

### Duplicated Functions in parallel_worker.py (lines 69-173):
```python
# wait_for_adb(device_id, timeout=90, logger=None) -> bool (lines 69-107)
# - Polls ADB devices list until device appears
# - Returns True when device shows as "device" (not "offline")
# - Used before Appium session creation

# ensure_device_alive(device_id, logger=None) -> bool (lines 110-139)
# - Single check if device is in ADB devices list
# - Returns True if device is present and not offline
# - Used for health checks during job execution

# reconnect_adb(device_id, logger=None) -> bool (lines 142-173)
# - Disconnects and reconnects ADB to device
# - Returns True if reconnection successful
# - Used for recovery from dropped connections
```

### Similar Methods Already in DeviceConnectionManager:
- `_wait_for_device_ready()` (lines 198-218) - similar to wait_for_adb but instance-based
- `verify_adb_connection()` (lines 238-246) - similar to ensure_device_alive
- `reconnect_adb()` (lines 248-278) - instance-based, fetches password from Geelark

## Implementation Plan

### Step 1: Add Static/Class Methods to DeviceConnectionManager

Add these as **static methods** (don't require self) for device-agnostic operations:

```python
# device_connection.py - add after existing imports

@staticmethod
def wait_for_device(device_id: str, timeout: int = 90, logger=None) -> bool:
    """
    Wait for a device to appear in ADB devices list.
    
    This is the explicit ADB readiness gate - call AFTER starting phone
    but BEFORE creating Appium session.
    
    Args:
        device_id: Device identifier (e.g., "192.168.1.100:5555")
        timeout: Maximum seconds to wait (default 90)
        logger: Optional logger for status updates
    
    Returns:
        True if device is ready, False on timeout
    """
    deadline = time.time() + timeout
    check_count = 0
    
    while time.time() < deadline:
        check_count += 1
        try:
            result = subprocess.run(
                [ADB_PATH, "devices"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                if device_id in line and "device" in line and "offline" not in line:
                    if logger:
                        logger.info(f"ADB ready for {device_id} (took {check_count * 2}s)")
                    return True
        except Exception as e:
            if logger:
                logger.debug(f"ADB check error: {e}")
        
        time.sleep(2)
    
    if logger:
        logger.error(f"ADB timeout ({timeout}s) waiting for {device_id}")
    return False

@staticmethod
def is_device_alive(device_id: str, logger=None) -> bool:
    """
    Check if a device is present in ADB devices list.
    
    Call periodically during job execution to detect device loss.
    
    Args:
        device_id: Device identifier (e.g., "192.168.1.100:5555")
        logger: Optional logger for status updates
    
    Returns:
        True if device is alive, False if lost
    """
    try:
        result = subprocess.run(
            [ADB_PATH, "devices"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if device_id in line and "device" in line and "offline" not in line:
                return True
        if logger:
            logger.warning(f"Device {device_id} not found in ADB devices")
        return False
    except Exception as e:
        if logger:
            logger.warning(f"ADB devices check failed: {e}")
        return False

@staticmethod
def reconnect_device(device_id: str, logger=None) -> bool:
    """
    Attempt to reconnect an ADB device (disconnect + connect).
    
    Args:
        device_id: Device identifier (e.g., "192.168.1.100:5555")
        logger: Optional logger for status updates
    
    Returns:
        True if reconnect successful, False otherwise
    """
    try:
        # First disconnect
        subprocess.run([ADB_PATH, "disconnect", device_id],
                      capture_output=True, timeout=10)
        
        # Then reconnect
        result = subprocess.run([ADB_PATH, "connect", device_id],
                               capture_output=True, text=True, timeout=30)
        
        if "connected" in result.stdout.lower():
            if logger:
                logger.info(f"Reconnected ADB to {device_id}")
            return True
        else:
            if logger:
                logger.warning(f"ADB reconnect failed: {result.stdout}")
            return False
    except Exception as e:
        if logger:
            logger.warning(f"ADB reconnect error: {e}")
        return False
```

### Step 2: Refactor Existing Instance Methods to Use Static Methods

Update existing instance methods to delegate to the new static methods:

```python
# Update _wait_for_device_ready to use wait_for_device
def _wait_for_device_ready(self, max_attempts: int = 30) -> None:
    """Wait for device to appear in ADB devices list."""
    timeout = max_attempts * 2  # Each check is ~2 seconds
    if not DeviceConnectionManager.wait_for_device(self.device, timeout):
        raise Exception(f"Device {self.device} never appeared in ADB devices list after {timeout}s")

# Update verify_adb_connection to use is_device_alive
def verify_adb_connection(self) -> bool:
    """Verify device is still connected via ADB."""
    return DeviceConnectionManager.is_device_alive(self.device)
```

### Step 3: Update parallel_worker.py to Import and Use DeviceConnectionManager

```python
# parallel_worker.py - change imports
from device_connection import DeviceConnectionManager

# Remove the three standalone functions (lines 69-173)
# Replace all usages:

# Old: wait_for_adb(device_id, timeout, logger)
# New: DeviceConnectionManager.wait_for_device(device_id, timeout, logger)

# Old: ensure_device_alive(device_id, logger)  
# New: DeviceConnectionManager.is_device_alive(device_id, logger)

# Old: reconnect_adb(device_id, logger)
# New: DeviceConnectionManager.reconnect_device(device_id, logger)
```

### Step 4: Update Any Other Files Using These Functions

Search for other files importing these functions and update them similarly.

## Key Design Decisions

1. **Static methods vs instance methods**: Using static methods because these operations don't require instance state - they work on any device ID. This allows parallel_worker.py to call them without instantiating DeviceConnectionManager.

2. **Naming conventions**:
   - `wait_for_device()` - more general than `wait_for_adb()` 
   - `is_device_alive()` - clearer than `ensure_device_alive()`
   - `reconnect_device()` - consistent with existing naming

3. **Logger parameter**: Keep optional logger parameter for worker process logging integration.

4. **Backward compatibility**: Existing instance methods (`verify_adb_connection`, `reconnect_adb`) continue to work but delegate to static methods internally.

**Test Strategy:**

## Test Strategy

### 1. Verify Static Methods Import and Work Standalone
```bash
python -c "
from device_connection import DeviceConnectionManager

# Test that static methods exist and are callable
print('wait_for_device:', callable(DeviceConnectionManager.wait_for_device))
print('is_device_alive:', callable(DeviceConnectionManager.is_device_alive))
print('reconnect_device:', callable(DeviceConnectionManager.reconnect_device))

# Test with fake device (should return False, not crash)
result = DeviceConnectionManager.is_device_alive('192.168.99.99:5555')
print(f'is_device_alive for fake device: {result}')
assert result == False, 'Should return False for non-existent device'
print('All static method tests passed!')
"
```

### 2. Verify parallel_worker.py Imports Successfully
```bash
python -c "
from parallel_worker import run_worker, setup_worker_logging
from device_connection import DeviceConnectionManager
print('Import successful - no standalone ADB functions should exist')

# Verify old functions don't exist at module level
import parallel_worker
assert not hasattr(parallel_worker, 'wait_for_adb'), 'wait_for_adb should be removed'
assert not hasattr(parallel_worker, 'ensure_device_alive'), 'ensure_device_alive should be removed'
assert not hasattr(parallel_worker, 'reconnect_adb'), 'reconnect_adb should be removed'
print('Old functions properly removed!')
"
```

### 3. Verify Instance Methods Still Work
```bash
python -c "
from device_connection import DeviceConnectionManager

# Create instance (won't connect, just verify method exists)
manager = DeviceConnectionManager('test_phone')

# Verify instance methods exist and are callable
assert callable(manager.verify_adb_connection), 'Instance method should exist'
print('Instance methods verified!')
"
```

### 4. Line Count Verification
```bash
# Before: Count lines in parallel_worker.py
wc -l parallel_worker.py
# Should be ~550 lines

# After: Should be ~445 lines (105 lines removed)
# The functions removed span lines 69-173 (105 lines)
```

### 5. Integration Test - Run Worker Startup
```bash
# Run parallel_worker.py in dry-run mode to verify imports work
python parallel_worker.py --worker-id 0 --help
# Should show help without import errors
```

### 6. Full Integration Test (with actual phones)
```bash
# Test full posting flow works with consolidated ADB operations
python parallel_orchestrator.py --workers 1 --run

# Monitor logs for:
# - "ADB ready for" messages (from wait_for_device)
# - No import errors
# - Jobs complete successfully
```

### 7. Verify Code Deduplication
```bash
# Search for duplicate ADB patterns
grep -n "ADB_PATH.*devices" parallel_worker.py device_connection.py
# Should only find matches in device_connection.py, not parallel_worker.py
```
