# TikTok E2E Test Plan - Implementation Response

**Task:** Prompt 10 - End-to-End TikTok Posting Test Plan
**Date:** 2025-12-16

---

## Section 1: Test Plan (Iterative Steps)

### Step 1: Single Account Smoke Test
```bash
# Run with 1 worker and single account for initial validation
python parallel_orchestrator.py --campaign tiktok --workers 1 --run
```

**What to verify:**
- TikTok app launches successfully
- Video uploads to phone storage
- Claude can identify Create (+) button
- Navigation loop progresses past step 0

**Expected artifacts:**
- `debug_dumps/tiktok_<account>_step0_*.json` - Initial UI state
- Console logs showing step progression

**If failed:** Check `error_screenshots/tiktok_*.png` and `debug_dumps/` for stuck screen.

---

### Step 2: Full Flow Validation (Single Account)
After smoke test passes, run a complete posting attempt:

```bash
# Same command, but now expecting full flow completion
python parallel_orchestrator.py --campaign tiktok --workers 1 --run
```

**What to verify:**
- Video selected from gallery (`video_selected=True` in logs)
- Caption entered successfully (`caption_entered=True` in logs)
- Post button tapped (`post_clicked=True` in logs)
- Upload confirmation detected OR `action="done"` returned

**Key log patterns to watch:**
```
[TikTok Step N]
  State: video_uploaded=True, video_selected=True, caption_entered=False, post_clicked=False
```

**If stuck at max_steps:**
1. Check `error_screenshots/tiktok_*_max_steps_*.png`
2. Review `debug_dumps/tiktok_*_step*.json` for last 3 UI states
3. Identify which step is looping (same UI elements repeating)

---

### Step 3: Dual Account Validation
Run with both test accounts to verify consistency:

```bash
# Run sequentially (1 worker) with both accounts
python parallel_orchestrator.py --campaign tiktok --workers 1 --run
```

**Test accounts:**
- `glowingscarlets`
- `crookedwafflezing`

**What to verify:**
- Both accounts complete posting without `max_steps` failures
- No account-level errors (banned, suspended, logged out)
- Screenshots saved for any failures

---

### Step 4: Pattern Analysis & Fix Iteration
After initial runs, analyze failures:

1. **Collect all failure artifacts:**
   ```bash
   ls -la error_screenshots/tiktok_*.png
   ls -la debug_dumps/tiktok_*.json
   ```

2. **Identify recurring patterns:**
   - Same `action` repeated 5+ times
   - Stuck on specific screen (gallery, edit, caption)
   - Missing element detection (Create button, Upload, Post)

3. **Apply targeted fixes** (see Section 2 for common patterns)

4. **Re-run test** and verify fix effectiveness

---

### Step 5: Production Readiness Validation
Final validation before declaring production-ready:

```bash
# Run 3 consecutive successful posts per account
python parallel_orchestrator.py --campaign tiktok --workers 1 --run
# Repeat 2 more times
```

**Success criteria:** See Section 3.

---

## Section 2: How to Interpret Logs & Screenshots

### Console Log Patterns

| Pattern | Meaning | Action |
|---------|---------|--------|
| `[TikTok Step N]` with increasing N | Navigation progressing | Good - continue monitoring |
| `State: video_selected=False` after step 10+ | Stuck before gallery selection | Check if Upload button found |
| `State: caption_entered=False` after step 20+ | Stuck at caption entry | Check caption field detection |
| `[ERROR] logged_out:` | Account needs re-login | Mark account as needing attention |
| `[VISION] Analysis:` | Claude Vision analyzed screenshot | Read analysis for insight |
| `Action: scroll_down` repeated 5+ times | Stuck, can't find element | Check UI dump for expected element |

### Screenshot Analysis

**File naming convention:**
```
tiktok_<account>_<reason>_<timestamp>.png
```

**Reasons and what to look for:**

| Reason | What Happened | What to Check |
|--------|---------------|---------------|
| `max_steps_timeout` | Looped 30 times without success | Screenshot shows where Claude got stuck |
| `error_account_banned` | Account-level issue detected | Verify ban message on screen |
| `error_logged_out` | Login screen appeared | Account needs re-authentication |
| `exception_*` | Code error occurred | Check logs for Python traceback |

### UI Dump Analysis (`debug_dumps/`)

**Structure:**
```json
{
  "step": 5,
  "state": {
    "video_uploaded": true,
    "video_selected": false,
    "caption_entered": false,
    "post_clicked": false
  },
  "element_count": 47,
  "elements": [...]
}
```

**How to analyze:**
1. Open sequential dumps (step0, step5, step10...)
2. Check if `state` progresses (false → true)
3. Look for expected elements in `elements` array:
   - Create button: `text='Create'` or `desc='Add'`
   - Upload: `text='Upload'`
   - Video thumbnail: `clickable=true` with duration pattern
   - Post button: `text='Post'`

### Common Failure Patterns & Fixes

#### Pattern A: Never finds Create (+) button
**Symptoms:**
- Step count increases but `video_selected` stays False
- Repeated `scroll_down` actions
- Screenshot shows TikTok home feed

**Fix in `tiktok_poster.py`:**
```python
# Add more Create button patterns to prompt or add direct element detection
# Check if class='...ImageButton' in bottom nav bar
```

#### Pattern B: Taps Record instead of Upload
**Symptoms:**
- Camera preview appears
- `video_selected` stays False
- Screenshot shows recording UI

**Fix:** Prompt already says "DO NOT tap the red record button" - verify Claude is following. May need to add explicit check in `_execute_action()` to avoid Record button coordinates.

#### Pattern C: Video gallery but can't select video
**Symptoms:**
- Screenshot shows video thumbnails
- Repeated scroll or tap actions that don't advance

**Fix:** Check if video thumbnails are detected as `clickable`. May need to tap based on coordinates rather than element index if thumbnail detection is unreliable.

#### Pattern D: Caption entered multiple times
**Symptoms:**
- Caption appears, gets deleted, re-entered
- `caption_entered` toggles True/False

**Fix:** Once `_caption_entered=True`, skip caption step. Already handled in prompt, verify Claude respects it.

#### Pattern E: Post button never clicked
**Symptoms:**
- State shows `caption_entered=True` but `post_clicked` stays False
- Screenshot shows posting screen with Post button visible

**Fix:** Check if Post button has consistent element detection. May need to look for red-colored button or specific coordinates.

---

## Section 3: Iteration Criteria (Production Readiness)

### Minimum Success Thresholds

| Metric | Required Value | How to Measure |
|--------|---------------|----------------|
| Consecutive successful posts | 3 per account | Run 3 times with `--workers 1` |
| Max steps failure rate | 0% (last 6 posts) | No `max_steps` failures in last 6 attempts |
| Error rate | <10% | `(errors / total_attempts) < 0.1` |
| Average steps to completion | <20 | Check logs for step count at `done` |

### Account-Level Checks
Before production deployment, verify per account:

| Check | Pass Criteria |
|-------|---------------|
| Account not banned | No `account_banned` errors |
| Account logged in | No `logged_out` errors |
| Rate limit OK | No `rate_limited` errors in last 24h |
| Video upload works | `video_uploaded=True` consistently |

### Code Quality Checks

| Check | Status |
|-------|--------|
| Screenshot capture on failure | Implemented (Prompt 7) |
| Navigation instrumentation | Implemented (Prompt 8) |
| State tracking alignment | Implemented (Prompt 9) |
| `video_selected` state handling | Implemented (Prompt 9) |
| Claude Vision analysis on failure | Implemented (Prompt 7) |

### Production Go/No-Go Decision

**GO if all true:**
- [ ] 3 consecutive successful posts on `glowingscarlets`
- [ ] 3 consecutive successful posts on `crookedwafflezing`
- [ ] No `max_steps` failures in last 6 attempts total
- [ ] Average navigation steps < 20
- [ ] All failure screenshots are accounted for (known issues)
- [ ] No new error patterns in last test run

**NO-GO if any true:**
- [ ] Any account shows `account_banned` or `account_suspended`
- [ ] >50% of attempts hit `max_steps` timeout
- [ ] Recurring undiagnosed failure pattern
- [ ] Screenshot capture not working (no files in `error_screenshots/`)

---

## Quick Reference Commands

```bash
# Run TikTok campaign test
python parallel_orchestrator.py --campaign tiktok --workers 1 --run

# Check for failure screenshots
ls -la error_screenshots/tiktok_*.png

# Check for UI dumps
ls -la debug_dumps/tiktok_*.json

# View recent error screenshots (if on Linux/Mac)
# For Windows, open error_screenshots folder in Explorer

# Count successful vs failed posts in campaign progress
# Check campaigns/tiktok/progress.csv
```

---

## Files Referenced

- `parallel_orchestrator.py` - Main entry point for campaign execution
- `posters/tiktok_poster.py` - TikTok posting implementation (modified in Prompts 7-9)
- `campaigns/tiktok/campaign.json` - Campaign configuration
- `error_screenshots/` - Failure screenshots directory
- `debug_dumps/` - UI dump files directory
- `campaigns/tiktok/progress.csv` - Campaign progress tracking
