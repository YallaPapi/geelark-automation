# Instagram Reel Posting Flow Analysis
**Date:** December 22, 2025
**Data Source:** 288 flow logs from 12/22/2025
**Success Rate:** 119/288 (41.3%) - note: 103 failures were infrastructure (never started)

## Executive Summary

Analyzed 119 successful posting flows to map Instagram's Reel posting process. Identified 28 unique flow patterns with one dominant "happy path" covering 56% of successful posts.

## Flow Statistics

| Metric | Value |
|--------|-------|
| Total flow logs | 288 |
| Successful | 119 (41.3%) |
| Failed | 169 (58.7%) |
| - Infrastructure failures (Step 0) | 103 (61% of failures) |
| - Actual posting failures | 66 (39% of failures) |
| Unique screen signatures | 862 |
| Unique flow patterns | 28 |

### Duration Stats (Successful Flows)
- **Minimum:** 97.3 seconds
- **Maximum:** 611.9 seconds
- **Average:** 272.8 seconds (4.5 minutes)

### Step Count Distribution
| Steps | Count | Percentage |
|-------|-------|------------|
| 7 | 1 | 0.8% |
| 8 | 14 | 11.8% |
| **9** | **72** | **60.5%** |
| 10 | 19 | 16.0% |
| 11 | 4 | 3.4% |
| 12+ | 9 | 7.6% |

## The Posting Flow

### Primary Flow (9 Steps - 60.5% of successes)

```
Step 1: Feed/Home Screen
   └─► Tap: profile_tab (92.4%)

Step 2: Profile Screen
   └─► Tap: "Create New" button (91.5%)

Step 3: Create Menu (Bottom Sheet)
   └─► Tap: "Create new reel" option (90.8%)

Step 4: Gallery Screen
   └─► Tap: gallery_grid_item_thumbnail (72.9%)
   └─► OR Tap: cam_dest_clips "REEL" tab first (18.6%)

Step 5: Video Edit/Preview Screen
   └─► Tap: clips_right_action_button "Next" (73.3%)

Step 6: Caption Screen (Empty)
   └─► Tap & Type: caption_input_text_view (71.4%)

Step 7: Caption Screen (With Keyboard)
   └─► Tap: action_bar_button_text "OK" (62.4%)

Step 8: Share Screen
   └─► Tap: share_button "Share" (65.0%)

Step 9: Uploading/Success
   └─► Action: done (71.3%)
```

## Key Element Identifiers

### Screen Detection Rules

| Screen | Key Element ID | Key Description |
|--------|----------------|-----------------|
| Feed | `profile_tab`, `feed_tab`, `clips_tab` | Navigation bar present |
| Profile | `profile_header_*`, `action_bar_username_container` | "Create New" desc |
| Create Menu | N/A | "Create new reel" desc |
| Gallery | `gallery_grid_item_thumbnail`, `gallery_destination_item` | "New reel" text |
| Video Edit | `clips_right_action_button`, `clips_action_bar_*` | "Next" desc, "Edit video" |
| Caption | `caption_input_text_view` | "Write a caption" text |
| Share Ready | `share_button`, `save_draft_button` | "Share" desc |
| Uploading | `upload_snackbar_container` | "Sharing to Reels" text |

### Critical Action Elements

| Element ID | Description | When to Click |
|------------|-------------|---------------|
| `profile_tab` | Profile | Step 1 - Start posting flow |
| NO_ID | "Create New" | Step 2 - Open create menu |
| NO_ID | "Create new reel" | Step 3 - Select reel option |
| `gallery_grid_item_thumbnail` | Video thumbnail | Step 4 - Select video |
| `cam_dest_clips` | "REEL" tab | Step 4 (if needed) - Switch to reel mode |
| `clips_right_action_button` | "Next" | Step 5 - Proceed to caption |
| `caption_input_text_view` | Caption field | Step 6 - Enter caption |
| `action_bar_button_text` | "OK" | Step 7 - Dismiss keyboard |
| `share_button` | "Share" | Step 8 - Publish reel |

## Flow Variations

### Pattern 1: Happy Path (67 flows - 56%)
```
profile_tab → Create New → Create new reel → video_thumbnail → Next → caption → OK → Share → DONE
```

### Pattern 2: REEL Tab Selection (11 flows - 9%)
```
profile_tab → Create New → Create new reel → REEL_tab → video_thumbnail → Next → caption → OK → Share → DONE
```
**When:** Gallery opens in POST/STORY mode instead of REEL mode

### Pattern 3: No OK Button (10 flows - 8%)
```
profile_tab → Create New → Create new reel → video_thumbnail → Next → caption → Share → DONE
```
**When:** Keyboard auto-dismisses after caption entry

### Pattern 4: Multiple REEL Tab Taps (2 flows)
```
profile_tab → Create New → Create new reel → REEL_tab → REEL_tab → REEL_tab → video_thumbnail → ...
```
**When:** REEL tab doesn't respond on first tap

### Pattern 5: Dismiss Popups (varies)
```
dismiss_button → dismiss_button → ... → normal flow
```
**When:** Meta Verified popup or other notifications appear

## Failure Analysis

### Failure Distribution
| Step | Failures | Common Cause |
|------|----------|--------------|
| 0 | 103 (61%) | Infrastructure (ADB, Appium) |
| 1-3 | 21 | Popup dialogs, wrong screen |
| 4-5 | 7 | Video selection issues |
| 6-8 | 16 | Caption entry, Share button |
| 9+ | 7 | Post-share confirmation |

### Common Failure Patterns

1. **Never Started (103):** ADB timeout, Appium crash
2. **Create Menu Issues (12):** Popup blocking, menu didn't open
3. **Video Selection (7):** Wrong mode (POST not REEL), thumbnail not found
4. **Caption Problems (8):** Keyboard issues, OK button not found
5. **Share Failed (9):** Button not responding, post-share verification

## Recommendations for Hybrid Navigator

### Rule-Based Steps (High Confidence)
1. **Step 1:** Always tap `profile_tab` first
2. **Step 3:** Always tap "Create new reel" in menu
3. **Step 5:** Always tap "Next" (`clips_right_action_button`)
4. **Step 8:** Always tap "Share" (`share_button`)

### AI-Required Steps (Variations)
1. **Step 2:** "Create New" button location varies
2. **Step 4:** May need REEL tab selection first
3. **Step 6-7:** Caption entry and keyboard handling
4. **Popup handling:** Dismiss dialogs when detected

### Screen Detection Priority
1. Check for `dismiss_button` → Handle popup first
2. Check for `share_button` + `caption_input_text_view` → Share screen
3. Check for `caption_input_text_view` → Caption screen
4. Check for `clips_right_action_button` + "Next" → Video edit screen
5. Check for `gallery_grid_item_thumbnail` → Gallery screen
6. Check for "Create new reel" desc → Create menu
7. Check for "Create New" desc → Profile screen
8. Check for `profile_tab` clickable → Feed/other screen

## Appendix: Raw Data

### Top 5 Flow Signatures
1. **67 flows:** profile_tab → Create New → Create new reel → gallery_grid_it → clips_right_act → caption_input_t → action_bar_butt → share_button → DONE
2. **11 flows:** Same but with cam_dest_clips before gallery
3. **10 flows:** Same but without action_bar_button (OK)
4. **2 flows:** With alert dialog confirmation
5. **2 flows:** Starting from creation_tab instead of profile_tab
