# Task ID: 4

**Title:** Implement low-level Geelark control (screenshots, taps, typing, file transfer)

**Status:** done

**Dependencies:** 3 ✓

**Priority:** high

**Description:** Provide a concrete implementation of the Geelark device control abstraction using the chosen RPA/ADB/API mechanism.

**Details:**

Implementation details:
- Decide a concrete mechanism based on what Geelark exposes:
  - If Geelark offers an HTTP API: implement calls like `POST /devices/{id}/tap`, `POST /devices/{id}/type`, `GET /devices/{id}/screenshot`, etc.
  - If using ADB: use `subprocess` to call `adb -s <serial> shell input tap x y`, `input text`, `screencap -p`, and `adb push` for file transfer.
- Implement `GeelarkDeviceController` methods:
  - `connect`: resolve `account_name` to a device identifier (e.g. `device_serial`), possibly via config mapping; validate connectivity.
  - `launch_app`: `adb shell monkey -p com.instagram.android 1` or equivalent API.
  - `tap`: execute appropriate tap command.
  - `type_text`: escape special characters for ADB; for longer captions, implement paste via clipboard if device API supports it.
  - `screenshot`: capture and return raw bytes; ensure correct image format for Claude Vision.
  - `upload_file`: transfer video from host to device; return the device-side file path.
- Add minimal rate limiting to avoid overwhelming Geelark/API.
- Pseudo-code example (ADB-style):
```python
import subprocess, io

class AdbGeelarkDeviceController(GeelarkDeviceController):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def connect(self, account_name: str) -> DeviceHandle:
        serial = self.mapping.get(account_name) or next(iter(self.mapping.values()))
        return DeviceHandle(serial)

    def tap(self, device: DeviceHandle, x: int, y: int):
        subprocess.run(["adb", "-s", device.id, "shell", "input", "tap", str(x), str(y)], check=True)

    def screenshot(self, device: DeviceHandle) -> bytes:
        out = subprocess.check_output(["adb", "-s", device.id, "exec-out", "screencap", "-p"])
        return out

    def upload_file(self, device: DeviceHandle, local_path: str, remote_path: str) -> str:
        subprocess.run(["adb", "-s", device.id, "push", local_path, remote_path], check=True)
        return remote_path
```

**Test Strategy:**

- If using ADB: run integration tests against a test device or emulator.
  - Verify `connect` returns a valid handle.
  - Call `screenshot` and confirm returned bytes decode as an image.
  - Call `tap` and `type_text` while observing the device screen.
  - Transfer a small dummy video file and confirm existence on the device.
- If using HTTP API: use a mock server to validate request payloads, paths, and error handling.
- Add negative tests: simulate command/API failures and verify that exceptions are raised and propagated up.
