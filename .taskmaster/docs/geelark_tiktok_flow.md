# Geelark TikTok Posting Flow Documentation

This document describes the working Geelark TikTok posting flow, which serves as the baseline for porting to GrapheneOS.

## High-Level Flow

```
HOME_FEED -> CREATE_MENU -> GALLERY_PICKER -> VIDEO_EDITOR -> CAPTION_SCREEN -> SUCCESS
```

## Step-by-Step Flow

### Step 1: HOME_FEED (For You Page)

**Screen Detection** (`tiktok_screen_detector.py::_detect_home_feed`):
- Primary: Create button `id='lxd'` with `desc='Create'`
- Primary: Home nav button `id='lxg'` with `desc='Home'`
- Secondary: Profile nav `id='lxi'`, Friends nav `id='lxf'`, Inbox `id='lxh'`
- Secondary: "For You" / "Following" tabs in text
- Tertiary: Search button `id='ia6'`

**Action Handler** (`tiktok_action_engine.py::_handle_home_feed`):
- Primary: Tap Create button by ID `id='lxd'`
- Secondary: Tap by `desc='create'`
- Fallback: Coordinate tap at (360, 1322)

**Expected Outcome**: Opens camera/create menu

---

### Step 2: CREATE_MENU (Camera/Record Screen)

**Screen Detection** (`tiktok_screen_detector.py::_detect_create_menu`):
- Primary: Record button `id='q76'` with `desc='Record video'`
- Primary: Add sound button `id='d24'` with `desc='Add sound'`
- Primary: Gallery thumbnail `id='c_u'`
- Secondary: Close button `id='j0z'`
- Secondary: Duration options text ("10m", "60s", "15s")
- Tertiary: POST/CREATE tabs

**Action Handler** (`tiktok_action_engine.py::_handle_create_menu`):
- Primary: Tap gallery thumbnail `id='c_u'` (clickable)
- Secondary: Tap `id='r3r'` or `id='ymg'` (GrapheneOS IDs)
- Tertiary: Tap `id='frz'`
- Fallback: Coordinate tap at (540, 1900) for GrapheneOS or (580, 1165) for Geelark

**Expected Outcome**: Opens gallery picker

---

### Step 3: GALLERY_PICKER (Video Selection Grid)

**Screen Detection** (`tiktok_screen_detector.py::_detect_gallery_picker`):
- Primary: Recents selector `id='x4d'` with text='Recents'
- Primary: Next button `id='tvr'` with text='Next'
- Secondary: Gallery close button `id='b6x'`
- Secondary: Media filter tabs ("videos", "photos", "all")
- Secondary: "Select multiple" option
- Tertiary: Video duration labels `id='faj'` with MM:SS format

**Action Handler** (`tiktok_action_engine.py::_handle_gallery_picker`):
1. **If video not selected:**
   - Primary: Find clickable thumbnail containers (no ID, clickable=true, ~200-250px square)
   - Secondary: Tap video selection checkbox `id='gvi'`
   - Tertiary: Use coordinate from `id='faj'` duration label position
   - Fallback: Coordinate tap at (121, 312)
2. **If video selected:**
   - Tap Next button `id='tvr'`

**State Update**: Sets `video_selected = True`

**Expected Outcome**: Proceeds to video editor

---

### Step 4: VIDEO_EDITOR (Sounds/Effects Screen)

**Screen Detection** (`tiktok_screen_detector.py::_detect_video_editor`):
- Primary: Geelark editor IDs: `fmo`, `fmh`, `fms`, `flf`, `y48`, `fmu`, `fmw`, `fnx`
- Secondary: "Add sound" text
- Secondary: "Effects" / "Filters" options
- Tertiary: "Captions" / "Stickers" / "AutoCut" options
- Tertiary: Next button text='Next'

**Action Handler** (`tiktok_action_engine.py::_handle_video_editor`):
- Primary: Tap Next button by ID (`id='ntn'` or `id='ntq'` for GrapheneOS)
- Secondary: Tap by text='next' or desc='next'
- Tertiary: Tap 'skip', 'done', 'continue'
- Fallback: Coordinate tap at (796, 2181) for GrapheneOS or (650, 100) for Geelark

**Expected Outcome**: Proceeds to caption screen

---

### Step 5: CAPTION_SCREEN (Description + Post)

**Screen Detection** (`tiktok_screen_detector.py::_detect_caption_screen`):
- Primary: Description field `id='fpj'` with 'Add description...'
- Primary: Post button IDs: `id='pvl'`, `id='pvz'`, `id='pwo'`
- Secondary: Edit cover `id='d1k'`
- Secondary: Hashtags button `id='auj'`
- Secondary: Mention button `id='aui'`
- Secondary: Save draft `id='f6a'`
- Tertiary: Description hint text patterns
- Tertiary: "Everyone can view" visibility setting

**Action Handler** (`tiktok_action_engine.py::_handle_caption_screen`):
1. **If caption not entered:**
   - Primary: Type caption into description field `id='fpj'`
   - Secondary: Find by text containing 'describe' or 'caption'
2. **If caption entered:**
   - Primary: Tap Post button by ID (`id='pwo'`, `id='pvz'`, `id='pvl'`)
   - Secondary: Tap by text='post' or desc='post'

**State Update**: Sets `caption_entered = True` after typing

**Expected Outcome**: Video uploads and posts

---

### Step 6: SUCCESS (Post Complete)

**Screen Detection** (`tiktok_screen_detector.py::_detect_success`):
- High Priority: "Connect with contacts" / "Connect with friends" text
- High Priority: "Invite friends" screen
- Primary: Like video button `id='evz'` with desc containing 'like'
- Primary: Comments button `id='dnk'` with desc containing 'comment'
- Secondary: Like icon `id='evm'`
- Secondary: Profile reference `id='xo5'`
- Tertiary: Text markers ("uploaded successfully", "video posted")

**Action Handler** (`tiktok_action_engine.py::_handle_success`):
- Returns `ActionType.SUCCESS` with "Video posted successfully"

**Expected Outcome**: Flow complete, video is live

---

## Popup Handling

### Permission Popups

**Screen Detection** (`_detect_permission_popup`):
- Primary: `id='grant_dialog'`, `id='grant_singleton'`, `id='permission_message'`
- Primary: `id='permission_allow_foreground_only_button'`
- Secondary: "Allow TikTok to..." patterns
- Tertiary: "WHILE USING THE APP", "ONLY THIS TIME"

**Action Handler** (`_handle_permission_popup`):
- Primary: Tap permission button IDs
- Secondary: Tap by text ('while using the app', 'allow', 'only this time')
- Fallback: Coordinate tap at (359, 745)

### Dismissible Popups

**Screen Detection** (`_detect_dismissible_popup`):
- Dismiss markers: 'not now', 'skip', 'maybe later', 'dismiss', 'no thanks', 'cancel'
- Smaller element count (<20 elements)

**Action Handler** (`_handle_dismissible_popup`):
- Tap dismiss option
- Fallback: Press BACK key

---

## Element ID Reference (Geelark)

| Screen | Element | ID | Description |
|--------|---------|-----|-------------|
| HOME_FEED | Create button | lxd | desc='Create' |
| HOME_FEED | Home nav | lxg | desc='Home' |
| HOME_FEED | Profile nav | lxi | desc='Profile' |
| HOME_FEED | Friends nav | lxf | desc='Friends' |
| HOME_FEED | Inbox nav | lxh | desc='Inbox' |
| HOME_FEED | Search | ia6 | desc='Search' |
| CREATE_MENU | Record button | q76 | desc='Record video' |
| CREATE_MENU | Add sound | d24 | desc='Add sound' |
| CREATE_MENU | Gallery thumb | c_u | Clickable thumbnail |
| CREATE_MENU | Close | j0z | desc='Close' |
| GALLERY_PICKER | Recents | x4d | text='Recents' |
| GALLERY_PICKER | Next button | tvr | text='Next' |
| GALLERY_PICKER | Close | b6x | desc='Close' |
| GALLERY_PICKER | Duration | faj | text='MM:SS' |
| GALLERY_PICKER | Checkbox | gvi | Video selection |
| VIDEO_EDITOR | Editor IDs | fmo, fmh, fms, flf, y48 | Editing tools |
| CAPTION_SCREEN | Description | fpj | text='Add description...' |
| CAPTION_SCREEN | Post button | pwo, pvz, pvl | text='Post' |
| CAPTION_SCREEN | Edit cover | d1k | text='Edit cover' |
| CAPTION_SCREEN | Hashtags | auj | text='Hashtags' |
| CAPTION_SCREEN | Mention | aui | text='Mention' |
| CAPTION_SCREEN | Save draft | f6a | desc='Save draft' |
| SUCCESS | Like button | evz | desc='Like video' |
| SUCCESS | Comments | dnk | desc='Read or add comments' |
| SUCCESS | Like icon | evm | desc='Like' |
| SUCCESS | Profile ref | xo5 | Profile reference |

---

## State Machine

```
                    ┌─────────────┐
                    │  HOME_FEED  │
                    └──────┬──────┘
                           │ Tap Create (lxd)
                    ┌──────▼──────┐
            ┌───────│ CREATE_MENU │
            │       └──────┬──────┘
            │              │ Tap Gallery (c_u)
    Permission     ┌──────▼──────────┐
    Popup ─────────│ GALLERY_PICKER  │
                   └──────┬──────────┘
                          │ Select video + Tap Next (tvr)
                   ┌──────▼──────────┐
                   │  VIDEO_EDITOR   │
                   └──────┬──────────┘
                          │ Tap Next
                   ┌──────▼──────────┐
                   │ CAPTION_SCREEN  │
                   └──────┬──────────┘
                          │ Type caption + Tap Post (pwo)
                   ┌──────▼──────────┐
                   │    SUCCESS      │
                   └─────────────────┘
```
