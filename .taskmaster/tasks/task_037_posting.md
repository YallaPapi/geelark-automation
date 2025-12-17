# Task ID: 37

**Title:** Extract DeviceConnectionManager from SmartInstagramPoster

**Status:** done

**Dependencies:** 25 ✓, 29 ✓, 31 ✓, 32 ✓

**Priority:** high

**Description:** Create device_connection.py with a DeviceConnectionManager class that handles the device connection lifecycle, extracting the connect() method logic (~150 lines) from post_reel_smart.py that currently mixes Geelark API calls, ADB subprocess commands, and Appium connection.

**Details:**

## Current State Analysis

The `SmartInstagramPoster.connect()` method in `post_reel_smart.py` (lines 665-819, ~155 lines) currently handles:

1. **Geelark API calls** (via GeelarkClient):
   - `list_phones()` to find phone by name
   - `start_phone()` to boot the phone if not running
   - `get_phone_status()` to poll for boot completion
   - `enable_adb()` with retry loop for API failures
   - `get_adb_info()` to get IP/port/password

2. **ADB subprocess commands** (via subprocess.run):
   - `adb disconnect` to clean stale connections
   - `adb connect` to establish connection
   - `adb devices` polling to wait for device readiness
   - `adb shell glogin` for Geelark authentication

3. **Appium connection** (calls `connect_appium()` at the end)

## Implementation Plan

### 1. Create `device_connection.py` with DeviceConnectionManager class

```python
"""
Device Connection Manager - handles Geelark phone lifecycle and ADB connection.

Separates device connection concerns from Instagram posting logic.
"""
import subprocess
import time
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

from config import Config
from geelark_client import GeelarkClient

logger = logging.getLogger(__name__)

@dataclass
class DeviceInfo:
    """Information about a connected device."""
    phone_id: str
    phone_name: str
    device_address: str  # ip:port
    adb_password: str

class DeviceConnectionError(Exception):
    """Raised when device connection fails."""
    pass

class DeviceConnectionManager:
    """
    Manages the lifecycle of connecting to a Geelark cloud phone.
    
    Responsibilities:
    - Find phone by name via Geelark API
    - Start phone if not running
    - Enable ADB with retry logic
    - Establish ADB connection
    - Authenticate via glogin
    
    Usage:
        manager = DeviceConnectionManager(phone_name)
        device_info = manager.connect()
        # ... use device_info.device_address for Appium ...
        manager.disconnect()
    """
    
    ADB_PATH = Config.ADB_PATH
    
    def __init__(self, phone_name: str, client: GeelarkClient = None):
        self.phone_name = phone_name
        self.client = client or GeelarkClient()
        self.device_info: Optional[DeviceInfo] = None
        self._connected = False
```

### 2. Extract connection logic into methods

The DeviceConnectionManager should have these methods:

- `connect() -> DeviceInfo`: Main entry point, orchestrates the full connection
- `_find_phone() -> dict`: Find phone by name across multiple pages
- `_ensure_phone_running(phone_id: str) -> None`: Start phone and wait for boot
- `_enable_adb_with_retry(phone_id: str) -> dict`: Enable ADB with retry on API failures
- `_establish_adb_connection(ip: str, port: int, password: str) -> str`: Connect ADB and run glogin
- `_wait_for_adb_device(device_address: str, timeout: int) -> bool`: Poll until device appears in adb devices
- `disconnect() -> None`: Clean up connection
- `verify_connection() -> bool`: Check if ADB connection is still alive
- `reconnect() -> bool`: Re-establish dropped connection

### 3. Key implementation details from existing code

**Phone lookup with pagination** (lines 669-678):
```python
for page in range(1, 10):
    result = self.client.list_phones(page=page, page_size=100)
    for p in result["items"]:
        if p["serialName"] == self.phone_name or p["id"] == self.phone_name:
            # found
```

**ADB enable retry loop** (lines 703-758):
- Max 3 retries for enable_adb() API call
- 30 attempts × 2 seconds for get_adb_info() verification
- On failure, restart phone and retry the whole process

**ADB connection with device readiness** (lines 773-793):
- 30 attempts × 2 seconds = 60 seconds max wait
- Check for `\tdevice` in adb devices output (not `offline` or `unauthorized`)

**glogin retry** (lines 796-814):
- 3 attempts for glogin command
- Check for "success" or absence of "error"

### 4. Modify SmartInstagramPoster to use composition

```python
class SmartInstagramPoster:
    def __init__(self, phone_name, system_port=8200, appium_url=None):
        self.connection_manager = DeviceConnectionManager(phone_name)
        # ... rest of init ...
        
    def connect(self):
        """Connect to device using DeviceConnectionManager."""
        device_info = self.connection_manager.connect()
        self.phone_id = device_info.phone_id
        self.device = device_info.device_address
        self.connect_appium()
        return True
        
    def cleanup(self):
        """Cleanup after posting."""
        # ... existing cleanup ...
        self.connection_manager.disconnect()
```

### 5. Additional helper methods to extract

Also extract these related methods from SmartInstagramPoster:
- `verify_adb_connection()` (lines 821-829) → `DeviceConnectionManager.verify_connection()`
- `reconnect_adb()` (lines 831-863) → `DeviceConnectionManager.reconnect()`

### 6. Configuration integration

Use `Config.ADB_PATH` from centralized config (already done in post_reel_smart.py).

### 7. Logging

Use the module logger pattern consistent with other modules:
```python
logger = logging.getLogger(__name__)
```

### 8. Error handling

Create specific exceptions:
- `DeviceNotFoundError(DeviceConnectionError)`: Phone not found in Geelark
- `ADBEnableError(DeviceConnectionError)`: Failed to enable ADB after retries
- `ADBConnectionError(DeviceConnectionError)`: Failed to establish ADB connection

**Test Strategy:**

## Test Strategy

### 1. Unit Test - Module imports successfully
```bash
python -c "from device_connection import DeviceConnectionManager, DeviceInfo, DeviceConnectionError; print('Import OK')"
```

### 2. Unit Test - DeviceConnectionManager instantiation
```bash
python -c "
from device_connection import DeviceConnectionManager
manager = DeviceConnectionManager('test_phone')
assert manager.phone_name == 'test_phone'
assert manager.device_info is None
assert manager._connected is False
print('Instantiation OK')
"
```

### 3. Integration Test - Full connection flow (requires running phone)
```bash
# Use a known test account from accounts.txt
python -c "
from device_connection import DeviceConnectionManager

manager = DeviceConnectionManager('reelwisdompod_')
try:
    device_info = manager.connect()
    print(f'Connected to {device_info.device_address}')
    assert manager.verify_connection(), 'Connection verification failed'
finally:
    manager.disconnect()
print('Full flow OK')
"
```

### 4. Verify SmartInstagramPoster still works
```bash
# Test that the refactored SmartInstagramPoster works with DeviceConnectionManager
python -c "
from post_reel_smart import SmartInstagramPoster

poster = SmartInstagramPoster('reelwisdompod_')
# Check composition is set up correctly
assert hasattr(poster, 'connection_manager'), 'Missing connection_manager'
print('SmartInstagramPoster composition OK')
"
```

### 5. Verify parallel_worker.py still works
```bash
# Ensure the worker can still import and use SmartInstagramPoster
python -c "
from parallel_worker import execute_posting_job
print('parallel_worker imports OK')
"
```

### 6. End-to-end posting test (optional - uses real account)
```bash
# Only run if willing to make a real post
python posting_scheduler.py --add-folder chunk_01c --add-accounts reelwisdompod_ --run --limit 1
```

### 7. Verify error handling
```bash
# Test DeviceNotFoundError is raised for non-existent phone
python -c "
from device_connection import DeviceConnectionManager, DeviceConnectionError

manager = DeviceConnectionManager('nonexistent_phone_xyz123')
try:
    manager.connect()
    print('ERROR: Should have raised exception')
except DeviceConnectionError as e:
    print(f'Correctly raised DeviceConnectionError: {e}')
except Exception as e:
    print(f'Wrong exception type: {type(e).__name__}: {e}')
"
```

### 8. ADB path uses centralized config
```bash
python -c "
from device_connection import DeviceConnectionManager
from config import Config
assert DeviceConnectionManager.ADB_PATH == Config.ADB_PATH, 'ADB_PATH mismatch'
print(f'ADB_PATH correctly uses Config: {Config.ADB_PATH}')
"
```
