"""Update type_text function to use clipboard method"""
import re

filepath = 'C:/Users/asus/Desktop/projects/geelark-automation/post_reel_smart.py'

# Read file
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# New type_text function with clipboard method
new_func = '''    def type_text(self, text):
        """Type text via clipboard + paste - supports full Unicode, emojis, newlines"""
        import base64

        # ClipboardHelper APK method (works on Android 10-15)
        # Encode text to base64 for safe transmission of Unicode/emojis/newlines
        text_b64 = base64.b64encode(text.encode('utf-8')).decode('ascii')

        # Set clipboard via our custom ClipboardHelper activity
        result = self.adb(f"am start -a com.geelark.clipboard.COPY --es base64 {text_b64}")
        print(f"    ClipboardHelper: {result[:80] if result else 'started'}")
        time.sleep(0.5)  # Give activity time to set clipboard

        # Paste from clipboard (Ctrl+V / KEYCODE_PASTE)
        self.adb("input keyevent 279")  # KEYCODE_PASTE
        time.sleep(0.3)

        # Verify paste worked
        verify_elements, _ = self.dump_ui()
        text_found = any(text[:20] in elem.get('text', '') for elem in verify_elements)

        if not text_found:
            print("    KEYCODE_PASTE failed, trying long-press paste...")
            # Long press to get paste menu
            self.adb("input swipe 360 400 360 400 1000")
            time.sleep(0.5)

            # Look for Paste button
            paste_elements, _ = self.dump_ui()
            paste_btn = [e for e in paste_elements if 'paste' in e.get('text', '').lower() or 'paste' in e.get('desc', '').lower()]
            if paste_btn:
                self.tap(paste_btn[0]['center'][0], paste_btn[0]['center'][1])
            else:
                # Fallback to ADBKeyboard
                print("    Trying ADBKeyboard fallback...")
                self.adb(f"am broadcast -a ADB_INPUT_B64 --es msg {text_b64}")

        return True

'''

# Find and replace type_text function using regex
pattern = r'(    def type_text\(self, text\):.*?)(    def dump_ui)'
content_new = re.sub(pattern, new_func + r'\2', content, flags=re.DOTALL)

# Write back
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content_new)

print('Updated type_text function successfully!')
