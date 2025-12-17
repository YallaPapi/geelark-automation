# Task ID: 43

**Title:** Extract humanize action handlers from humanize_before_post()

**Status:** done

**Dependencies:** 39 ✓, 40 ✓

**Priority:** medium

**Description:** Extract the 4 inline action handlers (scroll_feed, view_story, scroll_reels, check_notifications) from humanize_before_post() method (lines 151-243) into dedicated private helper methods, reducing the 93-line method to a clean ~25-line dispatch loop.

**Details:**

## Current State Analysis

The `humanize_before_post()` method in `post_reel_smart.py` (lines 151-243, ~93 lines) contains 4 inline action handlers with nested loops:

### Current Structure:
```python
def humanize_before_post(self):
    print("\n[HUMANIZE] Performing random actions before posting...")
    actions_done = 0
    max_actions = random.randint(2, 4)

    for _ in range(max_actions):
        action = random.choice(['scroll_feed', 'view_story', 'scroll_reels', 'check_notifications'])

        if action == 'scroll_feed':
            # ~11 lines of inline scroll logic (lines 160-170)
            ...
        elif action == 'view_story':
            # ~19 lines of inline story viewing logic (lines 172-190)
            ...
        elif action == 'scroll_reels':
            # ~29 lines of inline reels browsing logic (lines 192-220)
            ...
        elif action == 'check_notifications':
            # ~15 lines of inline notification checking logic (lines 222-236)
            ...
```

## Implementation Plan

### Step 1: Extract `_humanize_scroll_feed()` (~15 lines)

**Location:** Add after `random_delay()` method (around line 150)

```python
def _humanize_scroll_feed(self):
    """Scroll through Instagram feed randomly."""
    print("  - Scrolling feed...")
    scroll_count = random.randint(1, 3)
    for _ in range(scroll_count):
        self.swipe(360, 900, 360, 400, random.randint(200, 400))
        self.random_delay(1.0, 3.0)
    # Scroll back up sometimes
    if random.random() < 0.3:
        self.swipe(360, 400, 360, 900, 300)
        self.random_delay(0.5, 1.5)
    return True  # Action always succeeds
```

### Step 2: Extract `_humanize_view_story()` (~25 lines)

```python
def _humanize_view_story(self):
    """View Instagram stories randomly.
    
    Returns True if a story was viewed, False if no unseen stories found.
    """
    print("  - Viewing a story...")
    elements, _ = self.dump_ui()
    story_elements = [e for e in elements 
                      if 'story' in e.get('desc', '').lower() 
                      and 'unseen' in e.get('desc', '').lower()]
    if not story_elements:
        return False
    
    story = random.choice(story_elements)
    self.tap(story['center'][0], story['center'][1])
    view_time = random.uniform(3, 8)
    print(f"    Watching for {view_time:.1f}s...")
    time.sleep(view_time)
    
    # Tap through a few more stories sometimes
    if random.random() < 0.5:
        for _ in range(random.randint(1, 3)):
            self.tap(650, 640)  # Tap right side to skip to next story
            time.sleep(random.uniform(2, 5))
    
    # Go back
    self.press_key('KEYCODE_BACK')
    self.random_delay(1.0, 2.0)
    return True
```

### Step 3: Extract `_humanize_scroll_reels()` (~30 lines)

```python
def _humanize_scroll_reels(self):
    """Browse Instagram Reels tab randomly.
    
    Returns True if reels were browsed, False if Reels tab not found.
    """
    print("  - Browsing reels...")
    elements, _ = self.dump_ui()
    reels_tab = [e for e in elements 
                 if 'reels' in e.get('desc', '').lower() and e['clickable']]
    if not reels_tab:
        return False
    
    self.tap(reels_tab[0]['center'][0], reels_tab[0]['center'][1])
    self.random_delay(2.0, 4.0)
    
    # Watch a few reels
    for _ in range(random.randint(1, 3)):
        watch_time = random.uniform(3, 10)
        print(f"    Watching reel for {watch_time:.1f}s...")
        time.sleep(watch_time)
        # Sometimes double-tap to like
        if random.random() < 0.15:
            print("    Double-tap like!")
            self.tap(360, 640)
            time.sleep(0.1)
            self.tap(360, 640)
            self.random_delay(0.5, 1.0)
        # Swipe to next reel
        self.swipe(360, 1000, 360, 300, 200)
        self.random_delay(0.5, 1.5)
    
    # Go back to home
    elements, _ = self.dump_ui()
    home_tab = [e for e in elements 
                if 'home' in e.get('desc', '').lower() and e['clickable']]
    if home_tab:
        self.tap(home_tab[0]['center'][0], home_tab[0]['center'][1])
    self.random_delay(1.0, 2.0)
    return True
```

### Step 4: Extract `_humanize_check_notifications()` (~20 lines)

```python
def _humanize_check_notifications(self):
    """Check Instagram notifications/activity tab randomly.
    
    Returns True if notifications were checked, False if tab not found.
    """
    print("  - Checking notifications...")
    elements, _ = self.dump_ui()
    notif_btn = [e for e in elements 
                 if ('notification' in e.get('desc', '').lower() 
                     or 'activity' in e.get('desc', '').lower()) 
                 and e['clickable']]
    if not notif_btn:
        return False
    
    self.tap(notif_btn[0]['center'][0], notif_btn[0]['center'][1])
    self.random_delay(2.0, 4.0)
    
    # Scroll through notifications sometimes
    if random.random() < 0.5:
        self.swipe(360, 800, 360, 400, 300)
        self.random_delay(1.0, 2.0)
    
    # Go back
    self.press_key('KEYCODE_BACK')
    self.random_delay(1.0, 2.0)
    return True
```

### Step 5: Refactor `humanize_before_post()` to Clean Dispatch Loop (~25 lines)

```python
def humanize_before_post(self):
    """Perform random human-like actions before posting."""
    print("\n[HUMANIZE] Performing random actions before posting...")
    
    # Map action names to handler methods
    action_handlers = {
        'scroll_feed': self._humanize_scroll_feed,
        'view_story': self._humanize_view_story,
        'scroll_reels': self._humanize_scroll_reels,
        'check_notifications': self._humanize_check_notifications,
    }
    
    actions_done = 0
    max_actions = random.randint(2, 4)

    for _ in range(max_actions):
        action = random.choice(list(action_handlers.keys()))
        handler = action_handlers[action]
        
        if handler():
            actions_done += 1
        
        if actions_done >= max_actions:
            break

    print(f"[HUMANIZE] Completed {actions_done} random actions")
    # Small delay before proceeding
    self.random_delay(1.0, 3.0)
```

## Key Design Decisions

1. **Return values for success tracking**: Each helper returns `True` if the action was performed, `False` if UI elements weren't found. This preserves the original behavior where `actions_done` only increments on successful actions.

2. **Naming convention**: Using `_humanize_*` prefix to:
   - Indicate private methods (underscore prefix)
   - Group them logically with the humanization feature
   - Make them easy to find via search/autocomplete

3. **No parameter passing**: All helpers use `self` to access `dump_ui()`, `tap()`, `swipe()`, `press_key()`, and `random_delay()`. This keeps signatures clean since all state is on the instance.

4. **Preserve exact behavior**: The random delays, tap coordinates, and conditional logic are preserved exactly as-is to avoid changing humanization behavior.

## File Changes Summary

| Change | Lines Affected |
|--------|----------------|
| Add `_humanize_scroll_feed()` | Insert ~15 lines after line 149 |
| Add `_humanize_view_story()` | Insert ~25 lines |
| Add `_humanize_scroll_reels()` | Insert ~30 lines |
| Add `_humanize_check_notifications()` | Insert ~20 lines |
| Replace `humanize_before_post()` body | Lines 151-243 → ~25 lines |

**Net effect**: From 93 lines to ~25 lines in main method, with 4 focused helper methods (~90 lines total). Total code grows slightly but complexity per method decreases significantly.

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
methods = ['_humanize_scroll_feed', '_humanize_view_story', '_humanize_scroll_reels', '_humanize_check_notifications', 'humanize_before_post']
for m in methods:
    assert hasattr(poster, m), f'Missing method: {m}'
    assert callable(getattr(poster, m)), f'Not callable: {m}'
print('All humanize methods exist and are callable')
"
```

### 3. Method Signature Verification
```bash
python -c "
import inspect
from post_reel_smart import SmartInstagramPoster

# All humanize helpers should take only self (no extra params)
for name in ['_humanize_scroll_feed', '_humanize_view_story', '_humanize_scroll_reels', '_humanize_check_notifications']:
    method = getattr(SmartInstagramPoster, name)
    sig = inspect.signature(method)
    params = list(sig.parameters.keys())
    assert params == ['self'], f'{name} should only have self param, got: {params}'
print('All helper methods have correct (self-only) signature')
"
```

### 4. Return Type Verification (Static Analysis)
```bash
# Check that helpers return bool values
grep -A 2 "def _humanize_" post_reel_smart.py | grep "return True\|return False"
# Expected: Should see return True/False in each helper
```

### 5. Main Method Structure Verification
```bash
python -c "
import inspect
from post_reel_smart import SmartInstagramPoster

# Get source of humanize_before_post
source = inspect.getsource(SmartInstagramPoster.humanize_before_post)
lines = source.strip().split('\n')
print(f'humanize_before_post() has {len(lines)} lines')
assert len(lines) <= 30, f'Expected ~25 lines, got {len(lines)}'

# Should contain dispatch logic, not inline handlers
assert 'action_handlers' in source or 'handler()' in source, 'Should use dispatch pattern'
assert 'for _ in range(scroll_count)' not in source, 'Should not have inline scroll loop'
print('Main method is properly refactored to dispatch pattern')
"
```

### 6. Live Behavior Test (Integration)
```bash
# Run with humanize flag on a test account to verify behavior unchanged
# Note: This requires a real Geelark phone to be available
python -c "
from post_reel_smart import SmartInstagramPoster
import unittest.mock as mock

# Create poster with mocked connection
poster = SmartInstagramPoster('test_phone')

# Mock the UI controller methods to avoid needing real device
poster._ui_controller = mock.MagicMock()
poster._conn.appium_driver = mock.MagicMock()

# Mock dump_ui to return elements that will trigger actions
poster.dump_ui = mock.MagicMock(return_value=([
    {'desc': 'unseen story', 'text': '', 'center': (100, 100), 'clickable': True},
    {'desc': 'reels', 'text': '', 'center': (200, 200), 'clickable': True},
    {'desc': 'notification', 'text': '', 'center': (300, 300), 'clickable': True},
    {'desc': 'home', 'text': '', 'center': (50, 50), 'clickable': True},
], ''))

# Run humanize - should call helper methods
import random
random.seed(42)  # Deterministic for testing
poster.humanize_before_post()

# Verify swipe/tap/press_key were called (humanization happened)
assert poster._ui_controller.swipe.called or poster._ui_controller.tap.called, 'Humanization should have done something'
print('Humanize behavior test passed')
"
```

### 7. Verify Original Behavior Preserved
```bash
# Check that random selection and max_actions limit are preserved
grep -A 5 "def humanize_before_post" post_reel_smart.py | grep -E "random.choice|max_actions|random.randint"
# Expected: Should see random.choice for action selection and random.randint(2, 4) for max_actions
```

### 8. Full Integration Test (Optional - Requires Live Phone)
```bash
# Test with real phone to verify humanization still works
# Use --humanize flag if posting_scheduler supports it, or test directly:
python -c "
# Only run this with a real test account
# python post_reel_smart.py test_account test_video.mp4 'test caption' --humanize
print('Skip live test - run manually with real phone')
"
```
