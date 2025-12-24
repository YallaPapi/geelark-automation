# PRD: TikTok Hybrid Posting System

## Overview

Implement TikTok video posting using the same hybrid navigation pattern as Instagram posting and follow systems. This provides rule-based screen detection with optional AI fallback.

## Background

### Previous Attempt (Dec 16, 2025)
- Created AI-only TikTok poster in `posters/tiktok_poster.py`
- Failed with 100% `max_steps_timeout` errors
- Reverted in commit `10483cb` because it broke Instagram posting
- Root causes: No screen detection rules, no loop detection, changed shared infrastructure

### Current State
- Instagram posting: Working (hybrid navigation)
- Follow system: Working (94.4% success, 100% rule-based)
- TikTok: Not implemented (code reverted)

## Test Accounts

TikTok accounts available for testing:
- `glowingscarlets` (used in previous attempt)
- `crookedwafflezing` (used in previous attempt)
- `themotivationmischief` (confirmed working Dec 24)
- `talkingsquidbaby` (confirmed working Dec 24)
- `calknowsbestsometimes` (confirmed working Dec 24)
- `inspirebanana` (confirmed working Dec 24)

## Implementation Plan

### Phase 1: Standalone AI-Only Poster (Data Collection)

**Goal:** Capture UI dumps and screenshots to understand TikTok's flow

1. Create `tiktok_poster_standalone.py` - Completely separate from Instagram
   - No factory pattern, no changes to `parallel_worker.py`
   - Direct copy of the AI navigation loop from `post_reel_smart.py`
   - Swap Instagram prompt for TikTok prompt
   - Heavy logging: Save UI XML dump + screenshot at EVERY step

2. Run against 1-2 test accounts
   - Manual single-phone runs, not orchestrated
   - Goal: Complete 5-10 successful posts to capture the full flow
   - If AI fails, manually guide it and note what went wrong

3. Artifacts collected:
   ```
   tiktok_flow_analysis/
   ├── step_01_home.xml + step_01_home.png
   ├── step_02_create_menu.xml + step_02_create_menu.png
   ├── step_03_gallery.xml + step_03_gallery.png
   └── ... (every screen in the flow)
   ```

### Phase 2: Screen Mapping

**Goal:** Identify all TikTok screen types and their markers

Expected screens (to be validated):

| Screen | Key Markers (hypothetical) |
|--------|---------------------------|
| `HOME_FEED` | Bottom nav with Home/Discover/+/Inbox/Profile |
| `CREATE_MENU` | "New video", "Templates", "Photo editor" options |
| `CAMERA_VIEW` | Record button, "Upload" option, Effects |
| `GALLERY_PICKER` | "Recents", video thumbnails, "Next" button |
| `VIDEO_PREVIEW` | "Select", "Next" buttons, video playing |
| `EDITOR_SCREEN` | "Sounds", "Effects", "Text", "Stickers" |
| `CAPTION_SCREEN` | Description input, hashtag suggestions |
| `POST_CONFIRMATION` | "Post" button, visibility settings |
| `UPLOAD_PROGRESS` | Progress bar, "Uploading..." text |
| `SUCCESS` | Back to feed, "Posted" confirmation |

### Phase 3: Build Hybrid Components

**Goal:** Create rule-based navigation like Instagram/Follow

New files to create:
```
├── tiktok_screen_detector.py   # TikTokScreenType enum + detection rules
├── tiktok_action_engine.py     # Screen -> action mapping
├── hybrid_tiktok_navigator.py  # Coordinates detection + execution
└── tiktok_poster.py            # Main orchestrator (minimal)
```

Pattern match Instagram exactly:
- `TikTokScreenType` enum mirrors `ScreenType`
- Detection uses element IDs, text, resource-ids from TikTok app
- Action engine returns `{"action": "tap", "element_index": N, "reason": "..."}`

### Phase 4: Test Hybrid Mode

**Goal:** Validate 90%+ success rate before integration

1. Run hybrid with `ai_analyzer=None` (pure rules)
2. Track which screens hit `UNKNOWN`
3. Add rules for any missing screens
4. Iterate until 10+ consecutive successes

### Phase 5: Integration

**Goal:** Multi-platform support without breaking Instagram

**Recommended: Separate Entry Points**
```bash
# Instagram (unchanged)
python parallel_orchestrator.py --campaign podcast --workers 3

# TikTok (separate)
python tiktok_orchestrator.py --campaign tiktok --workers 2
```

Only consider factory pattern integration after TikTok is proven stable.

## Critical Requirements

1. **DO NOT MODIFY** existing Instagram posting code
2. **DO NOT MODIFY** `parallel_worker.py` or `parallel_orchestrator.py`
3. Create all TikTok code as NEW files
4. Test TikTok standalone before any integration
5. Keep Instagram and TikTok completely separate until both are stable

## Success Criteria

- 10+ consecutive successful TikTok posts
- 90%+ success rate over 50 posts
- Zero regressions in Instagram posting
- Zero AI API calls in production (100% rule-based)

## Estimated Effort

| Phase | Hours |
|-------|-------|
| Phase 1: AI-only poster + test runs | 1-2 |
| Phase 2: Analyze dumps, document screens | 1-2 |
| Phase 3: Build 3 new hybrid files | 3-4 |
| Phase 4: Test + iterate | 2-3 |
| Phase 5: Separate orchestrator | 1 |
| **Total** | **~10 hours** |

## Files Referenced

Existing patterns to follow:
- `screen_detector.py` - Instagram screen detection
- `action_engine.py` - Instagram action rules
- `hybrid_navigator.py` - Instagram hybrid coordinator
- `follow_screen_detector.py` - Follow screen detection
- `follow_action_engine.py` - Follow action rules
- `hybrid_follow_navigator.py` - Follow hybrid coordinator
