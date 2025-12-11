# Geelark Instagram Automation

Automated Instagram Reel posting to Geelark cloud phones using AI-driven UI navigation.

## Core Concept

The automation follows a simple, reliable loop:

```
1. UI dump (uiautomator dump)
2. Send elements to Claude
3. Claude decides what to tap
4. Execute tap
5. Repeat until done
```

**Every single step uses this loop. No exceptions. No hardcoded coordinates. No skipping steps.**

## How It Works

### The Loop (post_reel_smart.py)

```python
for step in range(max_steps):
    # 1. Dump UI
    elements = dump_ui()

    # 2. Ask Claude what to do
    action = analyze_ui(elements, caption)

    # 3. Execute action
    if action['action'] == 'tap':
        tap(elements[action['element_index']]['center'])
    elif action['action'] == 'tap_and_type':
        tap(element)
        type_text(caption)
    elif action['action'] == 'back':
        press_back()
    elif action['action'] == 'done':
        return True
```

### Claude's Job

Claude receives:
- List of all UI elements with bounds, text, descriptions
- Current state (video uploaded? caption entered?)
- The caption to post

Claude returns:
- Which element to tap (by index)
- Or special actions: back, scroll, done
- Never gives up - if something unexpected appears, press back and continue

### Error Recovery

If unexpected screens appear (Play Store, popups, wrong app):
1. Press back button
2. If that doesn't work, press home button
3. Reopen Instagram
4. Continue the loop

**The AI should NEVER return "error" and give up.** It should always try to recover.

## Files

### Core Scripts

| File | Purpose |
|------|---------|
| `post_reel_smart.py` | Main posting script - THE WORKING ONE |
| `geelark_client.py` | Geelark API wrapper (phones, ADB, uploads) |

### Batch Scripts (use post_reel_smart.py internally)

| File | Purpose |
|------|---------|
| `batch_post.py` | Sequential posting to multiple phones |
| `batch_post_concurrent.py` | Parallel posting with ThreadPoolExecutor |

## Usage

### Single Post

```bash
python post_reel_smart.py <phone_name> <video_path> "<caption>"
```

Example:
```bash
python post_reel_smart.py miccliparchive video.mp4 "Check out this clip!"
```

### Batch Post

```bash
python batch_post.py <chunk_folder> <phone1> <phone2> ... [--limit N]
```

Example:
```bash
python batch_post.py va_chunk_05 miccliparchive reelwisdompod_ podmindstudio --limit 3
```

## Setup

### Requirements

1. Python 3.8+
2. ADB (Android Debug Bridge)
3. Anthropic API key
4. Geelark account with API access

### Environment Variables (.env)

```
GEELARK_APP_ID=your_app_id
GEELARK_API_KEY=your_api_key
GEELARK_TOKEN=your_token
ANTHROPIC_API_KEY=your_anthropic_key
```

### ADB Path

Edit `ADB_PATH` in `post_reel_smart.py`:
```python
ADB_PATH = r"C:\path\to\adb.exe"
```

## Instagram Posting Flow

The AI navigates through these screens:

1. **Home Feed** - Tap Create/+ button (bottom nav or top left "Create New")
2. **Post Type Selection** - Tap "REEL" option
3. **Gallery** - Select the uploaded video thumbnail
4. **Video Preview** - Tap "Next"
5. **Edit Screen** - Tap "Next" (skip editing)
6. **Caption Screen** - Tap caption field, type caption, hide keyboard
7. **Share** - Tap "Share" button
8. **Confirmation** - See "Sharing to Reels" or return to feed = done

## Geelark API Flow

1. **Find phone** by name via `/open/v1/phone/list`
2. **Start phone** if not running via `/open/v1/phone/start`
3. **Enable ADB** via `/open/v1/adb/setStatus`
4. **Get ADB info** (ip, port, password) via `/open/v1/adb/getData`
5. **Connect ADB** with `adb connect ip:port` then `glogin password`
6. **Upload video** to Geelark cloud, then to phone's Downloads folder
7. **Run posting loop** (UI dump + Claude + tap)
8. **Cleanup** - delete video, disable ADB

## Key Technical Details

### UI Dump

```bash
adb shell uiautomator dump /sdcard/ui.xml
adb shell cat /sdcard/ui.xml
```

Returns XML with all UI elements including:
- `text` - visible text
- `content-desc` - accessibility description
- `bounds` - [x1,y1][x2,y2] coordinates
- `clickable` - whether element is tappable

### Text Input

Uses ADBKeyboard with base64 encoding for special characters:
```python
text_b64 = base64.b64encode(text.encode('utf-8')).decode('ascii')
adb shell am broadcast -a ADB_INPUT_B64 --es msg {text_b64}
```

### Geelark ADB Authentication

Geelark cloud phones require special login after ADB connect:
```bash
adb shell glogin {password}
```

## Chunk Folder Structure

For batch posting, organize videos in folders:

```
va_chunk_05/
  chunk_05.csv          # Shortcode,Text columns
  ABC123-1.mp4          # Video file (shortcode + "-1.mp4")
  DEF456-1.mp4
  ...
```

CSV format:
```csv
Shortcode,Text
ABC123,"Caption for first video"
DEF456,"Caption for second video"
```

## Troubleshooting

### "Phone not found"
- Check phone name matches exactly (case-sensitive)
- Phone might be on a different page - script searches up to 10 pages

### "Upload timeout"
- Check Geelark dashboard for phone status
- Phone might be offline or slow
- Increase timeout in `wait_for_upload()`

### "Unexpected screen" (Play Store, etc.)
- AI should press back and recover
- If it keeps happening, phone might have popups that need manual dismissal

### "Caption not typed"
- ADBKeyboard might not be installed
- Check if keyboard is set as default input method on the phone

### Unicode/Emoji errors on Windows
- Scripts include UTF-8 encoding fix at top
- Make sure it runs BEFORE any other imports
