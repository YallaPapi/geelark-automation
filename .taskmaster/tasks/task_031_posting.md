# Task ID: 31

**Title:** Add HTTP connection pooling to GeelarkClient

**Status:** done

**Dependencies:** 25 ✓, 29 ✓, 30 ✓

**Priority:** medium

**Description:** Create a requests.Session() with HTTPAdapter connection pooling in GeelarkClient.__init__() and migrate all HTTP calls from requests.post()/requests.put() to self.session.post()/self.session.put() to prevent connection exhaustion under parallel worker load.

**Details:**

## Problem Statement

The current `GeelarkClient` (geelark_client.py lines 40-68) creates a new HTTP connection for every API call via `requests.post()` and `requests.put()`. Under parallel worker load (5+ workers making concurrent API calls), this can lead to:
- Connection exhaustion (too many simultaneous connections)
- TCP TIME_WAIT accumulation
- Increased latency (no connection reuse)
- Resource leaks under high load

## Current Implementation Analysis

**geelark_client.py line 49:**
```python
resp = requests.post(url, json=data or {}, headers=headers)
```

**geelark_client.py line 161:**
```python
resp = requests.put(upload_url, data=f)
```

Each `GeelarkClient()` instance (created in parallel_worker.py:220, parallel_orchestrator.py:379, post_reel_smart.py:43, etc.) opens fresh connections per request.

## Implementation Steps

### 1. Add requests.Session with HTTPAdapter in __init__()

```python
# geelark_client.py - imports (add at top)
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# In __init__() after line 29:
def __init__(self):
    self.app_id = os.getenv("GEELARK_APP_ID")
    self.api_key = os.getenv("GEELARK_API_KEY")
    self.token = os.getenv("GEELARK_TOKEN")
    
    # Create session with connection pooling
    self.session = requests.Session()
    
    # Configure HTTPAdapter with connection pooling
    adapter = HTTPAdapter(
        pool_connections=10,  # Number of connection pools to cache
        pool_maxsize=10,      # Max connections per pool
        max_retries=Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[502, 503, 504]
        )
    )
    self.session.mount('http://', adapter)
    self.session.mount('https://', adapter)
```

### 2. Update _request() to use self.session.post()

```python
# geelark_client.py line 49 - change:
# FROM:
resp = requests.post(url, json=data or {}, headers=headers)
# TO:
resp = self.session.post(url, json=data or {}, headers=headers)
```

### 3. Update upload_file_to_geelark() to use self.session.put()

```python
# geelark_client.py line 161 - change:
# FROM:
resp = requests.put(upload_url, data=f)
# TO:
resp = self.session.put(upload_url, data=f)
```

### 4. Add optional close() method for cleanup

```python
def close(self):
    """Close the session and release connections."""
    if hasattr(self, 'session') and self.session:
        self.session.close()

def __enter__(self):
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    self.close()
```

## Configuration Recommendations

The `pool_connections=10` and `pool_maxsize=10` values are appropriate because:
- `Config.MAX_WORKERS` is 10 (config.py line 57)
- Geelark API is a single host (API_BASE = "https://openapi.geelark.com")
- Each worker may have 1-2 concurrent requests at most

## Integration with Existing Tasks

This task complements:
- **Task 29**: HTTP timeout parameter (can be added to session.post/put calls)
- **Task 30**: Credential validation (should run before session creation)

## Edge Cases to Handle

1. **Session reuse across methods**: All methods inherit the pooled session
2. **File uploads**: Large file PUT requests should still benefit from pooling
3. **Concurrent access**: requests.Session is thread-safe for most operations
4. **Error recovery**: Built-in retry via Retry adapter handles transient failures

**Test Strategy:**

## Test Strategy

### 1. Unit Test - Session Creation
```bash
python -c "
from geelark_client import GeelarkClient
client = GeelarkClient()

# Verify session exists
assert hasattr(client, 'session'), 'Session not created'
assert client.session is not None, 'Session is None'

# Verify adapters mounted
adapters = client.session.adapters
assert 'https://' in adapters, 'HTTPS adapter not mounted'
assert 'http://' in adapters, 'HTTP adapter not mounted'

print('Session creation: PASS')
"
```

### 2. Unit Test - Connection Pooling Configuration
```bash
python -c "
from geelark_client import GeelarkClient
from requests.adapters import HTTPAdapter

client = GeelarkClient()
adapter = client.session.get_adapter('https://')

# Verify it's an HTTPAdapter (not default)
assert isinstance(adapter, HTTPAdapter), f'Wrong adapter type: {type(adapter)}'

# Verify pool settings (introspect the adapter)
config = adapter.config
assert config.get('pool_connections', 0) >= 10, 'pool_connections too low'
assert config.get('pool_maxsize', 0) >= 10, 'pool_maxsize too low'

print('Connection pooling config: PASS')
"
```

### 3. Functional Test - API Calls Use Session
```bash
python -c "
from geelark_client import GeelarkClient
from unittest.mock import patch, MagicMock

client = GeelarkClient()

# Mock the session.post method
with patch.object(client.session, 'post') as mock_post:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'code': 0, 'data': {'items': [], 'total': 0}}
    mock_response.text = '{}'
    mock_response.headers = {}
    mock_post.return_value = mock_response
    
    # Call list_phones which uses _request()
    client.list_phones(page_size=1)
    
    # Verify session.post was called (not requests.post)
    assert mock_post.called, 'session.post was not called'
    print('API calls use session: PASS')
"
```

### 4. Live Test - Parallel Workers
```bash
# Start orchestrator with 5 workers briefly
python parallel_orchestrator.py --workers 5 --status

# Check geelark_api.log for connection patterns
# Should NOT see TCP connection errors or exhaustion warnings
tail -20 geelark_api.log
```

### 5. Load Test - Multiple Concurrent Clients
```bash
python -c "
import threading
import time
from geelark_client import GeelarkClient

results = []
errors = []

def make_requests(client_id):
    try:
        client = GeelarkClient()
        # Make 5 requests in quick succession
        for i in range(5):
            result = client.list_phones(page_size=1)
            results.append((client_id, i, 'success'))
            time.sleep(0.1)
    except Exception as e:
        errors.append((client_id, str(e)))

# Spawn 5 threads (simulating 5 workers)
threads = []
for i in range(5):
    t = threading.Thread(target=make_requests, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

print(f'Successful requests: {len(results)}')
print(f'Errors: {len(errors)}')
if errors:
    for e in errors:
        print(f'  Client {e[0]}: {e[1]}')
else:
    print('All concurrent requests succeeded: PASS')
"
```

### 6. Context Manager Test
```bash
python -c "
from geelark_client import GeelarkClient

# Test context manager usage
with GeelarkClient() as client:
    result = client.list_phones(page_size=1)
    print(f'Got {result.get(\"total\", 0)} phones')

# Session should be closed after exiting context
print('Context manager: PASS')
"
```
