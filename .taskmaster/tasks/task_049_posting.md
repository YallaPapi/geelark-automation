# Task ID: 49

**Title:** Extract screen coordinate constants in post_reel_smart.py

**Status:** done

**Dependencies:** 39 ✓, 43 ✓, 47 ✓

**Priority:** medium

**Description:** Define named constants for magic numbers like SCREEN_CENTER_X=360, FEED_TOP_Y=400, FEED_BOTTOM_Y=900 used in swipe/tap operations. This makes the code self-documenting and easier to adjust for different screen sizes.

**Details:**

## Current State Analysis

Magic numbers are scattered throughout `post_reel_smart.py` for screen coordinate operations. These numbers appear in swipe and tap calls but lack semantic meaning:

### Magic Numbers Found (multi-use candidates):

**Horizontal coordinates:**
- `360` - Screen center X (12+ occurrences across swipes and taps)
- `650` - Right side X (used for story skip tap at line 180)

**Vertical coordinates:**
- `400` - Feed top Y / scroll destination (used in scroll_down swipes)
- `640` - Screen center Y (used for double-tap like at lines 205-207)
- `800` - Notifications scroll Y
- `900` - Feed bottom Y / scroll start (used in scroll_up swipes)
- `1000` - Reels bottom Y (used in reels swipe at line 210)
- `300` - Reels top Y (used in reels swipe at line 210)

**Duration constants:**
- `200, 300, 400` - Swipe durations in ms (some via `random.randint(200, 400)`)

### Implementation Plan

**Step 1: Define constants at class level or module level**

Add a new `ScreenCoordinates` dataclass or class-level constants in `post_reel_smart.py`:

```python
# Screen coordinate constants for 720x1280 resolution
# These values are calibrated for Geelark cloud phones
class ScreenCoords:
    """Screen coordinate constants for UI interactions."""
    # Horizontal
    SCREEN_CENTER_X = 360  # Center of 720px screen
    STORY_SKIP_X = 650     # Right side for story skip tap
    
    # Vertical
    FEED_TOP_Y = 400       # Top of scrollable feed area
    SCREEN_CENTER_Y = 640  # Center of 1280px screen
    NOTIFICATIONS_Y = 800  # Notifications scroll position
    FEED_BOTTOM_Y = 900    # Bottom of scrollable feed area
    REELS_TOP_Y = 300      # Top Y for reels swipe
    REELS_BOTTOM_Y = 1000  # Bottom Y for reels swipe
    
    # Swipe durations (ms)
    SWIPE_FAST_MS = 200
    SWIPE_NORMAL_MS = 300
    SWIPE_SLOW_MS = 400
```

**Step 2: Update usages in `post_reel_smart.py`**

Replace magic numbers with constants:

```python
# Before (line 156):
self.swipe(360, 900, 360, 400, random.randint(200, 400))

# After:
self.swipe(ScreenCoords.SCREEN_CENTER_X, ScreenCoords.FEED_BOTTOM_Y,
           ScreenCoords.SCREEN_CENTER_X, ScreenCoords.FEED_TOP_Y,
           random.randint(ScreenCoords.SWIPE_FAST_MS, ScreenCoords.SWIPE_SLOW_MS))
```

**Lines to update in `post_reel_smart.py`:**
- Line 156: `_humanize_scroll_feed()` - scroll down swipe
- Line 160: `_humanize_scroll_feed()` - scroll up swipe
- Line 180: `_humanize_view_story()` - story skip tap (650, 640)
- Lines 205-207: `_humanize_scroll_reels()` - double-tap like (360, 640)
- Line 210: `_humanize_scroll_reels()` - reels swipe (360, 1000, 360, 300)
- Line 232: `_humanize_check_notifications()` - notifications swipe
- Line 283: `humanize_after_post()` - feed scroll
- Line 564: `_action_scroll_down()` - ADB swipe command
- Line 568: `_action_scroll_up()` - ADB swipe command

**Step 3: Update `appium_ui_controller.py`**

The `scroll_down()` and `scroll_up()` methods (lines 221-227) also use these magic numbers. Either:
1. Import `ScreenCoords` from `post_reel_smart.py` (creates import dependency)
2. Define constants in a shared module (e.g., `config.py`)
3. Define locally in `appium_ui_controller.py` (duplicate but isolated)

**Recommended approach:** Add constants to `config.py` since it's already the centralized config:

```python
# In config.py, add:
class ScreenCoords:
    """Screen coordinate constants for 720x1280 Geelark phones."""
    SCREEN_CENTER_X = 360
    FEED_TOP_Y = 400
    SCREEN_CENTER_Y = 640
    STORY_SKIP_X = 650
    NOTIFICATIONS_Y = 800
    FEED_BOTTOM_Y = 900
    REELS_TOP_Y = 300
    REELS_BOTTOM_Y = 1000
    SWIPE_FAST_MS = 200
    SWIPE_NORMAL_MS = 300
    SWIPE_SLOW_MS = 400
```

Then import in both files:
```python
from config import Config, ScreenCoords, setup_environment
```

**Step 4: Exclude single-use magic numbers**

Only extract constants for values used in **multiple places**. Single-use coordinates like element centers from UI dumps should remain as-is since they're dynamically determined.

### Files to Modify

1. `config.py` - Add `ScreenCoords` class/dataclass
2. `post_reel_smart.py` - Import and use `ScreenCoords` constants (9 locations)
3. `appium_ui_controller.py` - Import and use `ScreenCoords` constants (2 locations)

**Test Strategy:**

## Test Strategy

### 1. Syntax and Import Verification
```bash
# Verify all files have no syntax errors after changes
python -c "from config import Config, ScreenCoords; print('config.py OK')"
python -c "from post_reel_smart import SmartInstagramPoster; print('post_reel_smart.py OK')"
python -c "from appium_ui_controller import AppiumUIController; print('appium_ui_controller.py OK')"
```

### 2. Verify ScreenCoords Constants Exist
```bash
python -c "
from config import ScreenCoords
print('SCREEN_CENTER_X:', ScreenCoords.SCREEN_CENTER_X)
print('FEED_TOP_Y:', ScreenCoords.FEED_TOP_Y)
print('FEED_BOTTOM_Y:', ScreenCoords.FEED_BOTTOM_Y)
print('All constants defined correctly')
"
```

### 3. Verify No Magic Numbers Remain in Multi-Use Locations
```bash
# Check that 360 is not used as a raw literal in swipe/tap calls
# (should be replaced with ScreenCoords.SCREEN_CENTER_X)
grep -n "swipe(360" post_reel_smart.py
grep -n "tap(360" post_reel_smart.py
grep -n "swipe(360" appium_ui_controller.py
# Expected: No matches (all replaced with constants)
```

### 4. Verify Constant Values Match Original
```bash
python -c "
from config import ScreenCoords
# Verify the constants have the correct values
assert ScreenCoords.SCREEN_CENTER_X == 360, 'SCREEN_CENTER_X wrong'
assert ScreenCoords.FEED_TOP_Y == 400, 'FEED_TOP_Y wrong'
assert ScreenCoords.FEED_BOTTOM_Y == 900, 'FEED_BOTTOM_Y wrong'
assert ScreenCoords.SCREEN_CENTER_Y == 640, 'SCREEN_CENTER_Y wrong'
assert ScreenCoords.REELS_BOTTOM_Y == 1000, 'REELS_BOTTOM_Y wrong'
assert ScreenCoords.REELS_TOP_Y == 300, 'REELS_TOP_Y wrong'
print('All constant values verified')
"
```

### 5. Behavior Verification (No Code Breakage)
```bash
# Quick instantiation test to ensure the class still works
python -c "
from post_reel_smart import SmartInstagramPoster
poster = SmartInstagramPoster('test_phone')
print('SmartInstagramPoster instantiation OK')
"
```

### 6. Unit Test for Swipe Methods
```bash
python -c "
from config import ScreenCoords
from appium_ui_controller import AppiumUIController

# Verify scroll_down and scroll_up use correct values
# (Check source code for ScreenCoords usage)
import inspect
source = inspect.getsource(AppiumUIController.scroll_down)
assert 'ScreenCoords' in source or 'SCREEN_CENTER_X' in source, 'scroll_down should use constants'
print('AppiumUIController methods use constants')
"
```

### 7. Full Integration Test (Optional - requires running phone)
```bash
# Only run if a test phone is available
# python post_reel_smart.py test_phone test_video.mp4 "Test caption"
```

### 8. Code Review Checklist
- [ ] All multi-use magic numbers (360, 400, 640, 900, etc.) replaced with named constants
- [ ] Constants defined in `config.py` ScreenCoords class
- [ ] `post_reel_smart.py` imports and uses ScreenCoords
- [ ] `appium_ui_controller.py` imports and uses ScreenCoords
- [ ] Single-use numbers (from element bounds) NOT extracted
- [ ] Code behavior unchanged (same coordinates used)
