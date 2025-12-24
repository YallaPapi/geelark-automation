# TikTok Screen Reference

This document maps TikTok Android UI elements for building hybrid navigation rules.
Based on flow logs collected 2024-12-24 from AI-only test runs.

## Package Name

```
com.zhiliaoapp.musically
```

## Screen Types

### 1. HOME_FEED (For You Page)

The main TikTok feed with video playback.

**Key Indicators (High Confidence):**

| Element | ID | Text | Desc | Confidence |
|---------|-----|------|------|------------|
| Create button | `lxd` | - | `Create` | 0.95 |
| Home nav | `lxg` | - | `Home` | 0.90 |
| Profile nav | `lxi` | - | `Profile` | 0.90 |
| Search | `ia6` | - | `Search` | 0.85 |
| For You tab | `text1` | `For You` | - | 0.80 |
| Following tab | `text1` | `Following` | - | 0.80 |

**Detection Rule:**
```python
def _detect_home_feed(self, elements, texts, descs, all_text):
    score = 0.0
    found = []

    # Primary: Create button in nav
    for elem in elements:
        if elem.get('id') == 'lxd' and 'create' in elem.get('desc', '').lower():
            score += 0.4
            found.append('create_button')

    # Secondary: For You / Following tabs
    if 'for you' in all_text:
        score += 0.25
        found.append('for_you_tab')

    # Tertiary: Bottom nav elements
    if any(e.get('id') == 'lxg' for e in elements):
        score += 0.2
        found.append('home_nav')

    return min(score, 0.95), found
```

---

### 2. PERMISSION_POPUP (System Dialogs)

Camera, microphone, and storage permission requests.

**Key Indicators (High Confidence):**

| Element | ID | Text | Desc | Confidence |
|---------|-----|------|------|------------|
| Dialog container | `grant_dialog` | - | - | 0.95 |
| Dialog singleton | `grant_singleton` | - | - | 0.90 |
| Message | `permission_message` | `Allow TikTok to...` | - | 0.95 |
| Allow button | `permission_allow_foreground_only_button` | `WHILE USING THE APP` | - | 0.98 |
| One-time button | `permission_allow_one_time_button` | `ONLY THIS TIME` | - | 0.98 |
| Deny button | `permission_deny_button` | `DON'T ALLOW` | - | 0.98 |

**Common Permission Types:**
- "Allow TikTok to take pictures and record video?"
- "Allow TikTok to record audio?"
- "Allow TikTok to access photos and videos on this device?"

**Detection Rule:**
```python
def _detect_permission_popup(self, elements, texts, descs, all_text):
    score = 0.0
    found = []

    # Primary: Permission dialog IDs
    for elem in elements:
        if elem.get('id') in ['grant_dialog', 'grant_singleton', 'permission_message']:
            score += 0.5
            found.append('permission_dialog')
            break

    # Primary: Allow buttons
    for elem in elements:
        if elem.get('id') == 'permission_allow_foreground_only_button':
            score += 0.4
            found.append('allow_button')
            break

    return min(score, 0.98), found
```

---

### 3. CREATE_MENU (Camera/Recording Screen)

The recording interface with upload option.

**Key Indicators (High Confidence):**

| Element | ID | Text | Desc | Confidence |
|---------|-----|------|------|------------|
| Record button | `q76` | - | `Record video` | 0.95 |
| Add sound | `d24` | - | `Add sound` | 0.90 |
| Add sound text | `x51` | `Add sound` | - | 0.85 |
| Close button | `j0z` | - | `Close` | 0.90 |
| Gallery thumbnail | `c_u` | - | - | 0.80 |
| Duration options | `u33` | `10m`/`60s`/`15s` | - | 0.85 |
| POST button | `u33` | `POST` | - | 0.90 |
| CREATE button | `u33` | `CREATE` | - | 0.90 |

**Camera Mode Options:**
- `10m` - 10 minute video
- `60s` - 60 second video
- `15s` - 15 second video
- `PHOTO` - Photo mode
- `TEXT` - Text mode

**Detection Rule:**
```python
def _detect_create_menu(self, elements, texts, descs, all_text):
    score = 0.0
    found = []

    # Primary: Record video button
    for elem in elements:
        if elem.get('id') == 'q76' and 'record' in elem.get('desc', '').lower():
            score += 0.4
            found.append('record_button')
            break

    # Primary: Add sound
    for elem in elements:
        if elem.get('id') == 'd24' and 'sound' in elem.get('desc', '').lower():
            score += 0.3
            found.append('add_sound')
            break

    # Secondary: Duration options
    if '10m' in texts or '60s' in texts or '15s' in texts:
        score += 0.15
        found.append('duration_options')

    # Tertiary: POST/CREATE buttons
    if 'post' in texts or 'create' in texts:
        score += 0.1
        found.append('post_create')

    return min(score, 0.95), found
```

---

### 4. GALLERY_PICKER (Video Selection)

The gallery overlay for selecting existing videos.

**Key Indicators (High Confidence):**

| Element | ID | Text | Desc | Confidence |
|---------|-----|------|------|------------|
| Gallery close | `b6x` | - | `Close` | 0.90 |
| Recents selector | `x4d` | `Recents` | - | 0.90 |
| Videos tab | - | `Videos` | - | 0.85 |
| Photos tab | - | `Photos` | - | 0.85 |
| Next button | `tvr` | `Next` | - | 0.95 |
| Select multiple | `mlr` | `Select multiple` | - | 0.85 |
| Video duration | `faj` | `MM:SS` | - | 0.80 |

**Detection Rule:**
```python
def _detect_gallery_picker(self, elements, texts, descs, all_text):
    score = 0.0
    found = []

    # Primary: Recents selector
    for elem in elements:
        if elem.get('id') == 'x4d' and 'recents' in elem.get('text', '').lower():
            score += 0.35
            found.append('recents_selector')
            break

    # Primary: Next button
    for elem in elements:
        if elem.get('id') == 'tvr' and elem.get('text', '').lower() == 'next':
            score += 0.35
            found.append('next_button')
            break

    # Secondary: Video/Photos tabs
    if 'videos' in texts or 'photos' in texts:
        score += 0.15
        found.append('media_tabs')

    # Secondary: Select multiple option
    if 'select multiple' in all_text:
        score += 0.1
        found.append('multi_select')

    return min(score, 0.95), found
```

---

### 5. VIDEO_EDITOR (Sounds/Effects Screen)

After selecting video, before caption screen.

**Expected Indicators (to be confirmed):**

| Element | ID | Text | Desc | Confidence |
|---------|-----|------|------|------------|
| Next button | - | `Next` | - | 0.90 |
| Sounds option | - | `Sounds` | - | 0.85 |
| Effects option | - | `Effects` | - | 0.85 |
| Text option | - | `Text` | - | 0.80 |
| Video preview | - | - | - | - |

**Note:** Need more flow data to confirm these elements.

---

### 6. CAPTION_SCREEN (Post Details)

Final screen before posting.

**Expected Indicators (to be confirmed):**

| Element | ID | Text | Desc | Confidence |
|---------|-----|------|------|------------|
| Description field | - | `Describe your video` | - | 0.90 |
| Post button | - | `Post` | - | 0.95 |
| Visibility | - | `Everyone`/`Friends` | - | 0.80 |
| Hashtag suggestions | - | `#` | - | 0.70 |

**Note:** Need more flow data to confirm these elements.

---

### 7. UPLOAD_PROGRESS (Posting)

While video is uploading/processing.

**Expected Indicators:**

| Element | ID | Text | Desc | Confidence |
|---------|-----|------|------|------------|
| Progress bar | - | - | - | 0.80 |
| Uploading text | - | `Uploading...`/`Posting...` | - | 0.90 |

---

### 8. SUCCESS (Post Complete)

After successful post.

**Expected Indicators:**
- Return to HOME_FEED or profile
- Toast message about post success

---

## Error States

### LOGGED_OUT
- `text='Log in to TikTok'`
- `text='Sign up for TikTok'`
- `text='Phone number or email'`

### BANNED
- `text='Your account was permanently banned'`
- `text='account has been banned'`

### SUSPENDED
- `text='account suspended'`
- `text='temporarily suspended'`

### CAPTCHA
- `text='Verify you are human'`
- `text='security verification'`
- `text='slide to verify'`

### RESTRICTION
- `text='You cannot post'`
- `text='posting is restricted'`
- `text='try again later'`

---

## Action Patterns

### Tap Create Button (HOME_FEED -> CREATE_MENU)
```python
for elem in elements:
    if elem.get('id') == 'lxd' and 'create' in elem.get('desc', '').lower():
        return Action(ActionType.TAP, target_element=idx, confidence=0.95)
```

### Dismiss Permission (PERMISSION_POPUP)
```python
for elem in elements:
    if elem.get('id') == 'permission_allow_foreground_only_button':
        return Action(ActionType.TAP, target_element=idx, confidence=0.98)
```

### Open Gallery (CREATE_MENU -> GALLERY_PICKER)
```python
for elem in elements:
    if elem.get('id') == 'c_u':  # Gallery thumbnail
        return Action(ActionType.TAP, target_element=idx, confidence=0.85)
```

### Tap Next (GALLERY_PICKER -> VIDEO_EDITOR)
```python
for elem in elements:
    if elem.get('id') == 'tvr' and elem.get('text', '').lower() == 'next':
        return Action(ActionType.TAP, target_element=idx, confidence=0.95)
```

---

## Data Sources

Flow logs collected from:
- `themotivationmischief_20251224_162606.jsonl` (58KB, 12 steps)
- `calknowsbestsometimes_20251224_163148.jsonl` (85KB, 12 steps)

Test accounts:
- themotivationmischief
- talkingsquidbaby
- calknowsbestsometimes
- inspirebanana
- glowingscarlets
- crookedwafflezing

---

## Next Steps

1. Collect more flow data for VIDEO_EDITOR and CAPTION_SCREEN
2. Implement `tiktok_screen_detector.py`
3. Implement `tiktok_action_engine.py`
4. Test hybrid navigation
