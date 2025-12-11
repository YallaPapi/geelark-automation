# Claude Code Instructions

## Task Master AI Instructions

**Import Task Master's development workflow commands and guidelines, treat as if import is in the main CLAUDE.md file.**
@./.taskmaster/CLAUDE.md

Always use taskmaster to research the best solution any time I ask you to do something. Do not use web search. Use taskmaster.

---

## Project Overview

This project automates Instagram Reel posting to Geelark cloud phones. It uses:
- **Geelark API** for phone management (start/stop, ADB enable, file upload)
- **Appium + UIAutomator2** for Android UI automation (tapping, typing, navigation)
- **Claude AI** for intelligent UI analysis and decision-making

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   batch_post.py │────▶│post_reel_smart.py│────▶│  Geelark API    │
│ (orchestrator)  │     │ (single phone)  │     │ (cloud phones)  │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
            ┌───────────────┐         ┌───────────────┐
            │ Appium Server │         │  Claude API   │
            │ (UI control)  │         │ (UI analysis) │
            └───────────────┘         └───────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `post_reel_smart.py` | Core posting logic - connects to phone, uploads video, navigates Instagram |
| `batch_post.py` | Posts multiple videos across multiple phones in round-robin fashion |
| `batch_post_concurrent.py` | Parallel version using multiple Appium ports |
| `geelark_client.py` | Geelark API wrapper |

## Setup Requirements

### 1. Appium Server (REQUIRED for Android 15+)

```bash
# Install
npm install -g appium
appium driver install uiautomator2

# Run (must be running before posting)
appium --address 127.0.0.1 --port 4723
```

### 2. Environment Variables

```bash
# Required in .env
GEELARK_ACCESS_KEY=your_access_key
GEELARK_ACCESS_SECRET=your_access_secret
ANTHROPIC_API_KEY=your_claude_key

# Set in code (post_reel_smart.py)
ANDROID_HOME=C:\Users\asus\Downloads\android-sdk
```

### 3. ADB Platform Tools

Path: `C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe`

## Appium Integration (Android 15 Fix)

The original ADBKeyboard approach broke on Android 15. We migrated to Appium for all UI operations:

### Key Changes Made (Dec 2024)

1. **`dump_ui()`** - Uses `driver.page_source` instead of `adb uiautomator dump`
   - CRITICAL: Uses `root.iter()` not `iter('node')` - Appium uses class names as XML tags

2. **`tap(x, y)`** - Uses `driver.tap([(x, y)])` instead of `adb input tap`

3. **`swipe()`** - Uses `driver.swipe()` instead of `adb input swipe`

4. **`press_key()`** - Uses `driver.press_keycode()` instead of `adb input keyevent`

5. **`type_text()`** - Uses Appium's `send_keys()` - supports Unicode/emojis on all Android versions

### Why Appium?

| Feature | ADBKeyboard | Appium |
|---------|-------------|--------|
| Android 15 support | No | Yes |
| Unicode/emoji | Buggy | Native |
| UI inspection | Conflicts with Appium | Unified |
| Reliability | Flaky | Stable |

## Usage

### Single Phone Post
```bash
python post_reel_smart.py <phone_name> <video_path> <caption>

# Example
python post_reel_smart.py reelwisdompod_ video.mp4 "Check this out! 🎬"
```

### Batch Posting
```bash
python batch_post.py <chunk_folder> <phone1> <phone2> ... [--limit N]

# Example
python batch_post.py chunk_01c reelwisdompod_ podmindstudio --limit 3
```

## Chunk Data Format

```
chunk_01c/
├── chunk_01c_cleaned.csv    # Caption + video shortcode mapping
├── 2bears.1cave/            # Video folder by source
│   ├── DM6m1Econ4x-2.mp4
│   └── DMbMMftoiDC-2.mp4
├── alexjones.tv/
└── ...
```

CSV columns: `Text, Image/Video link 1 (shortcode)`

## Troubleshooting

### "No UI elements found"
- Ensure Appium server is running: `curl http://127.0.0.1:4723/status`
- Check `dump_ui()` uses `root.iter()` not `root.iter('node')`

### "Device offline" in Appium
- Re-run `adb connect <ip:port>` then `adb -s <device> shell glogin <password>`
- Restart Appium server

### Caption not typed
- Verify `caption_entered` flag is only set AFTER actual typing (not from Claude's analysis)

## Testing

```bash
# Quick connectivity test
python test_full_flow_android15.py

# Full posting test
python post_reel_smart.py reelwisdompod_ video.mp4 "Test caption"
```
