# Task ID: 39

**Title:** Extract AppiumUIController from SmartInstagramPoster

**Status:** done

**Dependencies:** 25 ✓, 37 ✓, 23 ✓

**Priority:** medium

**Description:** Create appium_ui_controller.py with an AppiumUIController class that encapsulates all Appium-based UI interaction methods, extracting tap(), swipe(), press_key(), type_text_via_appium(), and dump_ui() from post_reel_smart.py to create a clean interface between posting logic and device control.

**Details:**

## Current State Analysis

The `SmartInstagramPoster` class in `post_reel_smart.py` contains several Appium-based UI interaction methods that should be extracted:

### Methods to Extract (with line numbers):

1. **`tap(x, y)`** (lines 91-97): Taps at coordinates using Appium driver
   - Requires `self.appium_driver`
   - Includes 1.5s sleep after tap

2. **`swipe(x1, y1, x2, y2, duration_ms)`** (lines 99-103): Swipes between points
   - Requires `self.appium_driver`

3. **`press_key(keycode)`** (lines 105-117): Presses Android key codes
   - Maps string keycodes ('KEYCODE_BACK') to integers
   - Requires `self.appium_driver`

4. **`type_text(text)`** (lines 441-473): Types text using Appium send_keys
   - Finds EditText elements or uses active element
   - Requires `self.appium_driver`

5. **`dump_ui()`** (lines 475-537): Dumps UI hierarchy via Appium page_source
   - Parses XML, extracts clickable elements with bounds
   - Handles UiAutomator2 crash recovery via `reconnect_appium()`
   - Returns tuple of (elements_list, raw_xml)

### Supporting Methods to Also Extract:

6. **`is_uiautomator2_crash(exception)`** (lines 69-77): Detects UiAutomator2 crash signatures
7. **`reconnect_appium()`** (lines 79-89): Reconnects Appium after crash
8. **`is_keyboard_visible()`** (lines 422-439): Checks keyboard visibility via ADB dumpsys

## Implementation Plan

### 1. Create `appium_ui_controller.py`

```python
"""
Appium UI Controller - encapsulates all Appium-based UI interactions.

This module provides a clean interface for device UI control, separating
posting logic from low-level Appium operations.
"""
import re
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple, Optional, Union, Callable
from dataclasses import dataclass

from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy

from config import Config

@dataclass
class UIElement:
    """Represents a parsed UI element from the hierarchy."""
    text: str
    desc: str
    resource_id: str
    bounds: str
    center: Tuple[int, int]
    clickable: bool

class AppiumUIControllerError(Exception):
    """Base exception for AppiumUIController errors."""
    pass

class UIAutomator2CrashError(AppiumUIControllerError):
    """Raised when UiAutomator2 crashes on device."""
    pass

class AppiumUIController:
    """
    Encapsulates all Appium-based UI interaction methods.
    
    This class provides a clean interface for device UI control operations,
    handling Appium driver interactions, crash recovery, and UI hierarchy parsing.
    
    Usage:
        driver = webdriver.Remote(...)
        controller = AppiumUIController(driver)
        
        # Basic interactions
        controller.tap(500, 500)
        controller.swipe(100, 500, 100, 200)
        controller.press_key('KEYCODE_BACK')
        controller.type_text("Hello world")
        
        # UI inspection
        elements, xml = controller.dump_ui()
    """
    
    # Android keycode mapping
    KEYCODES = {
        'KEYCODE_BACK': 4,
        'KEYCODE_HOME': 3,
        'KEYCODE_ENTER': 66,
        'KEYCODE_TAB': 61,
        'KEYCODE_MENU': 82,
    }
    
    def __init__(
        self,
        driver: webdriver.Remote,
        adb_shell_func: Optional[Callable[[str], str]] = None,
        reconnect_func: Optional[Callable[[], bool]] = None,
        tap_delay: float = 1.5
    ):
        """
        Initialize AppiumUIController.
        
        Args:
            driver: Appium WebDriver instance
            adb_shell_func: Optional function to run ADB shell commands (for keyboard detection)
            reconnect_func: Optional function to reconnect Appium after crash
            tap_delay: Delay in seconds after tap (default 1.5)
        """
        self._driver = driver
        self._adb_shell = adb_shell_func
        self._reconnect = reconnect_func
        self._tap_delay = tap_delay
    
    @property
    def driver(self) -> webdriver.Remote:
        """Get the underlying Appium driver."""
        return self._driver
    
    def set_driver(self, driver: webdriver.Remote) -> None:
        """Update the Appium driver (e.g., after reconnection)."""
        self._driver = driver
    
    def _ensure_driver(self) -> None:
        """Ensure driver is connected, raise if not."""
        if not self._driver:
            raise AppiumUIControllerError("Appium driver not connected")
    
    def tap(self, x: int, y: int, delay: Optional[float] = None) -> None:
        """
        Tap at coordinates.
        
        Args:
            x: X coordinate
            y: Y coordinate
            delay: Optional custom delay after tap (uses tap_delay if not specified)
        """
        self._ensure_driver()
        self._driver.tap([(x, y)])
        time.sleep(delay if delay is not None else self._tap_delay)
    
    def swipe(
        self,
        x1: int, y1: int,
        x2: int, y2: int,
        duration_ms: int = 300
    ) -> None:
        """
        Swipe from one point to another.
        
        Args:
            x1, y1: Start coordinates
            x2, y2: End coordinates
            duration_ms: Swipe duration in milliseconds
        """
        self._ensure_driver()
        self._driver.swipe(x1, y1, x2, y2, duration_ms)
    
    def press_key(self, keycode: Union[int, str]) -> None:
        """
        Press an Android key.
        
        Args:
            keycode: Integer keycode or string like 'KEYCODE_BACK'
        """
        self._ensure_driver()
        if isinstance(keycode, str):
            keycode = self.KEYCODES.get(keycode, 4)  # Default to BACK
        self._driver.press_keycode(keycode)
    
    def type_text(self, text: str) -> bool:
        """
        Type text into the currently focused field.
        
        Args:
            text: Text to type (supports Unicode, emojis, newlines)
            
        Returns:
            True if text was sent successfully, False otherwise
        """
        self._ensure_driver()
        
        try:
            # Find EditText elements
            edit_texts = self._driver.find_elements(
                AppiumBy.CLASS_NAME, "android.widget.EditText"
            )
            
            for et in edit_texts:
                if et.is_displayed():
                    et.send_keys(text)
                    time.sleep(0.8)
                    return True
            
            # Fallback: try active element
            active = self._driver.switch_to.active_element
            if active:
                active.send_keys(text)
                time.sleep(0.8)
                return True
            
            return False
            
        except Exception as e:
            raise AppiumUIControllerError(f"Typing failed: {e}")
    
    def is_uiautomator2_crash(self, exception: Exception) -> bool:
        """Check if exception indicates UiAutomator2 crashed."""
        error_msg = str(exception).lower()
        crash_indicators = [
            'instrumentation process is not running',
            'uiautomator2 server',
            'cannot be proxied',
            'probably crashed',
        ]
        return any(indicator in error_msg for indicator in crash_indicators)
    
    def is_keyboard_visible(self) -> bool:
        """
        Check if the keyboard is currently visible.
        
        Requires adb_shell_func to be set.
        """
        if not self._adb_shell:
            return False  # Cannot determine without ADB
        
        # Method 1: Check dumpsys for keyboard visibility
        result = self._adb_shell("dumpsys input_method | grep mInputShown")
        if "mInputShown=true" in result:
            return True
        
        # Method 2: Check window visibility
        result = self._adb_shell("dumpsys window | grep -i keyboard")
        if "isVisible=true" in result.lower() or "mhasfocus=true" in result.lower():
            return True
        
        # Method 3: Check InputMethod window
        result = self._adb_shell("dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'")
        if "InputMethod" in result:
            return True
        
        return False
    
    def dump_ui(self) -> Tuple[List[Dict], str]:
        """
        Dump UI hierarchy and return parsed elements.
        
        Returns:
            Tuple of (elements_list, raw_xml_string)
            
        Raises:
            AppiumUIControllerError: If UI dump fails after recovery attempts
        """
        self._ensure_driver()
        
        elements = []
        xml_str = ""
        
        try:
            xml_str = self._driver.page_source
        except Exception as e:
            if self.is_uiautomator2_crash(e):
                # Try to recover
                if self._reconnect and self._reconnect():
                    try:
                        xml_str = self._driver.page_source
                    except Exception as e2:
                        raise UIAutomator2CrashError(
                            f"Recovery failed: {type(e2).__name__}: {e2}"
                        )
                else:
                    raise UIAutomator2CrashError("Appium reconnect failed")
            else:
                raise AppiumUIControllerError(
                    f"UI dump failed: {type(e).__name__}: {str(e)[:100]}"
                )
        
        if '<?xml' not in xml_str:
            return elements, xml_str
        
        xml_clean = xml_str[xml_str.find('<?xml'):]
        try:
            root = ET.fromstring(xml_clean)
            # Appium uses class names as tags, not <node>
            for elem in root.iter():
                text = elem.get('text', '')
                desc = elem.get('content-desc', '')
                res_id = elem.get('resource-id', '')
                bounds = elem.get('bounds', '')
                clickable = elem.get('clickable', 'false')
                
                if bounds and (text or desc or clickable == 'true'):
                    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if m:
                        x1, y1, x2, y2 = map(int, m.groups())
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        elements.append({
                            'text': text,
                            'desc': desc,
                            'id': res_id.split('/')[-1] if '/' in res_id else res_id,
                            'bounds': bounds,
                            'center': (cx, cy),
                            'clickable': clickable == 'true'
                        })
        except ET.ParseError as e:
            pass  # Return partial results
        
        return elements, xml_str
```

### 2. Update SmartInstagramPoster to Use AppiumUIController

After creating the controller, update `post_reel_smart.py`:

```python
from appium_ui_controller import AppiumUIController, AppiumUIControllerError

class SmartInstagramPoster:
    def __init__(self, phone_name, system_port=8200, appium_url=None):
        # ... existing init code ...
        self.ui_controller = None  # Will be set after Appium connects
    
    def connect_appium(self, retries=3):
        # ... existing connection code ...
        # After successful connection:
        self.ui_controller = AppiumUIController(
            driver=self.appium_driver,
            adb_shell_func=self.adb,
            reconnect_func=self._do_reconnect_appium,
            tap_delay=1.5
        )
    
    # Delegate methods to controller (thin wrappers for backward compatibility)
    def tap(self, x, y):
        print(f"  [TAP] ({x}, {y})")
        self.ui_controller.tap(x, y)
    
    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        self.ui_controller.swipe(x1, y1, x2, y2, duration_ms)
    
    def press_key(self, keycode):
        self.ui_controller.press_key(keycode)
    
    def type_text(self, text):
        print(f"    Typing via Appium ({len(text)} chars)...")
        result = self.ui_controller.type_text(text)
        if result:
            print("    Appium: text sent successfully")
        else:
            print("    ERROR: No text field found to type into")
        return result
    
    def dump_ui(self):
        return self.ui_controller.dump_ui()
    
    def is_keyboard_visible(self):
        return self.ui_controller.is_keyboard_visible()
```

### 3. Integration with Task 37 (DeviceConnectionManager)

The `AppiumUIController` should receive the driver from `DeviceConnectionManager`. When Task 37 is implemented:

```python
# In SmartInstagramPoster after Task 37 integration
connection_manager = DeviceConnectionManager(geelark_client)
device_info = connection_manager.connect(phone_name)

# Create UI controller with the Appium driver
self.ui_controller = AppiumUIController(
    driver=device_info.appium_driver,
    adb_shell_func=lambda cmd: connection_manager.adb_shell(cmd),
    reconnect_func=lambda: connection_manager.reconnect_appium()
)
```

### Key Design Decisions:

1. **Constructor Injection**: The Appium driver is injected via constructor, not created internally
2. **Optional ADB**: `adb_shell_func` is optional - keyboard detection gracefully degrades
3. **Optional Recovery**: `reconnect_func` callback allows crash recovery without tight coupling
4. **Backward Compatibility**: SmartInstagramPoster keeps thin wrapper methods for existing callers
5. **Clean Interface**: All Appium operations go through the controller
6. **Exception Hierarchy**: Custom exceptions for different failure modes

**Test Strategy:**

## Test Strategy

### 1. Unit Test - Module imports successfully
```bash
python -c "from appium_ui_controller import AppiumUIController, AppiumUIControllerError, UIAutomator2CrashError; print('Import OK')"
```

### 2. Unit Test - AppiumUIController instantiation
```bash
python -c "
from appium_ui_controller import AppiumUIController

# Create with mock driver
class MockDriver:
    def tap(self, coords): pass
    def swipe(self, *args): pass
    def press_keycode(self, code): pass
    def find_elements(self, by, value): return []
    @property
    def page_source(self): return '<hierarchy></hierarchy>'

controller = AppiumUIController(MockDriver())
print('Instantiation OK')
print(f'Driver set: {controller.driver is not None}')
"
```

### 3. Unit Test - tap() delegates correctly
```bash
python -c "
from appium_ui_controller import AppiumUIController

tap_calls = []

class MockDriver:
    def tap(self, coords):
        tap_calls.append(coords)

controller = AppiumUIController(MockDriver(), tap_delay=0)
controller.tap(100, 200)

assert tap_calls == [[(100, 200)]], f'Expected [[(100, 200)]], got {tap_calls}'
print('tap() delegation OK')
"
```

### 4. Unit Test - press_key() maps string keycodes
```bash
python -c "
from appium_ui_controller import AppiumUIController

pressed = []

class MockDriver:
    def press_keycode(self, code):
        pressed.append(code)

controller = AppiumUIController(MockDriver())
controller.press_key('KEYCODE_BACK')
controller.press_key('KEYCODE_HOME')
controller.press_key(66)  # Raw int

assert pressed == [4, 3, 66], f'Expected [4, 3, 66], got {pressed}'
print('press_key() mapping OK')
"
```

### 5. Unit Test - dump_ui() parses XML correctly
```bash
python -c "
from appium_ui_controller import AppiumUIController

class MockDriver:
    @property
    def page_source(self):
        return '''<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<hierarchy>
  <android.widget.Button text=\"OK\" bounds=\"[10,20][100,80]\" clickable=\"true\" resource-id=\"com.app/btn\" content-desc=\"Confirm\" />
</hierarchy>'''

controller = AppiumUIController(MockDriver())
elements, xml = controller.dump_ui()

assert len(elements) == 1, f'Expected 1 element, got {len(elements)}'
elem = elements[0]
assert elem['text'] == 'OK', f'Expected text=OK, got {elem[\"text\"]}'
assert elem['center'] == (55, 50), f'Expected center=(55,50), got {elem[\"center\"]}'
assert elem['clickable'] == True, f'Expected clickable=True'
print('dump_ui() parsing OK')
"
```

### 6. Unit Test - is_uiautomator2_crash() detection
```bash
python -c "
from appium_ui_controller import AppiumUIController

controller = AppiumUIController(None)

# Should detect crash
e1 = Exception('instrumentation process is not running')
assert controller.is_uiautomator2_crash(e1) == True

e2 = Exception('Original error: cannot be proxied')
assert controller.is_uiautomator2_crash(e2) == True

# Should not detect crash
e3 = Exception('Connection timeout')
assert controller.is_uiautomator2_crash(e3) == False

print('is_uiautomator2_crash() detection OK')
"
```

### 7. Unit Test - Error raised when no driver
```bash
python -c "
from appium_ui_controller import AppiumUIController, AppiumUIControllerError

controller = AppiumUIController(None)

try:
    controller.tap(100, 100)
    print('ERROR: Should have raised exception')
    exit(1)
except AppiumUIControllerError as e:
    assert 'not connected' in str(e).lower()
    print('No-driver error handling OK')
"
```

### 8. Integration Test - SmartInstagramPoster uses AppiumUIController
```bash
python -c "
from post_reel_smart import SmartInstagramPoster

poster = SmartInstagramPoster('test_phone')
# Before connect, ui_controller should be None
print(f'UI controller before connect: {getattr(poster, \"ui_controller\", \"NOT_ATTR\")}')
print('SmartInstagramPoster integration structure OK')
"
```

### 9. Integration Test - Full flow with mock Appium
```bash
python -c "
from appium_ui_controller import AppiumUIController

actions = []

class MockDriver:
    def tap(self, coords):
        actions.append(('tap', coords))
    def swipe(self, x1, y1, x2, y2, duration):
        actions.append(('swipe', x1, y1, x2, y2))
    def press_keycode(self, code):
        actions.append(('key', code))
    @property
    def page_source(self):
        return '<?xml version=\"1.0\"?><hierarchy><btn bounds=\"[0,0][100,100]\" clickable=\"true\"/></hierarchy>'

adb_calls = []
def mock_adb(cmd):
    adb_calls.append(cmd)
    return 'mInputShown=true' if 'input_method' in cmd else ''

controller = AppiumUIController(
    MockDriver(),
    adb_shell_func=mock_adb,
    tap_delay=0
)

# Run sequence
controller.tap(50, 50)
controller.swipe(0, 100, 0, 0, 300)
controller.press_key('KEYCODE_BACK')
elements, _ = controller.dump_ui()
kb_visible = controller.is_keyboard_visible()

assert len(actions) == 3, f'Expected 3 actions, got {actions}'
assert len(elements) == 1, f'Expected 1 element'
assert kb_visible == True, 'Expected keyboard visible'
print('Full flow integration OK')
"
```

### 10. Live Test - With real Appium server (manual)
```bash
# Start Appium server first: appium --port 4723

python -c "
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium_ui_controller import AppiumUIController

# Connect to a test device (update device address)
options = UiAutomator2Options()
options.platform_name = 'Android'
options.automation_name = 'UiAutomator2'
options.device_name = '192.168.1.100:5555'  # Update this
options.no_reset = True

try:
    driver = webdriver.Remote('http://127.0.0.1:4723', options=options)
    controller = AppiumUIController(driver)
    
    # Test dump_ui
    elements, xml = controller.dump_ui()
    print(f'Found {len(elements)} UI elements')
    
    # Test tap (tap center of screen)
    controller.tap(360, 640)
    print('Tap executed')
    
    driver.quit()
    print('Live test PASSED')
except Exception as e:
    print(f'Live test skipped or failed: {e}')
"
```
