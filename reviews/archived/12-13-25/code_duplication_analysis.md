# Code Duplication Analysis Report
## Geelark Instagram Automation Codebase

**Analysis Date:** December 13, 2025  
**Total Files Analyzed:** 40+ Python files  
**Severity Assessment:** HIGH - Significant duplication affecting maintainability

---

## Executive Summary

The codebase exhibits substantial code duplication across several key areas, particularly in:
1. ADB utility functions (6+ files)
2. Phone connection/setup logic (5+ files)
3. Backup files that are near-copies of main files (4 files)
4. Windows console encoding fixes (3+ files)
5. UI element parsing logic (2+ files)

**Estimated duplicated code:** ~500-700 lines of code (approximately 10-15% of core logic)

---

## Detailed Duplication Analysis

### 1. ADB Shell Command Execution Function

**Files:**
- `setup_adbkeyboard.py` (lines 18-24)
- `setup_adbkeyboard.backup.py` (lines 18-24)
- `setup_clipboard_helper.py` (lines 21-27)
- `setup_clipboard_helper.backup.py` (lines 21-27)
- `test_typing.py` (lines 26-32)
- `post_reel_smart.py` (lines 57-64)

**Length:** ~7 lines per occurrence × 6 files = **42 lines duplicated**

**Duplicated Code:**
```python
def adb(device, cmd, timeout=30):
    """Run ADB shell command"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "shell", cmd],
        capture_output=True, timeout=timeout,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""
```

**Impact:** HIGH
- Changes to ADB command handling require updates in 6 separate files
- Risk of inconsistent error handling across files
- Different timeout defaults could cause confusion

**Suggestions:**
- Extract into a shared `adb_utils.py` module
- Create an `AdbController` class with proper error handling
- Add logging and retry logic in one place

---

### 2. ADB APK Installation Function

**Files:**
- `setup_adbkeyboard.py` (lines 27-33)
- `setup_adbkeyboard.backup.py` (lines 27-33)
- `setup_clipboard_helper.py` (lines 30-36)
- `setup_clipboard_helper.backup.py` (lines 30-36)

**Length:** ~7 lines per occurrence × 4 files = **28 lines duplicated**

**Duplicated Code:**
```python
def adb_install(device, apk_path):
    """Install APK via ADB"""
    result = subprocess.run(
        [ADB_PATH, "-s", device, "install", "-r", apk_path],
        capture_output=True, timeout=120,
        encoding='utf-8', errors='replace'
    )
    return result.stdout.strip() if result.stdout else ""
```

**Impact:** MEDIUM
- Installation logic duplicated across setup scripts
- No unified retry mechanism for failed installs

**Suggestions:**
- Move to shared `adb_utils.py` alongside `adb()` function
- Add installation verification and retry logic
- Create a unified `install_apk()` helper

---

### 3. Phone Connection and Setup Logic

**Files:**
- `setup_adbkeyboard.py` - `setup_phone()` (lines 36-106)
- `setup_adbkeyboard.backup.py` - `setup_phone()` (lines 36-99)
- `setup_clipboard_helper.py` - `setup_phone()` (lines 39-120)
- `setup_clipboard_helper.backup.py` - `setup_phone()` (lines 39-107)
- `test_typing.py` - `connect_phone()` (lines 34-78)

**Length:** ~70 lines per occurrence × 5 files = **350 lines duplicated**

**Core Pattern (repeated in each file):**
```python
def setup_phone(phone_name):
    client = GeelarkClient()
    
    # Find phone (identical loop in all files)
    phone = None
    for page in range(1, 10):
        result = client.list_phones(page=page, page_size=100)
        for p in result["items"]:
            if p["serialName"] == phone_name:
                phone = p
                break
        if phone:
            break
    
    # Start phone if needed (identical in all files)
    if phone["status"] != 0:
        client.start_phone(phone_id)
        for i in range(60):
            time.sleep(2)
            status = client.get_phone_status([phone_id])
            # ... wait logic
    
    # Enable ADB (identical in all files)
    client.enable_adb(phone_id)
    
    # Get ADB info and connect (identical in all files)
    adb_info = client.get_adb_info(phone_id)
    device = f"{adb_info['ip']}:{adb_info['port']}"
    # ... connect logic
```

**Impact:** CRITICAL
- This is the most severe duplication in the codebase
- Any bug fix or improvement must be applied to 5+ files
- High risk of divergence between files
- Phone status waiting logic has subtle differences across files

**Suggestions:**
- Create `phone_manager.py` with a `PhoneManager` class:
  ```python
  class PhoneManager:
      def __init__(self, client: GeelarkClient = None):
          self.client = client or GeelarkClient()
      
      def find_phone(self, phone_name: str) -> dict:
          """Find phone by name across pages"""
          
      def ensure_running(self, phone_id: str, timeout: int = 120) -> bool:
          """Start phone and wait until ready"""
          
      def connect_adb(self, phone_id: str) -> str:
          """Enable ADB and return device string"""
          
      def setup_phone(self, phone_name: str) -> tuple[str, str]:
          """Full setup: find, start, connect. Returns (device, phone_id)"""
  ```
- All setup scripts should use `PhoneManager`
- Add context manager support for automatic cleanup

---

### 4. Backup Files (Near-Complete Duplication)

**Files:**
- `setup_adbkeyboard.py` ↔ `setup_adbkeyboard.backup.py` (~98% identical)
- `setup_clipboard_helper.py` ↔ `setup_clipboard_helper.backup.py` (~95% identical)

**Length:** ~160 lines × 2 pairs = **320 lines of redundant backup code**

**Impact:** HIGH
- Backup files are maintained in the repository
- Creates confusion about which file is canonical
- Git history should serve as backup, not duplicate files
- Risk of editing wrong file

**Suggestions:**
- **Delete backup files immediately** - use git for version history
- If specific versions are needed, use git tags or branches
- Add to `.gitignore` to prevent future backup files: `*.backup.py`

---

### 5. Windows Console Encoding Fix

**Files:**
- `post_reel_smart.py` (lines 10-15)
- `batch_post_ARCHIVED.py` (lines 5-7)
- `test_typing.py` (lines 14-16)

**Length:** ~5 lines per occurrence × 3+ files = **15+ lines duplicated**

**Duplicated Code:**
```python
if sys.platform == 'win32':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
```

**Impact:** MEDIUM
- Must be copied into every new script that handles Unicode
- Easy to forget in new files

**Suggestions:**
- Create `utils.py` with:
  ```python
  def configure_windows_console():
      """Fix Windows console for Unicode/emoji support"""
      if sys.platform == 'win32':
          if hasattr(sys.stdout, 'reconfigure'):
              sys.stdout.reconfigure(encoding='utf-8', errors='replace')
          if hasattr(sys.stderr, 'reconfigure'):
              sys.stderr.reconfigure(encoding='utf-8', errors='replace')
  ```
- Call at the start of each script: `configure_windows_console()`
- Or auto-configure in a package `__init__.py`

---

### 6. UI Element Dump/Parsing Logic

**Files:**
- `post_reel_smart.py` - `dump_ui()` method
- `test_full_flow_android15.py` - `dump_ui()` function

**Length:** ~40 lines per occurrence × 2 files = **80 lines duplicated**

**Core Pattern:**
```python
def dump_ui(driver):
    """Parse page_source into elements"""
    elements = []
    xml_str = driver.page_source
    
    xml_clean = xml_str[xml_str.find('<?xml'):]
    root = ET.fromstring(xml_clean)
    
    for elem in root.iter():
        text = elem.get('text', '')
        desc = elem.get('content-desc', '')
        bounds = elem.get('bounds', '')
        clickable = elem.get('clickable', 'false')
        
        if bounds and (text or desc or clickable == 'true'):
            m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
            if m:
                x1, y1, x2, y2 = map(int, m.groups())
                cx, cy = (x1+x2)//2, (y1+y2)//2
                elements.append({
                    'text': text,
                    'desc': desc,
                    'center': (cx, cy),
                    'clickable': clickable == 'true'
                })
    return elements
```

**Impact:** MEDIUM
- UI parsing logic must be kept in sync
- Bug fixes need to be applied in multiple places

**Suggestions:**
- Extract into `ui_parser.py`:
  ```python
  class UiElement:
      text: str
      desc: str
      bounds: str
      center: tuple[int, int]
      clickable: bool
      
  def parse_ui_hierarchy(xml_source: str) -> list[UiElement]:
      """Parse Android UI hierarchy XML into element list"""
  ```
- Use in both `SmartInstagramPoster` class and test files

---

### 7. Main Function CLI Pattern

**Files:**
- `setup_adbkeyboard.py` - `main()`
- `setup_clipboard_helper.py` - `main()`
- `test_typing.py` - `main()`

**Length:** ~25 lines per occurrence × 3 files = **75 lines duplicated**

**Pattern:**
```python
def main():
    if len(sys.argv) < 2:
        print("Usage: python script.py <phone1> <phone2> ...")
        sys.exit(1)
    
    phones = sys.argv[1:]
    results = {}
    
    for phone in phones:
        try:
            results[phone] = setup_phone(phone)
        except Exception as e:
            results[phone] = False
    
    # Summary
    print("\n" + "="*50)
    print("SETUP COMPLETE")
    print("="*50)
    for phone, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"  {phone}: {status}")
```

**Impact:** LOW-MEDIUM
- Boilerplate that's easy to copy but creates maintenance overhead

**Suggestions:**
- Create a `cli_utils.py` with common CLI patterns:
  ```python
  def run_for_phones(setup_func, script_name: str):
      """Run a setup function for all phones specified on CLI"""
  ```

---

### 8. ADB Path Constant Duplication

**Files:** 6+ files define the same constant

```python
ADB_PATH = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
```

**Impact:** HIGH
- Hardcoded path must be changed in multiple files
- Path is user-specific, not portable
- Should be configurable via environment variable

**Suggestions:**
- Move to `config.py`:
  ```python
  import os
  ADB_PATH = os.getenv('ADB_PATH', r'C:\Users\asus\Downloads\...\adb.exe')
  ```
- Or use `.env` file with `python-dotenv`
- All files import from config: `from config import ADB_PATH`

---

## Patterns and Trends

### Duplication Hotspots

1. **Setup Scripts** - The setup scripts (`setup_adbkeyboard.py`, `setup_clipboard_helper.py`) share 80%+ of their code
2. **Test Scripts** - Test files copy helper functions instead of importing
3. **Backup Files** - Manual backup strategy instead of using git

### Root Causes

1. **No shared utilities module** - Each file is standalone
2. **Copy-paste development** - New scripts copy from existing ones
3. **Backup files in repo** - Version control anti-pattern
4. **Hardcoded constants** - Configuration not centralized

---

## Refactoring Recommendations

### Priority 1: Critical (Do Immediately)

1. **Delete backup files**
   - Remove `setup_adbkeyboard.backup.py`
   - Remove `setup_clipboard_helper.backup.py`
   - Add `*.backup.py` to `.gitignore`
   - Estimated savings: 320 lines

2. **Create `phone_manager.py`**
   - Centralize all phone connection logic
   - Estimated savings: 300+ lines
   - Prevents future duplication

### Priority 2: High (This Sprint)

3. **Create `adb_utils.py`**
   - Move `adb()`, `adb_install()` functions
   - Add proper error handling and logging
   - Estimated savings: 70 lines

4. **Create `config.py`**
   - Centralize `ADB_PATH`, `APPIUM_SERVER`, etc.
   - Use environment variables
   - Estimated savings: 20+ lines, improved portability

### Priority 3: Medium (Next Sprint)

5. **Create `utils.py`**
   - Windows console encoding fix
   - Common CLI patterns
   - Estimated savings: 50+ lines

6. **Create `ui_parser.py`**
   - Extract UI parsing logic
   - Estimated savings: 80 lines

### Priority 4: Low (Backlog)

7. **Consolidate setup scripts**
   - Create generic `setup_apk.py` that takes APK path as argument
   - Or create unified `phone_setup.py` CLI tool

---

## Proposed Package Structure

```
geelark_automation/
├── __init__.py
├── config.py              # Centralized configuration
├── utils.py               # Common utilities
├── adb_utils.py           # ADB command helpers
├── phone_manager.py       # Phone connection/management
├── ui_parser.py           # UI hierarchy parsing
├── geelark_client.py      # API client (existing)
├── posting/
│   ├── __init__.py
│   ├── poster.py          # SmartInstagramPoster
│   └── scheduler.py       # PostingScheduler
├── setup/
│   ├── __init__.py
│   ├── adbkeyboard.py
│   └── clipboard_helper.py
└── tests/
    ├── __init__.py
    └── test_*.py
```

---

## Metrics Summary

| Category | Files Affected | Lines Duplicated | Priority |
|----------|---------------|------------------|----------|
| Phone Setup Logic | 5 | ~350 | CRITICAL |
| Backup Files | 4 | ~320 | CRITICAL |
| ADB Functions | 6 | ~70 | HIGH |
| UI Parsing | 2 | ~80 | MEDIUM |
| Console Fix | 3 | ~15 | MEDIUM |
| CLI Patterns | 3 | ~75 | LOW |
| Constants | 6+ | ~12 | HIGH |
| **Total** | **-** | **~900+** | **-** |

---

## Tools for Prevention

1. **Pre-commit hooks** - Use `flake8` with `--max-complexity` and custom rules
2. **Code review checklist** - "Is this logic duplicated elsewhere?"
3. **IDE support** - PyCharm/VSCode detect duplicates
4. **CI/CD** - Add `pylint` similarity checker: `pylint --enable=similarities`
5. **Documentation** - Create CONTRIBUTING.md with DRY guidelines

---

## Conclusion

The codebase has significant code duplication that increases maintenance burden and bug risk. The most critical issues are:

1. **Backup files** should be deleted immediately (320 lines)
2. **Phone setup logic** needs extraction into a shared module (350 lines)
3. **ADB utilities** should be centralized (70 lines)

Implementing the Priority 1 and 2 recommendations would eliminate approximately 700+ lines of duplicated code and significantly improve maintainability.

**Recommended Next Steps:**
1. Create a tracking issue for each Priority 1 and 2 item
2. Allocate 2-3 days for refactoring work
3. Update tests to verify refactored code works
4. Add linting rules to prevent future duplication
