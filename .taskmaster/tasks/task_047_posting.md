# Task ID: 47

**Title:** Convert action dispatch if/elif chain to ACTION_HANDLERS dispatch table

**Status:** done

**Dependencies:** 43 ✓, 3 ✓

**Priority:** medium

**Description:** Refactor the 8-action if/elif chain in the post() method (lines 801-854) to use an ACTION_HANDLERS class constant dict mapping action names to handler methods, following the Command pattern established in Task 43's humanize dispatch table.

**Details:**

## Current State Analysis

The `post()` method in `post_reel_smart.py` (lines 801-854) contains an 8-condition if/elif chain for dispatching actions:

```python
# Execute action
if action['action'] == 'done':
    print("\n[SUCCESS] Share initiated!")
    # ... 10 lines of success handling
    return True

elif action['action'] == 'home':
    print("  [HOME] Going to home screen...")
    self.press_key('KEYCODE_HOME')
    time.sleep(2)

elif action['action'] == 'open_instagram':
    print("  [OPEN] Opening Instagram...")
    self.adb("am force-stop com.instagram.android")
    time.sleep(1)
    self.adb("monkey -p com.instagram.android 1")
    time.sleep(4)

elif action['action'] == 'tap':
    idx = action.get('element_index', 0)
    if 0 <= idx < len(elements):
        elem = elements[idx]
        self.tap(elem['center'][0], elem['center'][1])
    else:
        print(f"  Invalid element index: {idx}")

elif action['action'] == 'tap_and_type':
    if self._handle_tap_and_type(action, elements, caption):
        continue  # Helper handled it and wants to skip to next step

elif action['action'] == 'back':
    self.press_key('KEYCODE_BACK')

elif action['action'] == 'scroll_down':
    self.adb("input swipe 360 900 360 400 300")

elif action['action'] == 'scroll_up':
    self.adb("input swipe 360 400 360 900 300")
```

## Target Implementation Pattern

Follow Task 43's pattern (lines 245-251 in `humanize_before_post()`):

```python
# Dispatch table for humanize actions
action_handlers = {
    'scroll_feed': self._humanize_scroll_feed,
    'view_story': self._humanize_view_story,
    'scroll_reels': self._humanize_scroll_reels,
    'check_notifications': self._humanize_check_notifications,
}
```

## Implementation Steps

### Step 1: Create Handler Methods

Extract each action into a private handler method. Handlers will receive context via a dataclass:

```python
@dataclass
class ActionContext:
    """Context passed to action handlers during post() execution."""
    action: Dict[str, Any]
    elements: List[Dict]
    caption: str
    humanize: bool

class SmartInstagramPoster:
    # ... existing code ...
    
    def _action_done(self, ctx: ActionContext) -> Optional[bool]:
        """Handle 'done' action - posting complete."""
        print("\n[SUCCESS] Share initiated!")
        if self.wait_for_upload_complete(timeout=60):
            print("[SUCCESS] Upload confirmed complete!")
        else:
            print("[WARNING] Upload confirmation timeout - may still be processing")
        if ctx.humanize:
            self.humanize_after_post()
        return True  # Return value signals post() to return True
    
    def _action_home(self, ctx: ActionContext) -> None:
        """Handle 'home' action - go to home screen."""
        print("  [HOME] Going to home screen...")
        self.press_key('KEYCODE_HOME')
        time.sleep(2)
    
    def _action_open_instagram(self, ctx: ActionContext) -> None:
        """Handle 'open_instagram' action - restart Instagram app."""
        print("  [OPEN] Opening Instagram...")
        self.adb("am force-stop com.instagram.android")
        time.sleep(1)
        self.adb("monkey -p com.instagram.android 1")
        time.sleep(4)
    
    def _action_tap(self, ctx: ActionContext) -> None:
        """Handle 'tap' action - tap an element by index."""
        idx = ctx.action.get('element_index', 0)
        if 0 <= idx < len(ctx.elements):
            elem = ctx.elements[idx]
            self.tap(elem['center'][0], elem['center'][1])
        else:
            print(f"  Invalid element index: {idx}")
    
    def _action_tap_and_type(self, ctx: ActionContext) -> Optional[str]:
        """Handle 'tap_and_type' action - tap field and type caption."""
        if self._handle_tap_and_type(ctx.action, ctx.elements, ctx.caption):
            return 'continue'  # Signal to skip to next iteration
        return None
    
    def _action_back(self, ctx: ActionContext) -> None:
        """Handle 'back' action - press back key."""
        self.press_key('KEYCODE_BACK')
    
    def _action_scroll_down(self, ctx: ActionContext) -> None:
        """Handle 'scroll_down' action - swipe up to scroll down."""
        self.adb("input swipe 360 900 360 400 300")
    
    def _action_scroll_up(self, ctx: ActionContext) -> None:
        """Handle 'scroll_up' action - swipe down to scroll up."""
        self.adb("input swipe 360 400 360 900 300")
```

### Step 2: Define ACTION_HANDLERS Dispatch Table

Create a class-level constant mapping action names to handler methods:

```python
class SmartInstagramPoster:
    # Class constant for action dispatch (Command pattern)
    # Keys match action names from ClaudeUIAnalyzer (claude_analyzer.py:103)
    ACTION_HANDLERS = {
        'done': '_action_done',
        'home': '_action_home', 
        'open_instagram': '_action_open_instagram',
        'tap': '_action_tap',
        'tap_and_type': '_action_tap_and_type',
        'back': '_action_back',
        'scroll_down': '_action_scroll_down',
        'scroll_up': '_action_scroll_up',
    }
```

Note: Use method name strings since we can't reference instance methods at class definition time.

### Step 3: Refactor post() Method

Replace the if/elif chain with dispatch table lookup:

```python
def post(self, video_path, caption, max_steps=30, humanize=False):
    # ... existing setup code (lines 722-800) ...
    
    # Create context for handlers
    ctx = ActionContext(
        action=action,
        elements=elements,
        caption=caption,
        humanize=humanize
    )
    
    # Dispatch action using handler table
    action_name = action['action']
    handler_name = self.ACTION_HANDLERS.get(action_name)
    
    if handler_name is None:
        print(f"  Unknown action: {action_name}")
        time.sleep(1)
        continue
    
    # Get and call handler method
    handler = getattr(self, handler_name)
    result = handler(ctx)
    
    # Handle special return values
    if result is True:
        return True  # 'done' handler signals success
    elif result is False:
        return False  # Handler signals failure
    elif result == 'continue':
        continue  # Skip to next loop iteration
    
    # ... existing loop detection code (lines 846-854) ...
```

### Step 4: Handle ActionContext Import

Add the dataclass import and definition at the top of the file:

```python
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

@dataclass
class ActionContext:
    """Context passed to action handlers during post() execution."""
    action: Dict[str, Any]
    elements: List[Dict]
    caption: str
    humanize: bool
```

## Benefits

1. **Consistency**: Matches the dispatch table pattern from Task 43 (`humanize_before_post()`)
2. **Maintainability**: Adding new actions requires only: (1) add handler method, (2) add entry to dict
3. **Testability**: Each handler method can be unit tested independently
4. **Readability**: The `post()` method becomes shorter and clearer
5. **Extensibility**: Easy to add new actions without modifying dispatch logic
6. **Self-documenting**: The ACTION_HANDLERS dict serves as documentation of supported actions

## Files Modified

- `post_reel_smart.py`: Add ActionContext dataclass, 8 handler methods, ACTION_HANDLERS constant, refactor post() dispatch logic

## Estimated Line Changes

- Remove: ~53 lines (if/elif chain)
- Add: ~70 lines (dataclass + 8 handlers + dict + dispatch logic)
- Net: +17 lines, but much better organization

**Test Strategy:**

## Test Strategy

### 1. Syntax and Import Verification
```bash
# Verify the file has no syntax errors and imports correctly
python -c "from post_reel_smart import SmartInstagramPoster; print('Import successful')"
```

### 2. Verify ACTION_HANDLERS Constant Exists
```bash
python -c "
from post_reel_smart import SmartInstagramPoster
print('ACTION_HANDLERS:', SmartInstagramPoster.ACTION_HANDLERS)
print('Keys:', list(SmartInstagramPoster.ACTION_HANDLERS.keys()))
expected = ['done', 'home', 'open_instagram', 'tap', 'tap_and_type', 'back', 'scroll_down', 'scroll_up']
assert set(SmartInstagramPoster.ACTION_HANDLERS.keys()) == set(expected), 'Missing handlers!'
print('All 8 handlers present')
"
```

### 3. Verify Handler Methods Exist
```bash
python -c "
from post_reel_smart import SmartInstagramPoster
poster = SmartInstagramPoster.__new__(SmartInstagramPoster)  # Create without __init__
handlers = ['_action_done', '_action_home', '_action_open_instagram', '_action_tap', 
            '_action_tap_and_type', '_action_back', '_action_scroll_down', '_action_scroll_up']
for handler in handlers:
    assert hasattr(poster, handler), f'Missing handler: {handler}'
    assert callable(getattr(poster, handler)), f'Handler not callable: {handler}'
print('All 8 handler methods exist and are callable')
"
```

### 4. Verify ActionContext Dataclass
```bash
python -c "
from post_reel_smart import ActionContext
ctx = ActionContext(
    action={'action': 'tap', 'element_index': 0},
    elements=[{'center': (100, 200)}],
    caption='Test caption',
    humanize=False
)
print('ActionContext created:', ctx)
print('action:', ctx.action)
print('elements:', ctx.elements)
print('caption:', ctx.caption)
print('humanize:', ctx.humanize)
"
```

### 5. Static Analysis - No if/elif Chain for Actions
```bash
# Verify the old if/elif chain is removed from post()
python -c "
import inspect
from post_reel_smart import SmartInstagramPoster
source = inspect.getsource(SmartInstagramPoster.post)
# Should NOT have the old pattern
assert \"elif action['action'] == 'back'\" not in source, 'Old if/elif chain still present!'
assert \"elif action['action'] == 'scroll_down'\" not in source, 'Old if/elif chain still present!'
# SHOULD have new dispatch pattern
assert 'ACTION_HANDLERS' in source or 'handler_name' in source, 'New dispatch pattern not found!'
print('Dispatch table pattern confirmed')
"
```

### 6. Integration Test - Full Posting Flow (Dry Run)
```bash
# Test with a mock scenario to verify dispatch works
# This requires the phone infrastructure but verifies the refactor
python -c "
from post_reel_smart import SmartInstagramPoster

# Check that the class can be instantiated (basic sanity)
try:
    poster = SmartInstagramPoster('test_phone')
    # Verify ACTION_HANDLERS is accessible
    assert hasattr(poster, 'ACTION_HANDLERS')
    # Verify all handler methods resolve
    for action_name, handler_name in poster.ACTION_HANDLERS.items():
        handler = getattr(poster, handler_name)
        print(f'{action_name} -> {handler_name} OK')
except Exception as e:
    # May fail due to missing credentials/phone, but dispatch should be configured
    print(f'Expected init error (no phone): {type(e).__name__}')
"
```

### 7. Live Test (Full Integration)
```bash
# Run an actual post to verify behavior is identical
# Use a test account and video
python post_reel_smart.py <test_phone> <test_video.mp4> "Test caption #test"
```

### 8. Verify Parallel Orchestrator Still Works
```bash
# The orchestrator uses SmartInstagramPoster internally
python parallel_orchestrator.py --status
```

### 9. Code Quality Checks
```bash
# Check for any remaining hardcoded action strings in dispatch area
grep -n "action\['action'\] ==" post_reel_smart.py | head -20
# Should only show the handler return value checks, not the old dispatch
```

### Success Criteria
1. All 8 actions in ACTION_HANDLERS constant
2. All 8 handler methods (_action_*) exist and are callable
3. ActionContext dataclass properly stores all fields
4. No if/elif chain for action dispatch remains
5. Same behavior: posting works identically before and after refactor
6. Existing tests pass (parallel_orchestrator.py --status)
7. Live post test succeeds with same output pattern
