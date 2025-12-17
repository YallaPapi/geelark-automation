# Task ID: 30

**Title:** Add credential validation to GeelarkClient.__init__()

**Status:** done

**Dependencies:** 25 ✓

**Priority:** medium

**Description:** Add fail-fast validation to GeelarkClient.__init__() that checks for required GEELARK_TOKEN at initialization time and raises a clear, actionable error immediately if missing, rather than failing later in the posting flow with cryptic authentication errors.

**Details:**

## Problem Statement

Currently, `GeelarkClient.__init__()` (lines 26-29 of `geelark_client.py`) simply assigns environment variables without validation:
```python
def __init__(self):
    self.app_id = os.getenv("GEELARK_APP_ID")
    self.api_key = os.getenv("GEELARK_API_KEY")
    self.token = os.getenv("GEELARK_TOKEN")
```

When `GEELARK_TOKEN` is missing, the first API call fails deep in the posting flow at `_get_headers()` (line 37) with `Authorization: Bearer None`, resulting in a confusing HTTP 401 error that doesn't clearly indicate the root cause.

## Implementation Requirements

### 1. Add credential validation in `__init__()`

```python
def __init__(self):
    self.app_id = os.getenv("GEELARK_APP_ID")
    self.api_key = os.getenv("GEELARK_API_KEY")
    self.token = os.getenv("GEELARK_TOKEN")
    
    # Fail-fast validation
    self._validate_credentials()

def _validate_credentials(self):
    """Validate required credentials are present. Raises ValueError if missing."""
    missing = []
    
    if not self.token:
        missing.append("GEELARK_TOKEN")
    
    # Optional: validate legacy credentials if used
    # if not self.app_id:
    #     missing.append("GEELARK_APP_ID")
    # if not self.api_key:
    #     missing.append("GEELARK_API_KEY")
    
    if missing:
        raise ValueError(
            f"Missing required Geelark credentials: {', '.join(missing)}. "
            f"Set these in your .env file or environment variables."
        )
```

### 2. Error message requirements

The error message should:
- Clearly state which credentials are missing
- Mention `.env` file as the expected location
- Be actionable (tell user what to do)

### 3. Follow existing patterns

The implementation mirrors the `_validate_config()` pattern in `config.py` (lines 174-185) which validates paths at import time. However, use `ValueError` instead of print warnings since missing credentials make the client non-functional.

### 4. Backward compatibility considerations

- The `app_id` and `api_key` are legacy credentials that may still be used in some code paths
- Focus validation on `GEELARK_TOKEN` which is the primary auth mechanism (used in `_get_headers()`)
- Consider making `app_id`/`api_key` validation optional or behind a flag

### 5. Update import error handling in consuming modules

Modules like `parallel_worker.py` (line 220), `parallel_orchestrator.py` (lines 379, 812), and `post_reel_smart.py` (line 43) instantiate `GeelarkClient()`. These should catch the `ValueError` if graceful startup failure is needed, though the default behavior of letting it propagate is often correct for fail-fast.

**Test Strategy:**

## Test Strategy

### 1. Manual validation - missing token
```bash
# Temporarily rename .env to test missing credentials
mv .env .env.backup

# Attempt to instantiate client
python -c "from geelark_client import GeelarkClient; c = GeelarkClient()"

# Expected: ValueError with message about missing GEELARK_TOKEN
# Restore .env
mv .env.backup .env
```

### 2. Manual validation - valid credentials
```bash
# With valid .env in place
python -c "from geelark_client import GeelarkClient; c = GeelarkClient(); print('OK')"

# Expected: prints 'OK' without error
```

### 3. Integration test - orchestrator startup
```bash
# Test that orchestrator fails fast with clear error
mv .env .env.backup
python parallel_orchestrator.py --status 2>&1 | grep -i "GEELARK_TOKEN"

# Expected: Error message mentions GEELARK_TOKEN
mv .env.backup .env
```

### 4. Verify error message clarity
```bash
# Create .env without GEELARK_TOKEN
echo "ANTHROPIC_API_KEY=test" > .env.test
env -i python -c "
import os
os.chdir('.')
# Load empty env
from geelark_client import GeelarkClient
try:
    c = GeelarkClient()
except ValueError as e:
    print(f'Good: {e}')
    assert 'GEELARK_TOKEN' in str(e)
    assert '.env' in str(e)
"
rm .env.test
```

### 5. Verify existing functionality still works
```bash
# Run the client's __main__ test (lists phones)
python geelark_client.py

# Expected: Should list phones if credentials valid, or clear error if not
```
