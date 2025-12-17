# Task ID: 3

**Title:** Design Geelark device control abstraction

**Status:** done

**Dependencies:** 1 ✓

**Priority:** high

**Description:** Create an abstraction layer to control Geelark cloud phones for screenshots, taps, typing, app launching, and file transfer, independent of the underlying mechanism (RPA, ADB, or API).

**Details:**

Implementation details:
- Define an interface `GeelarkDeviceController` with methods:
  - `connect(account_name: str) -> DeviceHandle`
  - `launch_app(device: DeviceHandle, app_id: str)` (e.g. Instagram)
  - `tap(device, x: int, y: int)`
  - `type_text(device, text: str)`
  - `screenshot(device) -> bytes` (PNG/JPEG bytes)
  - `swipe(device, x1, y1, x2, y2, duration_ms)`
  - `upload_file(device, local_path: str, remote_path: str) -> str` (returns remote path or URI).
- Implement an initial MVP adapter that talks to Geelark via whichever is available first (e.g. ADB over TCP or a Geelark HTTP API). For now, define stub methods that raise `NotImplementedError` but with clear signatures.
- Provide a mapping from `account_name` to `device_id` (config or simple dict) for the MVP single device.
- Include sensible timeouts and retry wrappers around network calls.
- Pseudo-code skeleton:
```python
# geelark_control.py
from dataclasses import dataclass

@dataclass
class DeviceHandle:
    id: str

class GeelarkDeviceController:
    def connect(self, account_name: str) -> DeviceHandle:
        # map account -> device_id (MVP: single device)
        raise NotImplementedError

    def launch_app(self, device: DeviceHandle, app_id: str):
        raise NotImplementedError

    def tap(self, device: DeviceHandle, x: int, y: int):
        raise NotImplementedError

    def type_text(self, device: DeviceHandle, text: str):
        raise NotImplementedError

    def screenshot(self, device: DeviceHandle) -> bytes:
        raise NotImplementedError

    def upload_file(self, device: DeviceHandle, local_path: str, remote_path: str) -> str:
        raise NotImplementedError
```
- Later tasks will fill implementations using the chosen low-level mechanism.

**Test Strategy:**

- Unit test that the interface exists and that stub methods raise `NotImplementedError`.
- Create a fake/mock implementation `MockGeelarkDeviceController` for testing higher-level logic without real devices.
- Verify that `account_name` to `device_id` mapping works as expected using the MVP single-device configuration.
