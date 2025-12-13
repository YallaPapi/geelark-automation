# API Reference

## GeelarkClient

The `GeelarkClient` class provides a Python interface to the Geelark Cloud Phone API.

### Initialization

```python
from geelark_client import GeelarkClient, GeelarkCredentialError

# Uses GEELARK_TOKEN from environment
client = GeelarkClient()

# Or pass token directly
client = GeelarkClient(token="your_token_here")
```

**Environment Variables:**
- `GEELARK_TOKEN` (required) - API bearer token

**Raises:**
- `GeelarkCredentialError` - If GEELARK_TOKEN is missing

---

## Phone Management

### list_phones

List all cloud phones in your account.

```python
result = client.list_phones(page=1, page_size=100, group_name=None)
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 100 | Items per page (max 100) |
| `group_name` | str | None | Filter by group name |

**Returns:** `dict`
```python
{
    "total": 82,
    "items": [
        {
            "id": "phone_id_123",
            "serialName": "myphone1",
            "status": 0,  # 0=running, 1=stopped
            "groupName": "default"
        },
        ...
    ]
}
```

---

### get_phone_status

Get status of specific phones.

```python
result = client.get_phone_status(["phone_id_1", "phone_id_2"])
```

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `phone_ids` | list[str] | List of phone IDs |

**Returns:** `dict`
```python
{
    "successDetails": [
        {"id": "phone_id_1", "status": 0}
    ]
}
```

---

### start_phone

Start a cloud phone.

```python
result = client.start_phone("phone_id_123")
```

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `phone_id` | str | Phone ID to start |

**Returns:** `dict` - Success details

**Raises:** `Exception` if phone fails to start

---

### stop_phone

Stop a cloud phone (saves billing minutes).

```python
client.stop_phone("phone_id_123")
```

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `phone_id` | str | Phone ID to stop |

---

## ADB Management

### enable_adb / disable_adb

Enable or disable ADB access on a phone.

```python
client.enable_adb("phone_id_123")
client.disable_adb("phone_id_123")
```

---

### get_adb_info

Get ADB connection details (IP, port, password).

```python
info = client.get_adb_info("phone_id_123")
```

**Returns:** `dict`
```python
{
    "ip": "123.45.67.89",
    "port": 5555,
    "pwd": "abc123",  # Password for glogin
    "code": 0
}
```

**Usage:**
```bash
adb connect 123.45.67.89:5555
adb -s 123.45.67.89:5555 shell glogin abc123
```

---

## File Upload

### upload_file_to_geelark

Upload a local file to Geelark's temporary storage.

```python
resource_url = client.upload_file_to_geelark("/path/to/video.mp4")
```

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `local_path` | str | Path to local file |

**Returns:** `str` - Resource URL for the uploaded file

---

### upload_file_to_phone

Upload a file from URL to the phone's Downloads folder.

```python
result = client.upload_file_to_phone("phone_id_123", resource_url)
task_id = result["taskId"]
```

**Returns:** `dict` with `taskId` for tracking

---

### wait_for_upload

Wait for file upload to phone to complete.

```python
success = client.wait_for_upload(task_id, timeout=60, verbose=True)
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `task_id` | str | - | Upload task ID |
| `timeout` | int | 60 | Max seconds to wait |
| `verbose` | bool | True | Print progress |

**Returns:** `bool` - True on success

**Raises:** `Exception` on failure or timeout

---

## Screenshots

### wait_for_screenshot

Take a screenshot and wait for the download URL.

```python
download_url = client.wait_for_screenshot("phone_id_123", timeout=30)
```

**Returns:** `str` - URL to download the screenshot

---

## Device Management

### one_click_new_device

Reset phone to fresh state (wipes all data).

```python
client.one_click_new_device("phone_id_123", change_brand_model=False)
```

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `phone_id` | str | - | Phone ID |
| `change_brand_model` | bool | False | Randomize device fingerprint |

**Warning:** This completely resets the phone - all apps and data will be lost!

---

### set_root_status

Enable or disable root access.

```python
client.set_root_status("phone_id_123", enable=True)
```

---

## HTTP Configuration

The client uses connection pooling and automatic retries:

```python
# Default timeout
DEFAULT_HTTP_TIMEOUT = 30  # seconds

# Retry configuration
max_retries = 3
backoff_factor = 0.5
status_forcelist = [500, 502, 503, 504]
```

All API responses are logged to `geelark_api.log` for debugging.

---

## Error Handling

```python
from geelark_client import GeelarkClient, GeelarkCredentialError

try:
    client = GeelarkClient()
    client.start_phone("invalid_id")
except GeelarkCredentialError as e:
    print(f"Missing credentials: {e}")
except Exception as e:
    print(f"API error: {e}")
```

Common errors:
- `GeelarkCredentialError` - Missing GEELARK_TOKEN
- `Exception: API error: 401` - Invalid token
- `Exception: Failed to start phone` - Phone unavailable
