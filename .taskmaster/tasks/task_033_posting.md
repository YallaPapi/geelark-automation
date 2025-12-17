# Task ID: 33

**Title:** Add JSON error handling to vision.py analyze functions

**Status:** done

**Dependencies:** 6 ✓

**Priority:** high

**Description:** Add try/except JSONDecodeError handling to analyze_screen() and analyze_for_instagram_post() functions in vision.py to prevent crashes when Claude returns malformed JSON responses, using the same error handling pattern already established in post_reel_smart.py.

**Details:**

## Problem Statement

The `vision.py` module has two functions that call `json.loads()` without error handling:
- `analyze_screen()` at line 90: `return json.loads(text)`
- `analyze_for_instagram_post()` at line 174: `return json.loads(text)`

When Claude returns malformed JSON (due to truncation, formatting issues, or model errors), these calls raise `json.JSONDecodeError` and crash without graceful error handling.

## Implementation Pattern

Follow the existing error handling pattern from `post_reel_smart.py` (lines 646-655):

```python
try:
    return json.loads(text)
except json.JSONDecodeError as e:
    # Log full raw response for debugging JSON issues
    print(f"  [JSON PARSE ERROR] attempt {attempt+1}: {e}")
    print(f"  Raw response (full): {text}")
    if attempt < 2:
        time.sleep(1)
        continue
    raise ValueError(f"JSON parse failed after 3 attempts: {e}. Response: {text[:100]}")
```

## Changes Required

### 1. Update imports at top of vision.py (line 6-7)

Add `json` to explicit imports (currently imported inline at lines 80, 165) and add `time` for retry delays:

```python
import anthropic
import base64
import json
import os
import time
```

### 2. Refactor analyze_screen() (lines 57-90)

Wrap the Claude API call and JSON parsing in a retry loop with proper error handling:

```python
# Replace lines 57-90 with:
for attempt in range(3):
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }]
        )

        # Check for empty response
        if not response.content:
            if attempt < 2:
                time.sleep(1)
                continue
            return {"action": "error", "message": "Claude returned empty response after 3 attempts"}

        text = response.content[0].text.strip()

        # Check for empty text
        if not text:
            if attempt < 2:
                time.sleep(1)
                continue
            return {"action": "error", "message": "Claude returned empty text after 3 attempts"}

        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"  [JSON PARSE ERROR in analyze_screen] attempt {attempt+1}: {e}")
            print(f"  Raw response: {text}")
            if attempt < 2:
                time.sleep(1)
                continue
            return {"action": "error", "message": f"JSON parse failed: {e}. Response: {text[:200]}"}

    except anthropic.APIError as e:
        print(f"  [API ERROR in analyze_screen] attempt {attempt+1}: {e}")
        if attempt < 2:
            time.sleep(1)
            continue
        return {"action": "error", "message": f"Claude API error after 3 attempts: {e}"}

return {"action": "error", "message": "Failed to get valid response from Claude after 3 attempts"}
```

### 3. Refactor analyze_for_instagram_post() (lines 143-174)

Apply the same retry and error handling pattern:

```python
# Replace lines 143-174 with similar retry loop structure
# Return dict with action="error" and message field on failure
# Include video_selected=False in error response for API consistency
```

### 4. Error Return Format

Both functions should return a consistent error structure that calling code can handle:

```python
# analyze_screen error return:
{"action": "error", "message": "descriptive error message"}

# analyze_for_instagram_post error return:
{"action": "error", "message": "descriptive error message", "video_selected": False}
```

### 5. Remove inline imports

Remove the inline `import json` statements at lines 80 and 165 since json will be imported at module level.

## Key Considerations

1. **Graceful degradation**: Return error dict instead of raising exceptions, allowing callers to handle gracefully
2. **Debugging support**: Log raw responses on parse failure for troubleshooting
3. **Retry logic**: 3 attempts with 1-second delays matches existing pattern
4. **API error handling**: Also catch anthropic.APIError for network/rate limit issues
5. **Consistent API**: Error responses include all expected fields to prevent KeyError in callers

**Test Strategy:**

## Test Strategy

### 1. Unit Test - Malformed JSON Handling

```bash
# Create test script to verify error handling
python -c "
import json
from unittest.mock import patch, MagicMock

# Mock anthropic client to return malformed JSON
mock_response = MagicMock()
mock_response.content = [MagicMock(text='not valid json {{{')]

with patch('anthropic.Anthropic') as mock_client:
    mock_client.return_value.messages.create.return_value = mock_response
    
    from vision import analyze_screen
    result = analyze_screen('test.png', 'test context')
    
    # Should return error dict, not raise exception
    assert result['action'] == 'error', f'Expected error action, got: {result}'
    assert 'message' in result, 'Error response missing message field'
    print(f'SUCCESS: Malformed JSON handled gracefully')
    print(f'Result: {result}')
"
```

### 2. Unit Test - Empty Response Handling

```bash
python -c "
from unittest.mock import patch, MagicMock

# Mock empty response
mock_response = MagicMock()
mock_response.content = []

with patch('anthropic.Anthropic') as mock_client:
    mock_client.return_value.messages.create.return_value = mock_response
    
    from vision import analyze_screen
    result = analyze_screen('test.png', 'test context')
    
    assert result['action'] == 'error', f'Expected error action, got: {result}'
    print('SUCCESS: Empty response handled gracefully')
"
```

### 3. Unit Test - analyze_for_instagram_post Error Fields

```bash
python -c "
from unittest.mock import patch, MagicMock

mock_response = MagicMock()
mock_response.content = [MagicMock(text='invalid')]

with patch('anthropic.Anthropic') as mock_client:
    mock_client.return_value.messages.create.return_value = mock_response
    
    from vision import analyze_for_instagram_post
    result = analyze_for_instagram_post('test.png', 'caption')
    
    assert result['action'] == 'error', f'Expected error action'
    assert 'video_selected' in result, 'Missing video_selected field in error response'
    print('SUCCESS: analyze_for_instagram_post error includes video_selected field')
"
```

### 4. Integration Test - Valid JSON Still Works

```bash
python -c "
from unittest.mock import patch, MagicMock
import json

# Mock valid JSON response
valid_response = {'action': 'tap', 'x': 100, 'y': 200, 'message': 'Tap button'}
mock_response = MagicMock()
mock_response.content = [MagicMock(text=json.dumps(valid_response))]

with patch('anthropic.Anthropic') as mock_client:
    mock_client.return_value.messages.create.return_value = mock_response
    
    from vision import analyze_screen
    result = analyze_screen('test.png', 'test context')
    
    assert result == valid_response, f'Expected {valid_response}, got {result}'
    print('SUCCESS: Valid JSON parsing still works correctly')
"
```

### 5. Manual Verification - Code Review

```bash
# Verify imports are at module level
head -10 vision.py | grep -E "^import json|^import time"

# Verify no inline imports remain
grep -n "import json" vision.py  # Should only show line ~6

# Verify try/except exists for json.loads
grep -A2 "json.loads" vision.py | grep -c "except"  # Should be 2
```

### 6. Test Retry Behavior

```bash
python -c "
from unittest.mock import patch, MagicMock, call
import json

# Track call count
call_count = 0

def failing_create(*args, **kwargs):
    global call_count
    call_count += 1
    mock = MagicMock()
    mock.content = [MagicMock(text='invalid json')]
    return mock

with patch('anthropic.Anthropic') as mock_client:
    mock_client.return_value.messages.create.side_effect = failing_create
    
    from vision import analyze_screen
    result = analyze_screen('test.png', 'test')
    
    # Should have retried 3 times
    assert call_count == 3, f'Expected 3 attempts, got {call_count}'
    print(f'SUCCESS: Retry logic executed {call_count} attempts')
"
```
