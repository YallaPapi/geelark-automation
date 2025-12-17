# Task ID: 44

**Title:** Create PhoneConnector helper for setup scripts

**Status:** done

**Dependencies:** 25 ✓, 31 ✓, 37 ✓

**Priority:** medium

**Description:** Create a lightweight PhoneConnector class that encapsulates the find→start→enable ADB→connect flow for use by setup scripts, eliminating ~70 lines of duplicated setup_phone() logic in setup_adbkeyboard.py and setup_clipboard_helper.py.

**Details:**

## Current State Analysis

Both `setup_adbkeyboard.py` and `setup_clipboard_helper.py` contain nearly identical `setup_phone()` logic (lines 42-99 in each file):

**Duplicated pattern in both scripts:**
```python
# 1. Find phone (lines 50-64)
for page in range(1, 10):
    result = client.list_phones(page=page, page_size=100)
    for p in result["items"]:
        if p["serialName"] == phone_name:
            phone = p
            break

# 2. Start phone if needed (lines 69-80)
if phone["status"] != 0:
    client.start_phone(phone_id)
    for i in range(60):
        time.sleep(2)
        status = client.get_phone_status([phone_id])
        ...

# 3. Enable ADB and connect (lines 82-99)
client.enable_adb(phone_id)
adb_info = client.get_adb_info(phone_id)
device = f"{adb_info['ip']}:{adb_info['port']}"
subprocess.run([ADB_PATH, "connect", device])
adb(device, f"glogin {password}")
```

## Architecture Decision

**Why not use DeviceConnectionManager?**
- `DeviceConnectionManager` (device_connection.py) is designed for the full posting workflow with Appium
- It has Appium-specific dependencies (`from appium import webdriver`)
- Setup scripts don't need Appium - they only need ADB access
- A lightweight helper avoids pulling in unnecessary dependencies

**Two-tier architecture:**
- **PhoneConnector** (new): Lightweight ADB-only flow for setup scripts
- **DeviceConnectionManager** (existing): Full Appium workflow for posting

## Implementation Plan

### 1. Create `phone_connector.py`

```python
"""
Lightweight phone connector for setup scripts.

This provides the basic find→start→ADB enable→connect flow without Appium.
For full posting workflow with Appium, use DeviceConnectionManager instead.
"""
import subprocess
import time
from typing import Optional, Tuple
from dataclasses import dataclass

from config import Config
from geelark_client import GeelarkClient

ADB_PATH = Config.ADB_PATH

@dataclass
class PhoneConnection:
    """Result of a successful phone connection."""
    client: GeelarkClient
    phone_id: str
    phone_name: str
    device_string: str  # "ip:port" format for ADB
    password: str

class PhoneConnectorError(Exception):
    """Raised when phone connection fails."""
    pass

class PhoneConnector:
    """
    Lightweight connector for Geelark phones - ADB only, no Appium.
    
    For setup scripts that need ADB access but not Appium.
    For full posting workflow, use DeviceConnectionManager instead.
    """
    
    def __init__(self, geelark_client: GeelarkClient = None):
        """
        Initialize the phone connector.
        
        Args:
            geelark_client: Optional GeelarkClient instance for dependency injection.
        """
        self.client = geelark_client or GeelarkClient()
    
    def find_phone(self, phone_name: str) -> Tuple[str, dict]:
        """
        Find a phone by name in Geelark.
        
        Args:
            phone_name: The serialName of the phone to find.
            
        Returns:
            Tuple of (phone_id, phone_info_dict)
            
        Raises:
            PhoneConnectorError: If phone not found.
        """
        print(f"Finding phone: {phone_name}")
        
        for page in range(1, 10):
            result = self.client.list_phones(page=page, page_size=100)
            for p in result["items"]:
                if p["serialName"] == phone_name:
                    phone_id = p["id"]
                    print(f"  Found: {p['serialName']} (Status: {p['status']})")
                    return phone_id, p
            if len(result["items"]) < 100:
                break
        
        raise PhoneConnectorError(f"Phone not found: {phone_name}")
    
    def ensure_running(self, phone_id: str, phone_status: int) -> bool:
        """
        Ensure the phone is running, starting it if necessary.
        
        Args:
            phone_id: The Geelark phone ID.
            phone_status: Current status (0=running, other=stopped).
            
        Returns:
            True when phone is ready.
        """
        if phone_status == 0:
            return True  # Already running
        
        print("  Starting phone...")
        self.client.start_phone(phone_id)
        
        for i in range(60):
            time.sleep(2)
            status = self.client.get_phone_status([phone_id])
            items = status.get("successDetails", [])
            if items and items[0].get("status") == 0:
                print(f"    Ready after {(i+1)*2}s")
                time.sleep(5)  # Extra stabilization time
                return True
        
        raise PhoneConnectorError(f"Phone {phone_id} failed to start after 120s")
    
    def connect_adb(self, phone_id: str) -> Tuple[str, str]:
        """
        Enable ADB and establish connection.
        
        Args:
            phone_id: The Geelark phone ID.
            
        Returns:
            Tuple of (device_string, password) where device_string is "ip:port".
        """
        print("  Enabling ADB...")
        self.client.enable_adb(phone_id)
        time.sleep(5)
        
        adb_info = self.client.get_adb_info(phone_id)
        device = f"{adb_info['ip']}:{adb_info['port']}"
        password = adb_info['pwd']
        
        print(f"  Connecting to {device}...")
        subprocess.run([ADB_PATH, "connect", device], capture_output=True)
        time.sleep(1)
        
        # glogin authentication
        result = subprocess.run(
            [ADB_PATH, "-s", device, "shell", f"glogin {password}"],
            capture_output=True, timeout=30,
            encoding='utf-8', errors='replace'
        )
        login_result = result.stdout.strip() if result.stdout else ""
        print(f"  Login: {login_result or 'OK'}")
        
        return device, password
    
    def setup_for_adb(self, phone_name: str) -> PhoneConnection:
        """
        Complete setup flow: find → start → enable ADB → connect.
        
        This is the main entry point for setup scripts.
        
        Args:
            phone_name: The serialName of the phone to connect.
            
        Returns:
            PhoneConnection with all connection details.
            
        Raises:
            PhoneConnectorError: On any failure.
        """
        phone_id, phone_info = self.find_phone(phone_name)
        self.ensure_running(phone_id, phone_info["status"])
        device, password = self.connect_adb(phone_id)
        
        return PhoneConnection(
            client=self.client,
            phone_id=phone_id,
            phone_name=phone_name,
            device_string=device,
            password=password
        )
```

### 2. Update `setup_adbkeyboard.py`

Replace lines 42-99 with:

```python
def setup_phone(phone_name):
    """Setup ADBKeyboard on a single phone"""
    from phone_connector import PhoneConnector, PhoneConnectorError
    
    print(f"\n{'='*50}")
    print(f"Setting up ADBKeyboard on: {phone_name}")
    print('='*50)
    
    try:
        connector = PhoneConnector()
        conn = connector.setup_for_adb(phone_name)
        device = conn.device_string
    except PhoneConnectorError as e:
        print(f"  ERROR: {e}")
        return False
    
    # Force uninstall first (clean slate)
    print("  Uninstalling existing ADBKeyboard (if any)...")
    uninstall_result = adb(device, "pm uninstall com.android.adbkeyboard")
    print(f"    {uninstall_result or 'Not installed'}")
    time.sleep(1)
    
    # ... rest of ADBKeyboard-specific logic (lines 107-131)
```

### 3. Update `setup_clipboard_helper.py`

Replace lines 42-99 with:

```python
def setup_phone(phone_name):
    """Setup ClipboardHelper on a single phone"""
    from phone_connector import PhoneConnector, PhoneConnectorError
    
    print(f"\n{'='*50}")
    print(f"Setting up ClipboardHelper on: {phone_name}")
    print('='*50)
    
    try:
        connector = PhoneConnector()
        conn = connector.setup_for_adb(phone_name)
        device = conn.device_string
    except PhoneConnectorError as e:
        print(f"  ERROR: {e}")
        return False
    
    # Check if already installed
    print("  Checking if ClipboardHelper is installed...")
    packages = adb(device, "pm list packages | grep geelark.clipboard")
    # ... rest of ClipboardHelper-specific logic (lines 104-129)
```

## Key Design Decisions

1. **Separate module, not in DeviceConnectionManager**: Keeps Appium dependency isolated
2. **PhoneConnection dataclass**: Clean return type with all connection details
3. **PhoneConnectorError exception**: Specific error handling without polluting DeviceConnectionError
4. **Dependency injection**: Optional GeelarkClient parameter for testing
5. **Idempotent**: Can be called multiple times safely (uses existing running phone)

**Test Strategy:**

## Test Strategy

### 1. Unit Test - Module imports successfully
```bash
python -c "from phone_connector import PhoneConnector, PhoneConnection, PhoneConnectorError; print('Import OK')"
```

### 2. Unit Test - PhoneConnector instantiation
```bash
python -c "
from phone_connector import PhoneConnector
connector = PhoneConnector()
print(f'Client type: {type(connector.client).__name__}')
print('Instantiation OK')
"
```

### 3. Integration Test - Find phone (read-only, safe)
```bash
python -c "
from phone_connector import PhoneConnector
connector = PhoneConnector()

# Use a known test phone name from accounts.txt
phone_id, info = connector.find_phone('reelwisdompod_')
print(f'Found: {info[\"serialName\"]} (ID: {phone_id})')
"
```

### 4. Integration Test - Full setup_for_adb flow
```bash
# Test with a real phone (will start if needed - costs minutes)
python -c "
from phone_connector import PhoneConnector
connector = PhoneConnector()
conn = connector.setup_for_adb('reelwisdompod_')
print(f'Connected to: {conn.device_string}')
print(f'Phone ID: {conn.phone_id}')
"
```

### 5. End-to-End Test - setup_adbkeyboard.py still works
```bash
# Test that the refactored script behaves identically
python setup_adbkeyboard.py reelwisdompod_

# Verify ADBKeyboard is enabled
adb -s <device> shell settings get secure default_input_method
# Should show: com.android.adbkeyboard/.AdbIME
```

### 6. End-to-End Test - setup_clipboard_helper.py still works
```bash
# Test that the refactored script behaves identically
python setup_clipboard_helper.py reelwisdompod_

# Verify ClipboardHelper is installed
adb -s <device> shell pm list packages | grep clipboard
# Should show: package:com.geelark.clipboard
```

### 7. Verify Code Reduction
```bash
# Before: Count lines in setup_phone() functions
# setup_adbkeyboard.py: lines 42-131 = ~90 lines
# setup_clipboard_helper.py: lines 42-129 = ~88 lines

# After: Each setup_phone() should be ~30-40 lines (APK-specific logic only)
# phone_connector.py: ~120 lines (shared by all setup scripts)
# Net reduction: ~60 lines duplicated code eliminated
```

### 8. Verify No Appium Dependency
```bash
# PhoneConnector should not import Appium
python -c "
import ast
with open('phone_connector.py', 'r') as f:
    tree = ast.parse(f.read())
imports = [node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import)]
from_imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
all_imports = imports + [m for m in from_imports if m]
assert 'appium' not in str(all_imports).lower(), 'PhoneConnector should not import Appium!'
print('No Appium dependency - OK')
"
```

### 9. Error Handling Test
```bash
# Test with non-existent phone
python -c "
from phone_connector import PhoneConnector, PhoneConnectorError
connector = PhoneConnector()
try:
    connector.find_phone('nonexistent_phone_12345')
    print('ERROR: Should have raised PhoneConnectorError')
except PhoneConnectorError as e:
    print(f'Correctly raised PhoneConnectorError: {e}')
"
```

### 10. Stop phone after testing (CRITICAL)
```bash
# ALWAYS stop phones after testing to save billing minutes
python -c "
from geelark_client import GeelarkClient
client = GeelarkClient()
for page in range(1, 20):
    result = client.list_phones(page=page, page_size=100)
    for phone in result['items']:
        if phone['status'] == 1:
            client.stop_phone(phone['id'])
            print(f'STOPPED: {phone[\"serialName\"]}')
    if len(result['items']) < 100:
        break
"
```
