"""
Appium UI Controller - encapsulates all Appium-based UI interactions.

This module provides a clean interface for interacting with Android
UI elements through Appium WebDriver.

Extracted from SmartInstagramPoster to improve separation of concerns.
"""
import re
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple, Optional, Any

from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy


class AppiumUIController:
    """Controls Android UI through Appium WebDriver."""

    def __init__(self, driver: webdriver.Remote):
        """
        Initialize the controller.

        Args:
            driver: Appium WebDriver instance (must already be connected).
        """
        self._driver = driver

    @property
    def driver(self) -> webdriver.Remote:
        """Get the underlying Appium driver."""
        return self._driver

    def tap(self, x: int, y: int, delay: float = 1.5) -> None:
        """Tap at coordinates.

        Args:
            x: X coordinate.
            y: Y coordinate.
            delay: Delay after tap in seconds.
        """
        print(f"  [TAP] ({x}, {y})")
        if not self._driver:
            raise Exception("Appium driver not connected - cannot tap")
        self._driver.tap([(x, y)])
        time.sleep(delay)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        """Swipe from one point to another.

        Args:
            x1: Start X coordinate.
            y1: Start Y coordinate.
            x2: End X coordinate.
            y2: End Y coordinate.
            duration_ms: Duration of swipe in milliseconds.
        """
        if not self._driver:
            raise Exception("Appium driver not connected - cannot swipe")
        self._driver.swipe(x1, y1, x2, y2, duration_ms)

    def press_key(self, keycode) -> None:
        """Press a key.

        Args:
            keycode: Key code (int) or string like 'KEYCODE_BACK'.
        """
        if not self._driver:
            raise Exception("Appium driver not connected - cannot press key")

        key_map = {
            'KEYCODE_BACK': 4,
            'KEYCODE_HOME': 3,
            'KEYCODE_ENTER': 66,
        }

        if isinstance(keycode, str):
            keycode = key_map.get(keycode, 4)  # Default to BACK

        self._driver.press_keycode(keycode)

    def type_text(self, text: str) -> bool:
        """Type text into the currently focused field.

        Args:
            text: Text to type (supports Unicode/emojis).

        Returns:
            True if text was typed successfully.
        """
        if not self._driver:
            print("    ERROR: Appium driver not connected!")
            return False

        print(f"    Typing via Appium ({len(text)} chars)...")
        try:
            # Find the currently focused EditText element
            edit_texts = self._driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
            if edit_texts:
                for et in edit_texts:
                    if et.is_displayed():
                        et.send_keys(text)
                        print("    Appium: text sent successfully")
                        time.sleep(0.8)
                        return True

            # Fallback: try to type using the active element
            active = self._driver.switch_to.active_element
            if active:
                active.send_keys(text)
                print("    Appium: text sent to active element")
                time.sleep(0.8)
                return True

            print("    ERROR: No text field found to type into")
            return False

        except Exception as e:
            print(f"    Appium typing error: {e}")
            return False

    def dump_ui(self) -> Tuple[List[Dict], str]:
        """Dump UI hierarchy and return parsed elements.

        Returns:
            Tuple of (elements list, raw XML string).
            Elements have: text, desc, id, bounds, center, clickable.

        Raises:
            Exception: If driver not connected or dump fails.
        """
        elements = []
        xml_str = ""

        if not self._driver:
            raise Exception("Appium driver not connected - cannot dump UI")

        xml_str = self._driver.page_source

        if '<?xml' not in xml_str:
            return elements, xml_str

        xml_clean = xml_str[xml_str.find('<?xml'):]
        try:
            root = ET.fromstring(xml_clean)
            # Appium uses class names as tags, iterate over ALL elements
            for elem in root.iter():
                text = elem.get('text', '')
                desc = elem.get('content-desc', '')
                res_id = elem.get('resource-id', '')
                bounds = elem.get('bounds', '')
                clickable = elem.get('clickable', 'false')

                if bounds and (text or desc or clickable == 'true'):
                    # Parse bounds [x1,y1][x2,y2]
                    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if m:
                        x1, y1, x2, y2 = map(int, m.groups())
                        cx, cy = (x1+x2)//2, (y1+y2)//2
                        elements.append({
                            'text': text,
                            'desc': desc,
                            'id': res_id.split('/')[-1] if '/' in res_id else res_id,
                            'bounds': bounds,
                            'center': (cx, cy),
                            'clickable': clickable == 'true'
                        })
        except ET.ParseError as e:
            print(f"  XML parse error: {e}")

        return elements, xml_str

    def is_keyboard_visible(self, adb_shell_func=None) -> bool:
        """Check if the keyboard is currently visible.

        Args:
            adb_shell_func: Optional function to run ADB shell commands.
                           If not provided, returns False.

        Returns:
            True if keyboard is visible.
        """
        if not adb_shell_func:
            return False

        # Method 1: Check dumpsys for keyboard visibility
        result = adb_shell_func("dumpsys input_method | grep mInputShown")
        if "mInputShown=true" in result:
            return True

        # Method 2: Check window visibility
        result = adb_shell_func("dumpsys window | grep -i keyboard")
        if "isVisible=true" in result.lower() or "mhasfocus=true" in result.lower():
            return True

        # Method 3: Check if InputMethod window is visible
        result = adb_shell_func("dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'")
        if "InputMethod" in result:
            return True

        return False

    def save_screenshot(self, filepath: str) -> bool:
        """Save a screenshot to file.

        Args:
            filepath: Path to save screenshot.

        Returns:
            True if screenshot was saved.
        """
        try:
            if self._driver:
                self._driver.save_screenshot(filepath)
                return True
        except Exception as e:
            print(f"    Failed to save screenshot: {e}")
        return False

    def scroll_down(self) -> None:
        """Scroll down on the screen."""
        self.swipe(360, 900, 360, 400, 300)

    def scroll_up(self) -> None:
        """Scroll up on the screen."""
        self.swipe(360, 400, 360, 900, 300)

    def go_back(self) -> None:
        """Press the back button."""
        self.press_key('KEYCODE_BACK')

    def go_home(self) -> None:
        """Press the home button."""
        self.press_key('KEYCODE_HOME')
