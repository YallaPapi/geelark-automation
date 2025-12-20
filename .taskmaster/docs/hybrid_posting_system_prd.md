# Hybrid Posting System PRD - Option C

## Overview

Build a hybrid Instagram posting system that uses **deterministic rules for known screens** (80-90% of cases) and **AI fallback for unknown/stuck situations** (10-20% of cases). This reduces API costs while maintaining flexibility.

## Problem Statement

- Claude Sonnet works but costs ~$20/day for 120 posts
- GPT-5 mini is cheap but can't handle complex prompts
- Current approach calls AI every single step (wasteful)
- Most Instagram screens are predictable and don't need AI

## Goals

1. Reduce AI API calls by 80-90%
2. Maintain posting success rate (>80%)
3. Build self-healing system that discovers new paths
4. Create reusable screen detection library

---

## Phase 1: Flow Logging Infrastructure

### Description
Add comprehensive logging to the current Sonnet-based poster to capture every step of the posting flow. This data will be used to identify patterns and build deterministic rules.

### Requirements

#### 1.1 Create FlowLogger class
- Logs each step with timestamp, screen signature, action, result
- Stores in JSONL format for easy parsing
- One file per posting session: `flow_logs/{account}_{timestamp}.jsonl`

#### 1.2 Log entry structure
```json
{
  "timestamp": "2025-12-19T10:30:45",
  "step": 5,
  "screen_signature": "abc123def456",
  "elements_summary": ["Create button", "Home tab", "Search tab"],
  "key_elements": [
    {"idx": 5, "text": "Create", "desc": "", "clickable": true, "bounds": [100,200,200,300]},
    {"idx": 12, "text": "Next", "desc": "", "clickable": true, "bounds": [900,50,1000,100]}
  ],
  "action_taken": {"action": "tap", "element_index": 5, "reason": "Tap Create to start posting"},
  "ai_called": true,
  "ai_tokens_used": 1500,
  "result": "success"
}
```

#### 1.3 Integrate with existing poster
- Add logging hooks in post_reel_smart.py post() method
- Log BEFORE and AFTER each action
- Capture screen state transitions

#### 1.4 Screen signature function
- Reuse/adapt ui_signature() from gpt5mini-optimization branch
- Stable hash of normalized UI elements
- Used to identify "same screen" across sessions

---

## Phase 2: Data Collection Run

### Description
Run the Sonnet poster on all accounts while collecting flow logs. This builds our training data for pattern analysis.

### Requirements

#### 2.1 Run full posting cycle
- Post to all podcast campaign accounts
- Post to all viral campaign accounts
- Capture logs for every session

#### 2.2 Capture edge cases
- Include accounts that hit popups
- Include accounts that require recovery
- Include any failure cases

#### 2.3 Log aggregation
- Combine all session logs into analysis dataset
- Track unique screen signatures seen
- Count frequency of each signature

---

## Phase 3: Pattern Analysis

### Description
Analyze collected flow logs to identify distinct screen types, common flows, and decision points.

### Requirements

#### 3.1 Screen clustering
- Group log entries by screen_signature
- Identify distinct screen types (feed, create menu, gallery, editing, caption, sharing, popups)
- Document visual characteristics of each type

#### 3.2 Flow mapping
- Build state transition graph: screen A -> action -> screen B
- Identify the "happy path" (most common successful flow)
- Identify branch points (where flow can diverge)

#### 3.3 Decision point analysis
- For each screen type, identify what action leads to success
- Document: "If on screen X, do action Y"
- Note any variations or edge cases

#### 3.4 Popup catalog
- List all popup types encountered
- Document how each was dismissed
- Categorize: dismissible (tap X), informational (tap OK), blocking (requires action)

---

## Phase 4: Screen Detection Rules

### Description
Convert pattern analysis into deterministic screen detection rules that don't require AI.

### Requirements

#### 4.1 ScreenDetector class
```python
class ScreenDetector:
    def detect(self, elements: List[Dict]) -> ScreenType:
        """Identify screen type from UI elements. No AI call."""
        pass
```

#### 4.2 Detection rules for each screen type
Each rule checks for presence/absence of key indicators:

**FEED_SCREEN**
- Has bottom nav: Home, Search, Reels, Profile tabs
- Has posts/stories in middle area
- No overlay/popup visible

**CREATE_MENU**
- Shows options: Story, Reel, Post, Live
- Appeared after tapping +/Create
- Modal or full screen

**GALLERY_PICKER**
- Shows media thumbnails in grid
- Has tabs: Recents, Gallery, etc.
- May have camera option

**EDITING_SCREEN**
- Has video preview
- Has Next button (top right)
- May have trim/audio/effects controls

**CAPTION_SCREEN**
- Has text input field for caption
- Has Share button
- Has back/cancel option

**SHARING_SCREEN**
- Shows "Sharing to Reels" or progress indicator
- Usually brief/transitional

**POPUP_DISMISSIBLE**
- Has X, Close, Not now, Maybe later
- Overlay on top of other content
- Meta Verified, Suggestions, etc.

**POPUP_ACTION_REQUIRED**
- Requires specific action (not just dismiss)
- Permissions, login, errors

**UNKNOWN**
- Doesn't match any known pattern
- Triggers AI fallback

#### 4.3 Rule priority
- Check for popups first (they overlay other screens)
- Then check for specific screens in order
- Fall back to UNKNOWN if no match

#### 4.4 Confidence scoring
- Each rule returns confidence score (0-100)
- If highest confidence < 70, treat as UNKNOWN
- Log low-confidence detections for review

---

## Phase 5: Deterministic Action Engine

### Description
For each detected screen type, execute the appropriate action without AI.

### Requirements

#### 5.1 ActionEngine class
```python
class ActionEngine:
    def get_action(self, screen_type: ScreenType, elements: List[Dict], state: PostingState) -> Action:
        """Return deterministic action for known screen. No AI call."""
        pass
```

#### 5.2 Action rules for each screen type

**FEED_SCREEN**
- Find Create/+ button -> tap it
- If not visible, tap Profile tab first

**CREATE_MENU**
- Find "Reel" option -> tap it

**GALLERY_PICKER**
- Find first video thumbnail (top-left area) -> tap it
- If no video visible, check for Videos/Reels tab

**EDITING_SCREEN**
- Find Next button -> tap it
- Handle trim/audio/effects by tapping Next

**CAPTION_SCREEN**
- If caption not entered: find caption field -> tap and type
- If caption entered: find Share button -> tap it

**SHARING_SCREEN**
- Wait and verify completion
- Return "done" when confirmed

**POPUP_DISMISSIBLE**
- Find dismiss button (X, Close, Not now) -> tap it
- Press back as fallback

**POPUP_ACTION_REQUIRED**
- Log for human review
- Attempt safe dismissal (back button)

**UNKNOWN**
- Trigger AI fallback

#### 5.3 Element finding helpers
```python
def find_element_by_text(elements, text_patterns) -> Optional[int]
def find_element_by_position(elements, region) -> Optional[int]
def find_clickable_in_region(elements, x_range, y_range) -> Optional[int]
```

---

## Phase 6: AI Fallback Integration

### Description
When screen is unknown or system is stuck, call AI with minimal focused prompt.

### Requirements

#### 6.1 Fallback trigger conditions
- ScreenDetector returns UNKNOWN
- Same screen detected 2+ times in a row (stuck)
- Action failed (element not found)

#### 6.2 Minimal AI prompt
```
Unknown Instagram screen. Goal: post Reel.
Current state: video_uploaded={}, caption_entered={}, share_clicked={}

UI elements (filtered):
[10-15 key elements with indices]

What single action should I take? Respond JSON only:
{"action": "tap|back|home", "element_index": N, "reason": "brief"}
```

#### 6.3 AI response handling
- Parse response
- Execute action
- Log the unknown screen + successful action for future rule creation

#### 6.4 Fallback limits
- Max 5 AI calls per posting session
- If exceeded, abort and log failure

---

## Phase 7: Self-Healing / Discovery System

### Description
Automatically discover and integrate new screen patterns without code changes.

### Requirements

#### 7.1 Unknown screen logging
- When AI handles unknown screen, log full details
- Include: elements, action taken, result, next screen

#### 7.2 Pattern discovery
- Periodically analyze unknown screen logs
- Identify frequently recurring unknowns
- Group by screen signature

#### 7.3 Rule suggestion
- For frequent unknowns, suggest detection rule
- Include: key elements, suggested action
- Store in `discovered_rules.json`

#### 7.4 Rule verification
- Before auto-adding rule, verify it works
- Require N successful uses (e.g., 3)
- Flag for human review if uncertain

#### 7.5 Rule integration
- Verified rules get added to ScreenDetector
- Can be loaded from config file (no code change needed)
- Support hot-reload of rules

---

## Phase 8: Integration and Testing

### Description
Integrate all components and test the hybrid system.

### Requirements

#### 8.1 Main posting flow refactor
```python
def post(video_path, caption):
    while not done:
        elements = dump_ui()
        screen_type = screen_detector.detect(elements)

        if screen_type == UNKNOWN or is_stuck():
            action = ai_fallback(elements, state)
            log_unknown_screen(elements, action)
        else:
            action = action_engine.get_action(screen_type, elements, state)

        execute(action)
        log_step(screen_type, action, result)
```

#### 8.2 A/B testing
- Run hybrid system on subset of accounts
- Compare success rate vs pure Sonnet
- Compare API costs

#### 8.3 Metrics tracking
- Total posts attempted
- Success rate
- AI calls per post (target: <2 average)
- Unknown screens encountered
- Rules auto-discovered

---

## Success Criteria

1. **API cost reduction**: 80%+ reduction in AI calls (from ~19/post to <4/post)
2. **Success rate**: Maintain >80% posting success
3. **Self-healing**: System discovers and handles new popups without code changes
4. **Reliability**: Deterministic paths are 100% consistent (no AI hallucination)

## Dependencies

- Current Claude Sonnet poster (working baseline)
- ui_signature() function (from gpt5mini branch)
- Flow logging infrastructure (new)

## Timeline Priority

1. **Phase 1** (Flow Logging) - Implement first, run immediately
2. **Phase 2** (Data Collection) - Run with normal posting
3. **Phase 3-5** (Analysis + Rules) - Build after collecting data
4. **Phase 6-7** (AI Fallback + Self-Healing) - Add after rules work
5. **Phase 8** (Testing) - Validate before full rollout
