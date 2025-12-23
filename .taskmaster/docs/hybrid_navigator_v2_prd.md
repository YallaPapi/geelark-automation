# PRD: Hybrid Navigator V2 - Data-Driven Fixes

## Overview
Update the hybrid posting system based on 119 successful AI flow logs from December 22, 2025. Replace guess-based logic with proven element IDs and patterns.

## Background
- Current hybrid navigator was built on assumptions
- We now have real data from 119 successful posts showing exact element IDs and flow patterns
- Success rate with AI-only: 88-92%
- Goal: Match or exceed this with hybrid (rule-based + AI fallback)

## Requirements

### Task 1: Update Screen Detector Element Matching
Update `screen_detector.py` to use element IDs as primary matching:

**Changes:**
- FEED_SCREEN: Look for `profile_tab`, `feed_tab`, `clips_tab` IDs
- PROFILE_SCREEN: Look for `action_bar_username_container`, "Create New" in desc
- CREATE_MENU: Look for "Create new reel" in desc (not text)
- GALLERY_PICKER: Look for `gallery_grid_item_thumbnail`, `cam_dest_clips`, `gallery_destination_item`
- VIDEO_EDITING: Look for `clips_right_action_button`, `clips_action_bar_*` IDs
- SHARE_PREVIEW: Look for `caption_input_text_view`, `share_button`, `action_bar_button_text`
- SHARING_PROGRESS: Look for `upload_snackbar_container`, "Sharing to Reels" text

### Task 2: Update Action Engine with Correct Element Lookups
Update `action_engine.py` to find elements by ID first, desc second:

**Step 1 (Feed → Profile):**
- Primary: element.id == 'profile_tab'
- Fallback: element.desc == 'Profile'

**Step 2 (Profile → Create):**
- Primary: element.desc == 'Create New'
- Fallback: element.id == 'creation_tab'

**Step 3 (Create Menu → Reel):**
- Primary: element.desc == 'Create new reel'

**Step 4 (Gallery → Video):**
- First check: If cam_dest_clips visible, tap it (REEL tab selection)
- Then: element.id == 'gallery_grid_item_thumbnail'

**Step 5 (Video Edit → Next):**
- Primary: element.id == 'clips_right_action_button'
- Fallback: element.desc == 'Next'

**Step 6 (Caption Entry):**
- Primary: element.id == 'caption_input_text_view'

**Step 7 (NEW - Dismiss Keyboard):**
- If element.id == 'action_bar_button_text' AND desc == 'OK': tap it
- This step was completely missing before

**Step 8 (Share):**
- Primary: element.id == 'share_button'
- Fallback: element.desc == 'Share'

### Task 3: Add REEL Tab Selection Logic
In GALLERY_PICKER handler, add check for REEL mode:
- If `cam_dest_clips` element exists and gallery is not in REEL mode
- Tap `cam_dest_clips` before selecting video
- This handles the 18.6% of flows that needed REEL tab first

### Task 4: Add OK Button Dismissal Step
Add new handling for keyboard dismissal:
- After caption is entered, check for `action_bar_button_text` with desc "OK"
- If found, tap it before looking for Share button
- 62.4% of successful flows needed this step

### Task 5: Run Podcast Campaign with Hybrid Navigator
- Reset podcast campaign progress
- Run with 5 workers using hybrid navigator
- Monitor failures in real-time via error_debugger logs
- Capture all failure screenshots and UI dumps

### Task 6: Analyze Podcast Failures and Fix Edge Cases
- Review each failure's screenshot and UI dump
- Identify missing if/else rules (popups, unexpected screens)
- Update screen_detector.py and action_engine.py with fixes
- Document each edge case found

### Task 7: Retry Podcast Failures
- Reset failed jobs to pending
- Run retry with updated hybrid navigator
- Measure improvement

### Task 8: Run Viral Campaign with Hybrid Navigator
- Reset viral campaign progress
- Run with 5 workers using hybrid navigator
- Monitor failures in real-time

### Task 9: Analyze Viral Failures and Fix Edge Cases
- Same process as Task 6
- Cross-reference with podcast findings
- Add any new edge cases to the rules

### Task 10: Retry Viral Failures
- Reset failed jobs to pending
- Run retry with updated rules
- Measure final success rates

### Task 11: Document Final Results
- Compare AI-only vs Hybrid success rates
- List all edge cases discovered and fixed
- Commit final working version

## Success Criteria
- Hybrid navigator achieves 85%+ success rate (matching AI-only performance)
- All discovered edge cases have if/else rules
- No AI fallback needed for standard posting flow

## Files to Modify
- `screen_detector.py` - Element ID matching
- `action_engine.py` - Action selection logic
- `hybrid_navigator.py` - State management (if needed)
- `post_reel_smart.py` - Integration (if needed)
