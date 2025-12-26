# GrapheneOS vs Geelark TikTok UI Differences

This document lists the differences between Geelark cloud phones and GrapheneOS physical devices when automating TikTok posting.

## Summary of Differences

| Aspect | Geelark | GrapheneOS |
|--------|---------|------------|
| TikTok Version | v43.x (varies) | v43.1.4 (tested) |
| Screen Resolution | 720x1280 typical | 1080x2400 (Pixel) |
| Element IDs | Stable IDs | Different ID scheme |
| Coordinate Fallbacks | Lower resolution | Higher resolution |

---

## Element ID Differences by Screen

### HOME_FEED

| Element | Geelark ID | GrapheneOS ID | Notes |
|---------|------------|---------------|-------|
| Create button | lxd | mkn | Both have desc='Create' |
| Home nav | lxg | mkq | Both have desc='Home' |
| Profile nav | lxi | mks | Both have desc='Profile' |
| Friends nav | lxf | mkp | Both have desc='Friends' |
| Inbox nav | lxh | mkr | Both have desc='Inbox' |
| Search | ia6 | irz | Both have desc='Search' |

**Action**: Tap Create button
- Geelark: Tap id='lxd'
- GrapheneOS: Tap id='mkn'
- Fallback coordinates differ due to resolution

---

### CREATE_MENU (Camera Screen)

| Element | Geelark ID | GrapheneOS ID | Notes |
|---------|------------|---------------|-------|
| Add sound | d24 | d8a | Both have desc='Add sound' |
| Record button | q76 | - | desc='Record video' |
| Gallery thumb | c_u | r3r, ymg | Tap to open gallery |
| Close button | j0z | jix | Close camera |

**CRITICAL DIFFERENCE - PHOTO/TEXT tabs**:
- GrapheneOS camera screen has "PHOTO" and "TEXT" tabs (UNIQUE!)
- These tabs do NOT appear in video editor
- Detection must prioritize these for correct CREATE_MENU vs VIDEO_EDITOR

**Duration Options**:
- Both have "10m", "60s", "15s" duration options
- UNIQUE to camera screen (not in video editor)

**Coordinate Fallbacks**:
- Geelark: Gallery at (580, 1165)
- GrapheneOS: Gallery at (540, 1900) - different due to resolution

---

### GALLERY_PICKER

| Element | Geelark ID | GrapheneOS ID | Notes |
|---------|------------|---------------|-------|
| Recents selector | x4d | x4d | Same ID |
| Next button | tvr | tvr | Same ID |
| Gallery close | b6x | b6x | Same ID |
| Duration label | faj | faj | Same ID |
| Selection checkbox | gvi | gvi | Same ID |

**SAME**: Gallery picker IDs are consistent between platforms.

---

### VIDEO_EDITOR

| Element | Geelark IDs | GrapheneOS IDs | Notes |
|---------|-------------|----------------|-------|
| Editor tools | fmo, fmh, fms, flf, y48 | ntq, ntn, d88, ycm, qxr, ce1, w85 | Completely different |
| Next button | Text='Next' | ntq (text='Next') | GrapheneOS has specific ID |
| Music indicator | - | d88 (desc='Music') | GrapheneOS specific |
| Your Story | - | qxr | GrapheneOS specific |

**CRITICAL DIFFERENCE - Next button**:
- Geelark: Text-based detection
- GrapheneOS: ID-based `id='ntq'` with text='Next'

**CRITICAL DIFFERENCE - Editing tools**:
- GrapheneOS has desc-based tools: 'Edit', 'Text', 'Stickers', 'Effects', 'Video templates', 'AI meme', 'AI alive'
- Detection uses desc matching, not IDs

**Coordinate Fallbacks**:
- Geelark: Next at (650, 100) - top right
- GrapheneOS: Next at (796, 2181) - bottom right

**IMPORTANT**: VIDEO_EDITOR must REQUIRE Next button and NOT match PHOTO/TEXT tabs

---

### CAPTION_SCREEN

| Element | Geelark ID | GrapheneOS ID | Notes |
|---------|------------|---------------|-------|
| Description field | fpj | fpj | Same ID |
| Post button | pwo, pvz, pvl | pwo, pvz, pvl | Same IDs |
| Edit cover | d1k | d1k | Same ID |
| Hashtags | auj | auj | Same ID |
| Mention | aui | aui | Same ID |
| Save draft | f6a | f6a | Same ID |

**SAME**: Caption screen IDs are consistent between platforms.

---

### SUCCESS

| Element | Geelark ID | GrapheneOS ID | Notes |
|---------|------------|---------------|-------|
| Like button | evz | evz | Same ID |
| Comments | dnk | dnk | Same ID |
| Like icon | evm | evm | Same ID |
| Profile ref | xo5 | xo5 | Same ID |

**SAME**: Success screen IDs are consistent between platforms.

---

## Detection Priority Issues

### Problem: CREATE_MENU vs VIDEO_EDITOR Confusion

Both screens can have "Add sound" text, causing confusion.

**Solution**: Detection order matters:
1. Check CREATE_MENU **BEFORE** VIDEO_EDITOR
2. CREATE_MENU signals: PHOTO/TEXT tabs, duration options (10m/60s/15s)
3. VIDEO_EDITOR signals: Must have Next button, must NOT have PHOTO/TEXT tabs

### Detection Scoring Adjustments

**CREATE_MENU**:
- +0.5 for PHOTO + TEXT tabs (UNIQUE)
- +0.45 for 2+ duration options (UNIQUE)
- +0.35 for record button
- +0.25 for add sound
- +0.2 for gallery thumbnail

**VIDEO_EDITOR**:
- +0.4 for Next button id='ntq'
- +0.35 for Music indicator id='d88'
- +0.35 for 4+ editing tools
- +0.25 for "Your Story"
- Must NOT match if PHOTO/TEXT tabs present

---

## Coordinate Fallback Reference

| Screen | Action | Geelark Coords | GrapheneOS Coords |
|--------|--------|----------------|-------------------|
| HOME_FEED | Tap Create | (360, 1322) | (540, 1400) |
| CREATE_MENU | Tap Gallery | (580, 1165) | (540, 1900) |
| GALLERY_PICKER | First video | (121, 312) | (200, 450) |
| VIDEO_EDITOR | Tap Next | (650, 100) | (796, 2181) |
| PERMISSION | Allow button | (359, 745) | (540, 1100) |

---

## Action Handler Differences

### GrapheneOS-Specific Handlers Needed

1. **HOME_FEED**: Use id='mkn' before 'lxd'
2. **CREATE_MENU**: Use id='r3r' or 'ymg' for gallery
3. **VIDEO_EDITOR**: Use id='ntq' for Next button
4. **Coordinate fallbacks**: Must use GrapheneOS resolution

### Shared Handlers (No Changes Needed)

1. **GALLERY_PICKER**: Same IDs work
2. **CAPTION_SCREEN**: Same IDs work
3. **SUCCESS**: Same IDs work
4. **Permission popups**: Same handling
5. **Dismissible popups**: Same handling

---

## Screen Resolution Differences

| Device Type | Resolution | DPI | Density |
|-------------|------------|-----|---------|
| Geelark Cloud | 720x1280 | 320 | xhdpi |
| Pixel 6 (GrapheneOS) | 1080x2400 | 411 | xxhdpi |
| Pixel 7 (GrapheneOS) | 1080x2400 | 420 | xxhdpi |

**Impact on coordinates**:
- GrapheneOS coordinates are ~1.5x larger in both dimensions
- Bottom navigation is higher on GrapheneOS (taller screen)
- Elements may be positioned differently

---

## Recommendations for GrapheneOS Port

1. **Add GrapheneOS IDs to all detectors** - done
2. **Check CREATE_MENU before VIDEO_EDITOR** - done
3. **Use PHOTO/TEXT tabs for CREATE_MENU detection** - done
4. **Require Next button for VIDEO_EDITOR** - need to verify
5. **Update coordinate fallbacks** - need GrapheneOS-specific values
6. **Add device-specific branches in action handlers** - in progress
