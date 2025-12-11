# Geelark Instagram Automation - Context Document

Use this to catch Claude up to speed on the project.

## Project Overview

Automated Instagram Reel posting to Geelark cloud phones using AI-driven UI navigation. The key innovation is using Claude AI to analyze UI hierarchy (via `uiautomator dump`) and decide what to tap at each step - no hardcoded coordinates.

## How It Works

1. Connect to Geelark cloud phone via their API
2. Enable ADB on the phone
3. Upload video to Geelark cloud → transfer to phone's Downloads folder
4. Open Instagram app
5. AI-driven navigation loop:
   - Dump UI elements via `uiautomator dump`
   - Send elements to Claude AI with current state
   - Claude decides next action (tap, type, back, scroll, done)
   - Execute action via ADB
   - Repeat until post is complete
6. Cleanup (delete video, disable ADB)

## Key Files

| File | Purpose |
|------|---------|
| `post_reel_smart.py` | Core posting logic with AI navigation - THE MAIN SCRIPT |
| `batch_post.py` | Sequential batch posting to multiple phones |
| `batch_post_concurrent.py` | Parallel batch posting with ThreadPoolExecutor |
| `geelark_client.py` | Geelark API wrapper (phones, ADB, uploads) |
| `post_gui.py` | Simple tkinter GUI for monitoring posts |

## Current CSV Format (chunk_01a)

Location: `chunk_01a/chunk_01a.csv`

| Column | Content |
|--------|---------|
| `Text` | Caption with hashtags, emojis, newlines |
| `Shortcode` | Full file path (needs `spoofed` replaced with `chunk_01a`) |

Videos are in subfolders: `chunk_01a/2bears.1cave/`, `chunk_01a/hubermanlab/`, etc.

**To load posts from this CSV:**
```python
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        video_path = row.get('Shortcode', '').replace('spoofed', 'chunk_01a')
        caption = row.get('Text', '').strip()
```

## Available Phones/Accounts

**Working (tested):**
- podmindstudio
- reelwisdompod_
- talktrackhub

**New (untested but available):**
- FusedMercurySpike
- DarkLichenCoded
- choice.jonestown
- chance_of_rain_tomorrow
- BrokenRockPace
- apexstratagem
- clipsonpodcast
- talkwisdomcut

**Broken (DO NOT USE):**
- miccliparchive (CAPTCHA issues)

## Text Input Method

Uses ADBKeyboard APK with base64 broadcast - simple and reliable:
```python
def type_text(self, text):
    import base64
    text_b64 = base64.b64encode(text.encode('utf-8')).decode('ascii')
    self.adb(f"am broadcast -a ADB_INPUT_B64 --es msg {text_b64}")
```

**DO NOT** use clipboard/paste method - it was causing issues. Direct ADBKeyboard typing works.

## Critical AI Prompt Rules (in post_reel_smart.py)

After typing caption, the AI MUST:
1. Tap "OK" button in top right corner to dismiss caption editor
2. THEN tap "Share" button

The Share button won't work while caption field is still active/focused.

## Known Issues & Fixes Applied

### Issue 1: Caption not typing
**Cause:** Old code used clipboard + paste which didn't work in Instagram
**Fix:** Changed `type_text()` to use ADBKeyboard broadcast directly

### Issue 2: Share button not working after caption
**Cause:** Need to tap OK button first to dismiss caption editor
**Fix:** Updated AI prompt to tap OK before Share

### Issue 3: Upload timeout on larger files
**Cause:** Geelark cloud-to-phone transfer is slow (not your upload speed)
**Status:** Need to investigate further - may need longer timeout or retry logic

## Environment Setup

Required in `.env`:
```
GEELARK_APP_ID=your_app_id
GEELARK_API_KEY=your_api_key
GEELARK_TOKEN=your_token
ANTHROPIC_API_KEY=your_anthropic_key
```

ADB path (hardcoded in scripts):
```python
ADB_PATH = r"C:\Users\asus\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
```

## Running Single Post

```bash
python post_reel_smart.py <phone_name> <video_path> "<caption>"
```

Example:
```bash
python post_reel_smart.py podmindstudio "chunk_01a/2bears.1cave/ABC123.mp4" "Caption here #hashtags"
```

## Running Batch Post

Current `batch_post.py` needs to be updated to handle the new CSV format. Once updated:

```bash
python batch_post.py chunk_01a phone1 phone2 phone3 --limit 6
```

## GUI

```bash
python post_gui.py
```

Current GUI is single-post only. Needs upgrade for batch mode with:
- Multi-phone selection
- Batch progress tracking
- Results table

## Logging Strategy (To Implement)

**Results CSV** (after every post):
```csv
timestamp,phone,video,status,error,duration_sec,steps
```

**Detailed log file** with phone prefix:
```
[podmindstudio] --- Step 1 ---
[podmindstudio] Action: tap Create button
```

## Testing Priority

1. Test across different Android versions/devices (phones are randomly configured)
2. Round-robin distribution across phones
3. Sequential first, then concurrent once stable
4. Log all failures to identify patterns

## Project Structure

```
geelark-automation/
├── post_reel_smart.py      # Main posting script
├── batch_post.py           # Sequential batch posting
├── batch_post_concurrent.py # Parallel batch posting
├── geelark_client.py       # Geelark API wrapper
├── post_gui.py             # GUI monitor
├── chunk_01a/              # Videos and CSV
│   ├── chunk_01a.csv       # Captions and video paths
│   ├── 2bears.1cave/       # Videos from this source
│   ├── hubermanlab/        # Videos from this source
│   └── ...
├── .taskmaster/            # Project requirements/tasks
│   ├── docs/prd-posting.txt
│   └── tasks/tasks.json
└── .env                    # API keys (not in git)
```

## Next Steps When Resuming

1. Update `batch_post.py` to handle new CSV format
2. Add phone prefix logging
3. Run sequential batch test with 2-3 phones
4. Once stable, test concurrent mode
5. Upgrade GUI for batch monitoring

## Quick Test Command

To verify posting still works:
```bash
python post_reel_smart.py podmindstudio "C:\Users\asus\Desktop\projects\geelark-automation\chunk_01a\2bears.1cave\DJj5lHON58y-2.mp4" "Test post"
```

This is a small 1.4MB video that uploads quickly.
