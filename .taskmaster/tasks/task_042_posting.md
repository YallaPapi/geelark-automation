# Task ID: 42

**Title:** Extract _detect_and_recover_from_loop helper from post() method

**Status:** done

**Dependencies:** 39 ✓, 40 ✓, 41 ✓

**Priority:** medium

**Description:** Extract the loop detection and recovery logic (lines 769-804) from the post() method into a dedicated _detect_and_recover_from_loop() helper method to improve readability and reduce the complexity of the main posting loop.

**Details:**

## Current State Analysis

The `post()` method in `post_reel_smart.py` contains inline loop detection and recovery logic at lines 769-804:

### Current Structure (lines 614-618, 769-804):

**Initialization (lines 614-618):**
```python
# Loop detection - track recent actions to detect stuck states
recent_actions = []  # List of (action_type, x, y) tuples
LOOP_THRESHOLD = 5  # If 5 consecutive same actions, we're stuck
loop_recovery_count = 0  # How many times we've tried to recover
MAX_LOOP_RECOVERIES = 2  # Give up after this many recovery attempts
```

**Action tracking (lines 769-778):**
```python
# Track action for loop detection
action_signature = action['action']
if action['action'] == 'tap' and 'element_index' in action:
    idx = action.get('element_index', 0)
    if 0 <= idx < len(elements):
        x, y = elements[idx]['center']
        action_signature = f"tap_{x}_{y}"
recent_actions.append(action_signature)
if len(recent_actions) > LOOP_THRESHOLD:
    recent_actions.pop(0)
```

**Loop detection and recovery (lines 780-804):**
```python
# Check for loop - if last N actions are all identical, we're stuck
if len(recent_actions) >= LOOP_THRESHOLD and len(set(recent_actions)) == 1:
    loop_recovery_count += 1
    print(f"\n  [LOOP DETECTED] Same action '{recent_actions[0]}' repeated {LOOP_THRESHOLD} times!")
    print(f"  [RECOVERY] Attempt {loop_recovery_count}/{MAX_LOOP_RECOVERIES}")

    if loop_recovery_count > MAX_LOOP_RECOVERIES:
        print("  [ABORT] Too many loop recoveries, giving up")
        return False

    # Recovery: press back 5 times and restart Instagram
    print("  Pressing BACK 5 times to escape stuck state...")
    for _ in range(5):
        self.press_key('KEYCODE_BACK')
        time.sleep(0.5)

    print("  Reopening Instagram...")
    self.adb("am force-stop com.instagram.android")
    time.sleep(2)
    self.adb("monkey -p com.instagram.android 1")
    time.sleep(5)

    # Reset action tracking
    recent_actions = []
    print("  [RECOVERY] Restarted - continuing from step", step + 1)
```

## Implementation Plan

### Step 1: Define constants as class-level attributes (add after line 70)

```python
# Loop detection constants
LOOP_THRESHOLD = 5  # If N consecutive same actions, we're stuck
MAX_LOOP_RECOVERIES = 2  # Give up after this many recovery attempts
```

### Step 2: Create _build_action_signature() helper (add after cleanup() method, ~line 820)

```python
def _build_action_signature(self, action, elements):
    """Build a unique signature for an action to detect loops.
    
    Args:
        action: The action dict from Claude's analysis
        elements: List of UI elements
        
    Returns:
        str: Action signature for loop comparison
    """
    action_signature = action['action']
    if action['action'] == 'tap' and 'element_index' in action:
        idx = action.get('element_index', 0)
        if 0 <= idx < len(elements):
            x, y = elements[idx]['center']
            action_signature = f"tap_{x}_{y}"
    return action_signature
```

### Step 3: Create _detect_and_recover_from_loop() helper (add after _build_action_signature)

```python
def _detect_and_recover_from_loop(self, recent_actions, loop_recovery_count, step):
    """Detect if we're stuck in a loop and attempt recovery.
    
    Args:
        recent_actions: List of recent action signatures
        loop_recovery_count: Current number of recovery attempts
        step: Current step number (for logging)
        
    Returns:
        tuple: (should_abort: bool, new_recovery_count: int, reset_actions: bool)
            - should_abort: True if we should abort the entire post operation
            - new_recovery_count: Updated recovery count
            - reset_actions: True if recent_actions should be cleared
    """
    # Not enough actions to detect a loop yet
    if len(recent_actions) < self.LOOP_THRESHOLD:
        return (False, loop_recovery_count, False)
    
    # Check if all recent actions are identical (loop detected)
    if len(set(recent_actions)) != 1:
        return (False, loop_recovery_count, False)
    
    # Loop detected!
    loop_recovery_count += 1
    print(f"\n  [LOOP DETECTED] Same action '{recent_actions[0]}' repeated {self.LOOP_THRESHOLD} times!")
    print(f"  [RECOVERY] Attempt {loop_recovery_count}/{self.MAX_LOOP_RECOVERIES}")
    
    # Check if we've exceeded max recovery attempts
    if loop_recovery_count > self.MAX_LOOP_RECOVERIES:
        print("  [ABORT] Too many loop recoveries, giving up")
        return (True, loop_recovery_count, False)
    
    # Attempt recovery: press back 5 times and restart Instagram
    print("  Pressing BACK 5 times to escape stuck state...")
    for _ in range(5):
        self.press_key('KEYCODE_BACK')
        time.sleep(0.5)
    
    print("  Reopening Instagram...")
    self.adb("am force-stop com.instagram.android")
    time.sleep(2)
    self.adb("monkey -p com.instagram.android 1")
    time.sleep(5)
    
    print(f"  [RECOVERY] Restarted - continuing from step {step + 1}")
    return (False, loop_recovery_count, True)
```

### Step 4: Refactor post() method to use the helpers

Replace lines 614-618 (initialization):
```python
# Loop detection state
recent_actions = []
loop_recovery_count = 0
```

Replace lines 769-804 with:
```python
# Track action for loop detection
action_signature = self._build_action_signature(action, elements)
recent_actions.append(action_signature)
if len(recent_actions) > self.LOOP_THRESHOLD:
    recent_actions.pop(0)

# Check for loop and attempt recovery if needed
should_abort, loop_recovery_count, reset_actions = self._detect_and_recover_from_loop(
    recent_actions, loop_recovery_count, step
)
if should_abort:
    return False
if reset_actions:
    recent_actions = []
```

## Key Design Decisions

1. **Return tuple pattern**: The helper returns a tuple `(should_abort, new_recovery_count, reset_actions)` to communicate multiple outcomes without side effects on mutable arguments.

2. **Class-level constants**: Moving `LOOP_THRESHOLD` and `MAX_LOOP_RECOVERIES` to class attributes allows easy configuration and testing.

3. **Separate signature builder**: The `_build_action_signature()` helper is small but encapsulates the logic of creating comparable action signatures, improving testability.

4. **Preserve logging**: All print statements are preserved in the helper to maintain the same debug output.

5. **No behavior changes**: The extracted code must produce identical behavior to the current implementation.

## Files Modified

- `post_reel_smart.py`: Add class constants, add two helper methods, refactor post() loop detection section

**Test Strategy:**

## Test Strategy

### 1. Syntax and Import Verification
```bash
# Verify the file has no syntax errors and imports correctly
python -c "from post_reel_smart import SmartInstagramPoster; print('Import successful')"
```

### 2. Method Existence Verification
```bash
python -c "
from post_reel_smart import SmartInstagramPoster
poster = SmartInstagramPoster.__new__(SmartInstagramPoster)

# Verify new methods exist
assert hasattr(poster, '_build_action_signature'), 'Missing _build_action_signature'
assert hasattr(poster, '_detect_and_recover_from_loop'), 'Missing _detect_and_recover_from_loop'
assert callable(poster._build_action_signature), '_build_action_signature not callable'
assert callable(poster._detect_and_recover_from_loop), '_detect_and_recover_from_loop not callable'

# Verify class constants exist
assert hasattr(SmartInstagramPoster, 'LOOP_THRESHOLD'), 'Missing LOOP_THRESHOLD constant'
assert hasattr(SmartInstagramPoster, 'MAX_LOOP_RECOVERIES'), 'Missing MAX_LOOP_RECOVERIES constant'
assert SmartInstagramPoster.LOOP_THRESHOLD == 5, f'LOOP_THRESHOLD should be 5, got {SmartInstagramPoster.LOOP_THRESHOLD}'
assert SmartInstagramPoster.MAX_LOOP_RECOVERIES == 2, f'MAX_LOOP_RECOVERIES should be 2, got {SmartInstagramPoster.MAX_LOOP_RECOVERIES}'

print('Method and constant verification passed')
"
```

### 3. Unit Test - _build_action_signature()
```bash
python -c "
from post_reel_smart import SmartInstagramPoster
poster = SmartInstagramPoster.__new__(SmartInstagramPoster)

# Test basic action signature
action = {'action': 'scroll_down'}
elements = []
sig = poster._build_action_signature(action, elements)
assert sig == 'scroll_down', f'Expected scroll_down, got {sig}'

# Test tap action with element
action = {'action': 'tap', 'element_index': 0}
elements = [{'center': (100, 200)}]
sig = poster._build_action_signature(action, elements)
assert sig == 'tap_100_200', f'Expected tap_100_200, got {sig}'

# Test tap action with invalid index
action = {'action': 'tap', 'element_index': 99}
elements = [{'center': (100, 200)}]
sig = poster._build_action_signature(action, elements)
assert sig == 'tap', f'Expected tap (invalid index), got {sig}'

# Test tap action without element_index
action = {'action': 'tap'}
elements = [{'center': (100, 200)}]
sig = poster._build_action_signature(action, elements)
assert sig == 'tap', f'Expected tap (no index), got {sig}'

print('_build_action_signature tests passed')
"
```

### 4. Unit Test - _detect_and_recover_from_loop() (no loop case)
```bash
python -c "
from post_reel_smart import SmartInstagramPoster
from unittest.mock import MagicMock

poster = SmartInstagramPoster.__new__(SmartInstagramPoster)
poster.LOOP_THRESHOLD = 5
poster.MAX_LOOP_RECOVERIES = 2

# Test with fewer than threshold actions (no loop)
recent_actions = ['tap_100_200', 'tap_150_300', 'scroll_down']
should_abort, new_count, reset = poster._detect_and_recover_from_loop(recent_actions, 0, 5)
assert not should_abort, 'Should not abort with few actions'
assert new_count == 0, 'Recovery count should remain 0'
assert not reset, 'Should not reset actions'

# Test with different actions (no loop)
recent_actions = ['tap_100_200', 'scroll_down', 'tap_150_300', 'back', 'tap_200_400']
should_abort, new_count, reset = poster._detect_and_recover_from_loop(recent_actions, 0, 5)
assert not should_abort, 'Should not abort with varied actions'
assert new_count == 0, 'Recovery count should remain 0'
assert not reset, 'Should not reset actions'

print('No-loop detection tests passed')
"
```

### 5. Unit Test - _detect_and_recover_from_loop() (loop with recovery)
```bash
python -c "
from post_reel_smart import SmartInstagramPoster
from unittest.mock import MagicMock
import time

poster = SmartInstagramPoster.__new__(SmartInstagramPoster)
poster.LOOP_THRESHOLD = 5
poster.MAX_LOOP_RECOVERIES = 2
poster.press_key = MagicMock()
poster.adb = MagicMock()

# Patch time.sleep to speed up test
original_sleep = time.sleep
time.sleep = lambda x: None

try:
    # Test loop detected - first recovery
    recent_actions = ['tap_100_200'] * 5
    should_abort, new_count, reset = poster._detect_and_recover_from_loop(recent_actions, 0, 10)
    assert not should_abort, 'Should not abort on first recovery'
    assert new_count == 1, f'Recovery count should be 1, got {new_count}'
    assert reset, 'Should reset actions after recovery'
    assert poster.press_key.call_count == 5, f'Should press BACK 5 times, called {poster.press_key.call_count}'
    assert poster.adb.call_count >= 2, 'Should call adb for force-stop and monkey'
    
    print('Loop recovery test passed')
finally:
    time.sleep = original_sleep
"
```

### 6. Unit Test - _detect_and_recover_from_loop() (max recoveries exceeded)
```bash
python -c "
from post_reel_smart import SmartInstagramPoster
from unittest.mock import MagicMock

poster = SmartInstagramPoster.__new__(SmartInstagramPoster)
poster.LOOP_THRESHOLD = 5
poster.MAX_LOOP_RECOVERIES = 2

# Test max recoveries exceeded - should abort
recent_actions = ['tap_100_200'] * 5
should_abort, new_count, reset = poster._detect_and_recover_from_loop(recent_actions, 2, 10)
assert should_abort, 'Should abort when max recoveries exceeded'
assert new_count == 3, f'Recovery count should be 3, got {new_count}'

print('Max recovery abort test passed')
"
```

### 7. Integration Test - Full post() method still works
```bash
# Verify post() method still exists and has proper structure
python -c "
import inspect
from post_reel_smart import SmartInstagramPoster

# Check post method signature
sig = inspect.signature(SmartInstagramPoster.post)
params = list(sig.parameters.keys())
expected = ['self', 'video_path', 'caption', 'max_steps', 'humanize']
assert params == expected, f'post() params changed: {params} != {expected}'

# Check that post() uses the helper methods (by inspecting source)
source = inspect.getsource(SmartInstagramPoster.post)
assert '_build_action_signature' in source, 'post() should call _build_action_signature'
assert '_detect_and_recover_from_loop' in source, 'post() should call _detect_and_recover_from_loop'
assert 'recent_actions' in source, 'post() should still track recent_actions'
assert 'loop_recovery_count' in source, 'post() should still track loop_recovery_count'

print('Integration check passed')
"
```

### 8. Line Count Verification
```bash
# Verify the post() method is shorter after extraction
python -c "
import inspect
from post_reel_smart import SmartInstagramPoster

source = inspect.getsource(SmartInstagramPoster.post)
lines = [l for l in source.split('\n') if l.strip()]
print(f'post() method: {len(lines)} non-empty lines')

# The inline loop detection was ~35 lines, now ~10 lines
# post() should be noticeably shorter
assert len(lines) < 250, f'post() should be shorter after extraction, got {len(lines)} lines'
print('Line count check passed')
"
```

### 9. Live Test - Run with actual posting (manual verification)
```bash
# This should be run manually to verify behavior is unchanged
# python post_reel_smart.py test_phone test_video.mp4 "Test caption"
# Verify loop detection still works by observing logs during stuck states
```
