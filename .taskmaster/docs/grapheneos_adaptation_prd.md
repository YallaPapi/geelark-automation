# GrapheneOS Adaptation PRD

## Goal

Add GrapheneOS physical device support **alongside** existing Geelark cloud phones. Runtime flag selects which device backend to use. Geelark functionality remains 100% intact.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DUAL-DEVICE ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  parallel_orchestrator.py                                                   │
│  ├── --device geelark (default) → uses GeelarkDeviceManager                │
│  └── --device grapheneos        → uses GrapheneOSDeviceManager             │
│                                                                             │
│  parallel_worker.py                                                         │
│  ├── Reads device_type from config                                          │
│  └── Instantiates correct DeviceManager                                     │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │  DeviceManager (ABC - new base class)                            │       │
│  │  ├── ensure_connected() → bool                                   │       │
│  │  ├── get_adb_address() → str (ip:port or serial)                │       │
│  │  ├── upload_video(local_path) → remote_path                      │       │
│  │  ├── cleanup() → None                                            │       │
│  │  └── get_appium_caps() → dict                                    │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│           │                                    │                            │
│           ▼                                    ▼                            │
│  ┌─────────────────────────┐      ┌─────────────────────────┐              │
│  │  GeelarkDeviceManager   │      │  GrapheneOSDeviceManager │              │
│  │  (existing code refactored)    │  (NEW)                   │              │
│  │                         │      │                          │              │
│  │  • find_phone()         │      │  • get_device()          │              │
│  │  • start_phone()        │      │  • switch_profile()      │              │
│  │  • enable_adb()         │      │  • push_video()          │              │
│  │  • glogin auth          │      │  • list_profiles()       │              │
│  │  • Geelark API upload   │      │  • adb push upload       │              │
│  │  • stop_phone()         │      │  • (no stop needed)      │              │
│  └─────────────────────────┘      └─────────────────────────┘              │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │  UNCHANGED - Platform Agnostic Layer                             │       │
│  ├─────────────────────────────────────────────────────────────────┤       │
│  │  • AppiumUIController (appium_ui_controller.py)                  │       │
│  │  • HybridNavigator (hybrid_navigator.py)                         │       │
│  │  • ScreenDetector (screen_detector.py)                           │       │
│  │  • ActionEngine (action_engine.py)                               │       │
│  │  • SmartInstagramPoster.post() loop                              │       │
│  │  • TikTokPoster.post() loop                                      │       │
│  │  • TikTokHybridNavigator                                         │       │
│  │  • FlowLogger                                                    │       │
│  │  • ClaudeUIAnalyzer                                              │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## New Files to Create

| File | Purpose |
|------|---------|
| `device_manager_base.py` | Abstract base class `DeviceManager` |
| `grapheneos_device_manager.py` | GrapheneOS implementation |
| `grapheneos_config.py` | GrapheneOS-specific settings (profiles, serial, screen coords) |

## Files to Modify

| File | Changes |
|------|---------|
| `device_connection.py` | Refactor to implement `DeviceManager` interface (no logic changes) |
| `post_reel_smart.py` | Accept `DeviceManager` instead of hardcoded `DeviceConnectionManager` |
| `tiktok_poster.py` | Accept `DeviceManager` instead of hardcoded `DeviceConnectionManager` |
| `parallel_orchestrator.py` | Add `--device` flag |
| `parallel_worker.py` | Instantiate correct `DeviceManager` based on flag |
| `config.py` | Add Pixel 7 screen coordinates |

## Files NOT Changed

- `hybrid_navigator.py`
- `screen_detector.py`
- `action_engine.py`
- `appium_ui_controller.py`
- `geelark_client.py`
- `progress_tracker.py`
- `flow_logger.py`
- `claude_analyzer.py`

---

## Implementation Details

### 1. DeviceManager Base Class

Create `device_manager_base.py`:

```python
from abc import ABC, abstractmethod
from typing import Dict, Optional

class DeviceManager(ABC):
    """Abstract base class for device management."""

    @abstractmethod
    def ensure_connected(self, account_name: str) -> bool:
        """Ensure device is connected and ready for the given account.

        For Geelark: finds phone, starts it, enables ADB, authenticates
        For GrapheneOS: verifies USB connection, switches to correct profile
        """
        pass

    @abstractmethod
    def get_adb_address(self) -> str:
        """Get ADB connection address.

        For Geelark: returns "ip:port"
        For GrapheneOS: returns USB serial like "32271FDH2006RW"
        """
        pass

    @abstractmethod
    def upload_video(self, local_path: str) -> str:
        """Upload video to device, return remote path.

        For Geelark: uses Geelark API upload
        For GrapheneOS: uses adb push
        """
        pass

    @abstractmethod
    def get_appium_caps(self) -> Dict:
        """Get Appium desired capabilities for this device."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup after posting.

        For Geelark: stops phone
        For GrapheneOS: no-op (device stays on)
        """
        pass

    @property
    @abstractmethod
    def device_type(self) -> str:
        """Return 'geelark' or 'grapheneos'."""
        pass
```

### 2. GrapheneOS Device Manager

Create `grapheneos_device_manager.py`:

```python
import subprocess
import os
from typing import Dict, List, Optional
from device_manager_base import DeviceManager
from config import Config

class GrapheneOSDeviceManager(DeviceManager):
    """Device manager for GrapheneOS physical devices."""

    def __init__(self,
                 serial: str = "32271FDH2006RW",
                 profile_mapping: Dict[str, int] = None):
        """
        Args:
            serial: USB device serial number
            profile_mapping: Maps account names to profile user IDs
                            e.g. {"account1": 0, "account2": 10, "account3": 11}
        """
        self.serial = serial
        self.adb_path = Config.ADB_PATH
        self.profile_mapping = profile_mapping or {}
        self.current_profile: Optional[int] = None

    @property
    def device_type(self) -> str:
        return "grapheneos"

    def _adb(self, *args) -> subprocess.CompletedProcess:
        """Run ADB command."""
        cmd = [self.adb_path, '-s', self.serial] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    def ensure_connected(self, account_name: str) -> bool:
        """Verify USB connection and switch to correct profile."""
        # 1. Check device connected
        result = self._adb('get-state')
        if 'device' not in result.stdout:
            raise Exception(f"Device {self.serial} not connected")

        # 2. Get target profile for this account
        target_profile = self.profile_mapping.get(account_name)
        if target_profile is None:
            raise Exception(f"No profile mapped for account: {account_name}")

        # 3. Switch profile if needed
        current = self._get_current_user()
        if current != target_profile:
            self._switch_profile(target_profile)
            self.current_profile = target_profile

        return True

    def _get_current_user(self) -> int:
        """Get current Android user ID."""
        result = self._adb('shell', 'am', 'get-current-user')
        return int(result.stdout.strip())

    def _switch_profile(self, user_id: int) -> None:
        """Switch to a different Android user profile."""
        self._adb('shell', 'am', 'switch-user', str(user_id))
        # Wait for profile switch to complete
        import time
        time.sleep(3)

    def get_adb_address(self) -> str:
        """Return USB serial (used by Appium for USB connection)."""
        return self.serial

    def upload_video(self, local_path: str) -> str:
        """Push video to device via ADB."""
        filename = os.path.basename(local_path)
        remote_path = f"/sdcard/Download/{filename}"

        result = self._adb('push', local_path, remote_path)
        if result.returncode != 0:
            raise Exception(f"adb push failed: {result.stderr}")

        return remote_path

    def get_appium_caps(self) -> Dict:
        """Appium caps for USB-connected device."""
        return {
            'platformName': 'Android',
            'automationName': 'UiAutomator2',
            'udid': self.serial,
            'noReset': True,
            'fullReset': False,
            'newCommandTimeout': 300,
        }

    def cleanup(self) -> None:
        """No cleanup needed - physical device stays on."""
        pass

    def list_profiles(self) -> List[Dict]:
        """List all Android user profiles."""
        result = self._adb('shell', 'pm', 'list', 'users')
        profiles = []
        for line in result.stdout.split('\n'):
            if 'UserInfo{' in line:
                import re
                match = re.search(r'UserInfo\{(\d+):([^:]+):', line)
                if match:
                    profiles.append({
                        'id': int(match.group(1)),
                        'name': match.group(2),
                        'running': 'running' in line
                    })
        return profiles
```

### 3. Refactor GeelarkDeviceManager

Modify `device_connection.py` to implement the DeviceManager interface:

```python
# Add at top of existing device_connection.py
from device_manager_base import DeviceManager

# Modify class declaration
class DeviceConnectionManager(DeviceManager):
    """Geelark cloud phone device manager."""

    @property
    def device_type(self) -> str:
        return "geelark"

    # All existing methods stay exactly the same
    # Just add these interface methods that map to existing ones:

    def ensure_connected(self, account_name: str) -> bool:
        """Implementation using existing Geelark flow."""
        self.find_phone(account_name)
        self.start_phone_if_needed()
        self.enable_adb_with_retry()
        return True

    def get_adb_address(self) -> str:
        """Return Geelark ADB address."""
        return f"{self.adb_host}:{self.adb_port}"

    def upload_video(self, local_path: str) -> str:
        """Use existing Geelark upload."""
        return self._upload_video_to_phone(local_path)

    def get_appium_caps(self) -> Dict:
        """Appium caps for Geelark cloud phone."""
        return {
            'platformName': 'Android',
            'automationName': 'UiAutomator2',
            'deviceName': self.phone_name,
            'udid': f"{self.adb_host}:{self.adb_port}",
            'noReset': True,
        }

    def cleanup(self) -> None:
        """Stop Geelark phone."""
        self._stop_phone()
```

### 4. Modify SmartInstagramPoster

Update `post_reel_smart.py` to accept DeviceManager:

```python
class SmartInstagramPoster:
    def __init__(self,
                 device_manager: DeviceManager,
                 appium_url: str = None,
                 worker_id: int = 0):
        self.device_manager = device_manager
        self.appium_url = appium_url or Config.DEFAULT_APPIUM_URL
        # ... rest stays same

    def post(self, video_path: str, caption: str, ...) -> dict:
        # 1. Connect device (works for both Geelark and GrapheneOS)
        self.device_manager.ensure_connected(self.account_name)

        # 2. Upload video (each manager handles differently)
        remote_path = self.device_manager.upload_video(video_path)

        # 3. Start Appium session
        caps = self.device_manager.get_appium_caps()
        driver = webdriver.Remote(self.appium_url, caps)

        # 4. Run posting loop (UNCHANGED - platform agnostic)
        # ... existing hybrid navigation loop ...

        # 5. Cleanup
        self.device_manager.cleanup()
```

### 5. Modify TikTokPoster

Same changes as SmartInstagramPoster - accept DeviceManager instead of hardcoded DeviceConnectionManager.

### 6. Add --device Flag to Orchestrator

Update `parallel_orchestrator.py`:

```python
parser.add_argument('--device', '-d',
                    choices=['geelark', 'grapheneos'],
                    default='geelark',
                    help='Device type: geelark (cloud) or grapheneos (physical)')
```

### 7. Device Factory in Worker

Update `parallel_worker.py`:

```python
def create_device_manager(account_name: str, device_type: str) -> DeviceManager:
    """Factory function to create correct device manager."""
    if device_type == 'geelark':
        from device_connection import DeviceConnectionManager
        return DeviceConnectionManager(account_name)
    elif device_type == 'grapheneos':
        from grapheneos_device_manager import GrapheneOSDeviceManager
        from grapheneos_config import PROFILE_MAPPING
        return GrapheneOSDeviceManager(profile_mapping=PROFILE_MAPPING)
    else:
        raise ValueError(f"Unknown device type: {device_type}")
```

### 8. GrapheneOS Config

Create `grapheneos_config.py`:

```python
"""GrapheneOS-specific configuration."""

# Pixel 7 device serial
DEVICE_SERIAL = "32271FDH2006RW"

# Map account names to GrapheneOS profile user IDs
PROFILE_MAPPING = {
    # Profile 0 (Owner) accounts
    "account_owner_1": 0,
    "account_owner_2": 0,

    # Profile 10 accounts
    "account_profile1_1": 10,
    "account_profile1_2": 10,

    # Profile 11 accounts
    "account_profile2_1": 11,
    "account_profile2_2": 11,
}

# Pixel 7 screen coordinates (1080x2400)
PIXEL_SCREEN = {
    'center_x': 540,
    'center_y': 1200,
    'feed_top_y': 600,
    'feed_bottom_y': 1800,
}
```

### 9. Update Config.py

Add Pixel coordinates:

```python
# Device type options
DEVICE_TYPE_GEELARK = "geelark"
DEVICE_TYPE_GRAPHENEOS = "grapheneos"

# Pixel 7 screen coordinates (1080x2400 resolution)
PIXEL_SCREEN_CENTER_X: int = 540
PIXEL_SCREEN_CENTER_Y: int = 1200
PIXEL_FEED_TOP_Y: int = 600
PIXEL_FEED_BOTTOM_Y: int = 1800
PIXEL_SWIPE_DURATION: int = 300
```

---

## CLI Usage

```bash
# Geelark campaigns (UNCHANGED - existing behavior)
python parallel_orchestrator.py --campaign podcast --workers 5 --run
python parallel_orchestrator.py --campaign viral --workers 3 --run

# GrapheneOS campaigns (NEW)
python parallel_orchestrator.py --campaign podcast --device grapheneos --run
python parallel_orchestrator.py --campaign viral --device grapheneos --workers 1 --run

# Status check
python parallel_orchestrator.py --campaign podcast --device grapheneos --status

# Single post test
python post_reel_smart.py --device grapheneos --account myaccount video.mp4 "caption"
```

---

## Implementation Order

1. Create DeviceManager base class (`device_manager_base.py`)
2. Create GrapheneOSDeviceManager (`grapheneos_device_manager.py`)
3. Create GrapheneOS config (`grapheneos_config.py`)
4. Refactor DeviceConnectionManager to implement interface (`device_connection.py`)
5. Update SmartInstagramPoster to use DeviceManager (`post_reel_smart.py`)
6. Update TikTokPoster to use DeviceManager (`tiktok_poster.py`)
7. Add --device flag to orchestrator (`parallel_orchestrator.py`)
8. Add device factory to worker (`parallel_worker.py`)
9. Add Pixel coordinates to config (`config.py`)
10. Test Geelark still works (run existing campaign)
11. Test GrapheneOS Instagram (single post test)
12. Test GrapheneOS TikTok (single post test)

---

## Key Principles

1. **Geelark code stays intact** - Only adds interface implementation, no logic changes
2. **Factory pattern** - Runtime selection of device manager
3. **Same posting loop** - HybridNavigator works for both
4. **Profile-based isolation** - Each GrapheneOS profile = one "phone"
5. **Parallel support** - Multiple profiles can post simultaneously (with care)
