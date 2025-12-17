# Task ID: 29

**Title:** Add HTTP timeout to GeelarkClient._request()

**Status:** done

**Dependencies:** 25 ✓

**Priority:** medium

**Description:** Add a configurable timeout parameter to all HTTP requests in geelark_client.py to prevent indefinite hangs on network issues, ensuring posting operations fail fast and can be retried rather than blocking workers indefinitely.

**Details:**

## Problem Statement

The `GeelarkClient._request()` method at line 49 of `geelark_client.py` uses `requests.post()` without a timeout parameter:
```python
resp = requests.post(url, json=data or {}, headers=headers)
```

Similarly, `upload_file_to_geelark()` at line 161 uses `requests.put()` without a timeout:
```python
resp = requests.put(upload_url, data=f)
```

Without timeouts, these calls can hang indefinitely on network issues, causing workers to become stuck and reducing system throughput.

## Implementation Steps

### 1. Add HTTP_TIMEOUT constant to config.py

Add to the TIMEOUTS section (around line 106-118):
```python
# HTTP request timeout for Geelark API calls (seconds)
HTTP_API_TIMEOUT: int = 30

# HTTP timeout for file uploads (larger files need more time)
HTTP_UPLOAD_TIMEOUT: int = 120
```

### 2. Update GeelarkClient._request() to use timeout

In `geelark_client.py`, import Config and add timeout to the POST request:

```python
from config import Config

# In _request() method (line 49):
resp = requests.post(url, json=data or {}, headers=headers, timeout=Config.HTTP_API_TIMEOUT)
```

### 3. Update upload_file_to_geelark() to use timeout

```python
# In upload_file_to_geelark() method (line 161):
resp = requests.put(upload_url, data=f, timeout=Config.HTTP_UPLOAD_TIMEOUT)
```

### 4. Add proper exception handling for timeout errors

Wrap the requests calls in try-except to handle `requests.exceptions.Timeout` and `requests.exceptions.ConnectionError`:

```python
def _request(self, endpoint, data=None):
    """Make API request with full response logging"""
    url = f"{API_BASE}{endpoint}"
    headers = self._get_headers()
    
    start_time = time.time()
    api_logger.debug(f"REQUEST: {endpoint} data={data}")
    
    try:
        resp = requests.post(
            url, 
            json=data or {}, 
            headers=headers, 
            timeout=Config.HTTP_API_TIMEOUT
        )
    except requests.exceptions.Timeout:
        api_logger.error(f"TIMEOUT: {endpoint} after {Config.HTTP_API_TIMEOUT}s")
        raise Exception(f"API timeout: {endpoint} did not respond within {Config.HTTP_API_TIMEOUT}s")
    except requests.exceptions.ConnectionError as e:
        api_logger.error(f"CONNECTION ERROR: {endpoint} - {e}")
        raise Exception(f"API connection error: {endpoint} - {e}")
    
    elapsed = time.time() - start_time
    # ... rest of method unchanged
```

### 5. Similar handling for upload_file_to_geelark()

```python
def upload_file_to_geelark(self, local_path):
    """Upload a local file to Geelark's temp storage, return resource URL"""
    # ... existing code to get upload_url and resource_url ...
    
    try:
        with open(local_path, "rb") as f:
            resp = requests.put(upload_url, data=f, timeout=Config.HTTP_UPLOAD_TIMEOUT)
    except requests.exceptions.Timeout:
        raise Exception(f"Upload timeout: file upload did not complete within {Config.HTTP_UPLOAD_TIMEOUT}s")
    except requests.exceptions.ConnectionError as e:
        raise Exception(f"Upload connection error: {e}")
    
    # ... rest of method unchanged
```

## Rationale for Timeout Values

- **HTTP_API_TIMEOUT = 30s**: Most Geelark API calls are simple JSON exchanges. 30 seconds is generous for normal operations while preventing indefinite hangs.
- **HTTP_UPLOAD_TIMEOUT = 120s**: File uploads (videos) can be several MB, requiring more time. 120 seconds accommodates larger files over slower connections.

## Files to Modify

1. `config.py` - Add HTTP_API_TIMEOUT and HTTP_UPLOAD_TIMEOUT constants
2. `geelark_client.py` - Add timeout parameter and exception handling to _request() and upload_file_to_geelark()

**Test Strategy:**

## Test Strategy

### 1. Unit Test - Verify timeout parameter is passed

```bash
# Quick verification that requests.post is called with timeout
python -c "
import geelark_client
import requests
from unittest.mock import patch, MagicMock

# Mock successful response
mock_resp = MagicMock()
mock_resp.status_code = 200
mock_resp.json.return_value = {'code': 0, 'data': {'items': []}}
mock_resp.text = '{}'
mock_resp.headers = {}

with patch.object(requests, 'post', return_value=mock_resp) as mock_post:
    client = geelark_client.GeelarkClient()
    client._request('/test/endpoint', {'test': 'data'})
    
    # Verify timeout was passed
    call_kwargs = mock_post.call_args.kwargs
    assert 'timeout' in call_kwargs, 'timeout parameter not passed to requests.post'
    assert call_kwargs['timeout'] == 30, f'Expected timeout=30, got {call_kwargs[\"timeout\"]}'
    print('✓ requests.post called with timeout=30')
"
```

### 2. Unit Test - Verify timeout exception handling

```bash
python -c "
import geelark_client
import requests
from unittest.mock import patch

# Test Timeout exception is caught and re-raised with descriptive message
with patch.object(requests, 'post', side_effect=requests.exceptions.Timeout()):
    client = geelark_client.GeelarkClient()
    try:
        client._request('/test/endpoint', {})
        print('✗ Expected exception was not raised')
    except Exception as e:
        assert 'timeout' in str(e).lower(), f'Exception message should mention timeout: {e}'
        print(f'✓ Timeout properly caught and re-raised: {e}')
"
```

### 3. Unit Test - Verify connection error handling

```bash
python -c "
import geelark_client
import requests
from unittest.mock import patch

# Test ConnectionError exception is caught and re-raised
with patch.object(requests, 'post', side_effect=requests.exceptions.ConnectionError('Network unreachable')):
    client = geelark_client.GeelarkClient()
    try:
        client._request('/test/endpoint', {})
        print('✗ Expected exception was not raised')
    except Exception as e:
        assert 'connection' in str(e).lower(), f'Exception message should mention connection: {e}'
        print(f'✓ ConnectionError properly caught and re-raised: {e}')
"
```

### 4. Verify config.py has timeout constants

```bash
python -c "
from config import Config
assert hasattr(Config, 'HTTP_API_TIMEOUT'), 'Missing HTTP_API_TIMEOUT'
assert hasattr(Config, 'HTTP_UPLOAD_TIMEOUT'), 'Missing HTTP_UPLOAD_TIMEOUT'
assert Config.HTTP_API_TIMEOUT == 30, f'Expected HTTP_API_TIMEOUT=30, got {Config.HTTP_API_TIMEOUT}'
assert Config.HTTP_UPLOAD_TIMEOUT == 120, f'Expected HTTP_UPLOAD_TIMEOUT=120, got {Config.HTTP_UPLOAD_TIMEOUT}'
print(f'✓ Config.HTTP_API_TIMEOUT = {Config.HTTP_API_TIMEOUT}')
print(f'✓ Config.HTTP_UPLOAD_TIMEOUT = {Config.HTTP_UPLOAD_TIMEOUT}')
"
```

### 5. Integration Test - Live API call with timeout

```bash
# Test that actual API calls work with the timeout
python -c "
from geelark_client import GeelarkClient
client = GeelarkClient()
try:
    result = client.list_phones(page_size=1)
    print(f'✓ API call succeeded with timeout: {len(result.get(\"items\", []))} phones')
except Exception as e:
    if 'timeout' in str(e).lower():
        print(f'⚠ API timed out (may indicate slow network): {e}')
    else:
        print(f'✗ API call failed: {e}')
"
```

### 6. Verify upload timeout on upload_file_to_geelark()

```bash
python -c "
import geelark_client
import requests
from unittest.mock import patch, MagicMock

# Mock get_upload_url response
mock_get_url = MagicMock()
mock_get_url.return_value = {'uploadUrl': 'https://test.com/upload', 'resourceUrl': 'https://test.com/resource'}

# Mock successful PUT response
mock_resp = MagicMock()
mock_resp.status_code = 200

with patch.object(requests, 'put', return_value=mock_resp) as mock_put:
    with patch.object(geelark_client.GeelarkClient, 'get_upload_url', mock_get_url):
        client = geelark_client.GeelarkClient()
        # Create a small temp file for testing
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            f.write(b'test data')
            temp_path = f.name
        
        try:
            client.upload_file_to_geelark(temp_path)
            call_kwargs = mock_put.call_args.kwargs
            assert 'timeout' in call_kwargs, 'timeout parameter not passed to requests.put'
            assert call_kwargs['timeout'] == 120, f'Expected timeout=120, got {call_kwargs[\"timeout\"]}'
            print('✓ requests.put called with timeout=120')
        finally:
            import os
            os.unlink(temp_path)
"
```
