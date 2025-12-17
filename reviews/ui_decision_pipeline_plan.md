# UI Decision Pipeline Investigation & Documentation Plan

## Executive Summary

This document provides a detailed plan to map, document, and potentially refactor the full UI decision pipeline used for posting to Instagram and TikTok in the `geelark-automation` codebase. The pipeline follows a UI dump → Claude analysis → action execution → logging pattern.

---

## Part 1: Key Components in the UI Decision Path

### 1.1 UI Dump → `uielements` Collection

| Component | File | Function/Method | Line Range (approx) | Description |
|-----------|------|-----------------|---------------------|-------------|
| **Appium UI Dump** | `appium_ui_controller.py` | `AppiumUIController.dump_ui()` | Lines 174014-174063 | Primary UI element collection. Parses Appium's `page_source` XML, extracts elements with text/desc/bounds/clickable attributes |
| **SmartInstagramPoster.dump_ui()** | `post_reel_smart.py` | `dump_ui()` | Lines 192884-192946 | Instagram-specific wrapper that calls Appium and handles UiAutomator2 crash recovery |
| **TikTok dump_ui** | `posters/tiktok_poster.py` | `_dump_ui()` | Lines 150506-150513 | Thin wrapper delegating to `self._ui_controller.dump_ui()` |

**Element Schema Produced:**
```python
{
    'text': str,      # android:text attribute
    'desc': str,      # content-desc attribute  
    'id': str,        # resource-id (stripped of package prefix)
    'bounds': str,    # "[x1,y1][x2,y2]" format
    'center': tuple,  # (cx, cy) computed center
    'clickable': bool # clickable attribute
}
```

### 1.2 Analyzer Class - ClaudeUIAnalyzer

| Component | File | Function/Method | Line Range (approx) | Description |
|-----------|------|-----------------|---------------------|-------------|
| **Class Definition** | `claude_analyzer.py` | `ClaudeUIAnalyzer` | Lines 179130-179517 | Main Instagram UI analyzer class |
| **Element Formatting** | `claude_analyzer.py` | `format_elements()` | Lines 179137-179160 | Converts elements list to text description for prompt |
| **Prompt Construction** | `claude_analyzer.py` | `build_prompt()` | Lines 179162-179356 | Builds the full prompt with state, elements, instructions |
| **Response Parsing** | `claude_analyzer.py` | `parse_response()` | Lines 179358-179382 | Parses JSON from Claude response, handles markdown blocks |
| **Analysis Orchestration** | `claude_analyzer.py` | `analyze()` | Lines 179384-179492 | Main entry point: calls build_prompt → API → parse + validate |
| **Index Validation** | `claude_analyzer.py` | within `analyze()` | Lines 179464-179476 | Validates/clamps element_index to valid range |

**TikTok Analyzer (Inline):**
| Component | File | Function/Method | Line Range (approx) | Description |
|-----------|------|-----------------|---------------------|-------------|
| **Prompt Constant** | `posters/tiktok_poster.py` | `TIKTOK_NAVIGATION_PROMPT` | Lines 150185-150245 | TikTok-specific navigation prompt |
| **Element Formatting** | `posters/tiktok_poster.py` | `_format_elements_for_claude()` | Lines 150515-150531 | Formats elements for TikTok prompt |
| **UI Analysis** | `posters/tiktok_poster.py` | `_analyze_ui()` | Lines 150533-150571 | Calls Claude API, parses response |

### 1.3 Call Sites in Instagram Poster

| Component | File | Function/Method | Line Range (approx) | Description |
|-----------|------|-----------------|---------------------|-------------|
| **SmartInstagramPoster class** | `post_reel_smart.py` | `SmartInstagramPoster` | Full file | Main Instagram posting orchestrator |
| **Analyzer instantiation** | `post_reel_smart.py` | `__init__()` | ~Line 192700 | Creates `self._analyzer = ClaudeUIAnalyzer()` |
| **analyze_ui() wrapper** | `post_reel_smart.py` | `analyze_ui()` | Lines 192948-192956 | Delegates to `self._analyzer.analyze()` |
| **Main posting loop** | `post_reel_smart.py` | `post()` | Lines 192998-193192 | The vision-action loop calling dump_ui → analyze_ui → execute |
| **InstagramPoster adapter** | `posters/instagram_poster.py` | `InstagramPoster` | Lines 149929-150090 | Thin adapter wrapping SmartInstagramPoster with BasePoster interface |

### 1.4 Call Sites in TikTok Poster

| Component | File | Function/Method | Line Range (approx) | Description |
|-----------|------|-----------------|---------------------|-------------|
| **TikTokPoster class** | `posters/tiktok_poster.py` | `TikTokPoster` | Lines 150104-150691 | TikTok posting implementation |
| **Main posting loop** | `posters/tiktok_poster.py` | `post()` | Lines 150367-150504 | Claude-driven navigation loop |
| **UI Analysis call** | `posters/tiktok_poster.py` | within `post()` | Line 150452 | `action = self._analyze_ui(elements, caption)` |

### 1.5 Action Execution

**Instagram Action Execution:**
| Component | File | Function/Method | Line Range (approx) | Description |
|-----------|------|-----------------|---------------------|-------------|
| **Action Dispatch Table** | `post_reel_smart.py` | `_get_action_handlers()` | Lines 192800-192807 | Returns dict mapping action names to handler methods |
| **Tap Handler** | `post_reel_smart.py` | `_action_tap()` | ~Line 192803 (reference) | Executes tap at `elements[idx]['center']` |
| **Tap and Type Handler** | `post_reel_smart.py` | `_handle_tap_and_type()` | Not shown, separate method | Handles caption entry |
| **Action Execution in post()** | `post_reel_smart.py` | `post()` | Lines 193112-193141 | Dispatches action via handler table |

**TikTok Action Execution:**
| Component | File | Function/Method | Line Range (approx) | Description |
|-----------|------|-----------------|---------------------|-------------|
| **Execute Action** | `posters/tiktok_poster.py` | `_execute_action()` | Lines 150573-150623 | Switch-case style action execution |
| **Tap Execution** | `posters/tiktok_poster.py` | within `_execute_action()` | Lines 150577-150584 | Gets center from `elements[idx]`, calls `self._ui_controller.tap()` |

**Low-level UI Operations:**
| Component | File | Function/Method | Description |
|-----------|------|-----------------|-------------|
| **Tap** | `appium_ui_controller.py` | `tap(x, y)` | Executes `driver.tap([(x, y)])` |
| **Type Text** | `appium_ui_controller.py` | `type_text(text)` | Finds EditText elements, sends keys |
| **Swipe** | `appium_ui_controller.py` | `swipe(x1, y1, x2, y2)` | Executes swipe gesture |
| **Press Key** | `appium_ui_controller.py` | `press_key(keycode)` | Executes keycode press |

### 1.6 Flow Analysis Logging

| Component | File | Location | Line Range (approx) | Description |
|-----------|------|----------|---------------------|-------------|
| **Log Directory Setup** | `post_reel_smart.py` | `post()` | Lines 193028-193031 | Creates `flow_analysis/` dir, opens JSONL file |
| **Step Logging** | `post_reel_smart.py` | `post()` | Lines 193084-193103 | Writes step data after each analyze_ui call |
| **Success Logging** | `post_reel_smart.py` | `post()` | Lines 193119-193123 | Logs `{'outcome': 'SUCCESS', ...}` |
| **Failure Logging** | `post_reel_smart.py` | `post()` | Lines 193162-193166, 193175-193179 | Logs failure outcomes |
| **TikTok** | `posters/tiktok_poster.py` | N/A | N/A | **NO FLOW LOGGING IMPLEMENTED** |

**Flow Log Schema:**
```json
{
    "step": int,
    "timestamp": "YYYY-MM-DD HH:MM:SS",
    "account": str,
    "state": {
        "video_uploaded": bool,
        "caption_entered": bool,
        "share_clicked": bool
    },
    "ui_elements": [{"text": str, "desc": str, "bounds": str}, ...],
    "action": {
        "action": str,
        "element_index": int,
        "text": str,
        "reason": str,
        ...
    }
}
```

---

## Part 2: elementIndex Handling Analysis

### 2.1 Where elementIndex is Parsed from Model Output

| Location | File | Function | Line Range | Notes |
|----------|------|----------|------------|-------|
| **Instagram** | `claude_analyzer.py` | `parse_response()` | Lines 179358-179382 | Uses `json.loads()` on cleaned response text |
| **Instagram** | `claude_analyzer.py` | `analyze()` | Line 179463 | `result = self.parse_response(text)` |
| **TikTok** | `posters/tiktok_poster.py` | `_analyze_ui()` | Lines 150565-150569 | `action = json.loads(text)` with fallback |

### 2.2 Where elementIndex is Validated and/or Clamped

**Instagram (claude_analyzer.py lines 179464-179476):**
```python
# Validate element_index is within bounds
if "element_index" in result and result["element_index"] is not None:
    idx = result["element_index"]
    max_idx = len(elements) - 1
    if not isinstance(idx, int) or idx < 0 or idx > max_idx:
        print(f"  [INVALID INDEX] Model returned element_index={idx}, but valid range is 0-{max_idx}")
        if attempt < retries - 1:
            time.sleep(1)
            continue  # Retry
        # On final attempt, clamp to valid range instead of crashing
        if isinstance(idx, int):
            result["element_index"] = max(0, min(idx, max_idx))
            print(f"  [INDEX CLAMPED] Clamped to {result['element_index']}")
```

**TikTok (posters/tiktok_poster.py lines 150577-150584):**
```python
# In _execute_action()
if action_type == 'tap':
    idx = action.get('element_index', 0)
    if 0 <= idx < len(elements) and elements[idx].get('center'):
        x, y = elements[idx]['center']
        self._ui_controller.tap(x, y)
    else:
        print(f"  Invalid element index {idx}, skipping tap")
```

**Key Differences:**
| Aspect | Instagram | TikTok |
|--------|-----------|--------|
| Validation Location | In `analyze()` before returning | In `_execute_action()` at execution time |
| Retry on Invalid | Yes (up to 3 retries) | No |
| Clamping | Yes (on final attempt) | No (just skips) |
| Logging | Prints `[INVALID INDEX]` and `[INDEX CLAMPED]` | Prints "Invalid element index, skipping" |

### 2.3 What Value Goes Into Logs vs What is Actually Executed

**Critical Issue Identified:**

In Instagram (`post_reel_smart.py` lines 193084-193103):
```python
step_data = {
    ...
    'action': action  # <-- This is the RAW action from Claude
}
with open(flow_log_file, 'a') as f:
    f.write(json.dumps(step_data) + '\n')
```

The flow log captures the **raw action from Claude** (which may contain invalid `element_index`), NOT the validated/clamped value.

However, execution uses the **validated value** (clamping happens in `analyze()` before the action is returned).

**Timeline:**
1. `analyze_ui()` called → Claude returns `element_index=52` (invalid, max=49)
2. `ClaudeUIAnalyzer.analyze()` validates → clamps to 49
3. Returned action dict has `element_index=49`
4. Flow log writes action with `element_index=49` (clamped)
5. Execution uses `element_index=49`

Wait - re-reading the code, the clamping happens INSIDE `analyze()` BEFORE returning, so the logged value SHOULD match the executed value.

**However**, looking at flow_analysis logs showing `element_index=52` when `max=49` means:
1. Either validation wasn't active when that log was created
2. OR the log is capturing the action BEFORE clamping (which contradicts the code flow)

**Actual Issue from Logs:** The logs show invalid indices because:
- The validation code was added AFTER those logs were created
- Workers running old code before validation was implemented

---

## Part 3: Design Doc Outline for `docs/ui_navigation_flow.md`

### Proposed Structure:

```markdown
# UI Navigation Flow Documentation

## Overview

[One paragraph describing the overall flow]

## Architecture Diagram

┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Appium Driver  │───▶│  dump_ui()       │───▶│  UI Elements    │
│  (page_source)  │    │  (parse XML)     │    │  List[Dict]     │
└─────────────────┘    └──────────────────┘    └────────┬────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Action Dict    │◀───│  analyze()       │◀───│  format_elements│
│  {action, idx}  │    │  (Claude API)    │    │  + build_prompt │
└────────┬────────┘    └──────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Log Step       │───▶│  Execute Action  │───▶│  UI Controller  │
│  (flow_analysis)│    │  (dispatch)      │    │  (tap/type/etc) │
└─────────────────┘    └──────────────────┘    └─────────────────┘

## Main Functions (In Execution Order)

1. **dump_ui()** - Captures current UI state via Appium page_source
   - Location: `appium_ui_controller.py:dump_ui()`
   - Returns: `(elements: List[Dict], raw_xml: str)`

2. **format_elements()** / **_format_elements_for_claude()** - Formats elements for prompt
   - Location: `claude_analyzer.py:format_elements()` or `tiktok_poster.py:_format_elements_for_claude()`
   - Returns: `str` (text representation)

3. **build_prompt()** - Constructs full prompt with state and instructions
   - Location: `claude_analyzer.py:build_prompt()`
   - Returns: `str` (complete prompt)

4. **analyze()** / **_analyze_ui()** - Sends to Claude, parses response
   - Location: `claude_analyzer.py:analyze()` or `tiktok_poster.py:_analyze_ui()`
   - Returns: `Dict` (action specification)

5. **parse_response()** - Extracts JSON from Claude response
   - Location: `claude_analyzer.py:parse_response()`
   - Returns: `Dict` (parsed action)

6. **validate element_index** - Ensures index is within bounds
   - Location: `claude_analyzer.py:analyze()` (inline)
   - Behavior: Retry or clamp

7. **_execute_action()** / **action_handlers[action]()** - Executes the action
   - Location: `post_reel_smart.py:_get_action_handlers()` or `tiktok_poster.py:_execute_action()`
   - Behavior: Calls UI controller methods

8. **Log step** - Records step to flow_analysis/*.jsonl
   - Location: `post_reel_smart.py:post()` (inline)

## Platform Differences

| Aspect | Instagram | TikTok |
|--------|-----------|--------|
| Analyzer | `ClaudeUIAnalyzer` class | Inline in `TikTokPoster` |
| Prompt Location | `claude_analyzer.py:build_prompt()` | `TIKTOK_NAVIGATION_PROMPT` constant |
| Index Validation | Yes, with retry + clamp | Only at execution (skip invalid) |
| Flow Logging | Yes (`flow_analysis/*.jsonl`) | **Not implemented** |
| Loop Detection | Yes (`_track_action_for_loop_detection`) | **Not implemented** |
| Error Screenshot | Yes (`analyze_failure_screenshot`) | **Not implemented** |
| State Tracking | `video_uploaded`, `caption_entered`, `share_clicked` | Same |

## Error Handling

[Document error states, recovery mechanisms]

## Extending for New Platforms

[Document how to add a new platform poster]
```

---

## Part 4: Step-by-Step Investigation PLAN

### Phase 1: Deep Code Reading (2-3 hours)

**TODO 1.1:** Read the complete `claude_analyzer.py` file
- [ ] Trace the full `analyze()` flow
- [ ] Document all retry/validation logic paths
- [ ] Identify any model-specific handling (OpenAI vs Anthropic)

**TODO 1.2:** Read the complete `post_reel_smart.py` file
- [ ] Map the `post()` method's full control flow
- [ ] Document all action handlers
- [ ] Trace error detection and recovery paths

**TODO 1.3:** Read the complete `posters/tiktok_poster.py` file
- [ ] Compare structure to Instagram implementation
- [ ] Identify missing features (loop detection, flow logging, etc.)
- [ ] Document the `_analyze_ui()` inline implementation

**TODO 1.4:** Read `appium_ui_controller.py`
- [ ] Document all available UI operations
- [ ] Note any error handling in UI methods

### Phase 2: Log Analysis (1-2 hours)

**TODO 2.1:** Analyze flow_analysis/*.jsonl files
- [ ] Write script to extract all invalid element_index occurrences
- [ ] Correlate with successful vs failed outcomes
- [ ] Identify patterns in invalid indices (consistent hallucination patterns?)

**TODO 2.2:** Analyze runtime logs
- [ ] Search for `[INVALID INDEX]` and `[INDEX CLAMPED]` messages
- [ ] Correlate with flow_analysis logs by timestamp/account

**TODO 2.3:** Document findings
- [ ] Create summary of element_index issues
- [ ] Quantify: What % of steps have invalid indices?
- [ ] Which actions most commonly have invalid indices?

### Phase 3: Create Documentation (2-3 hours)

**TODO 3.1:** Create `docs/ui_navigation_flow.md`
- [ ] Write the architecture diagram (text-based)
- [ ] Document all main functions with one-line descriptions
- [ ] Create the platform differences table

**TODO 3.2:** Update `CLAUDE.md` if needed
- [ ] Add reference to new documentation
- [ ] Document any discovered best practices

**TODO 3.3:** Create `docs/flow_analysis_schema.md`
- [ ] Document the JSONL schema
- [ ] Provide example entries
- [ ] Document how to query/analyze logs

### Phase 4: Identify Refactoring Opportunities (1-2 hours)

**TODO 4.1:** Document inconsistencies between Instagram and TikTok
- [ ] Missing TikTok flow logging
- [ ] Missing TikTok loop detection
- [ ] Different validation approaches

**TODO 4.2:** Propose unified architecture
- [ ] Consider extracting `BaseUIAnalyzer` class
- [ ] Consider unified action execution pattern
- [ ] Consider unified flow logging

**TODO 4.3:** Create refactoring tickets/TODOs
- [ ] Prioritize based on impact
- [ ] Estimate effort for each

---

## Part 5: Concrete TODOs (Implementation Ready)

### Immediate Fixes (High Priority)

1. **Add flow logging to TikTokPoster**
   - File: `posters/tiktok_poster.py`
   - Copy flow logging pattern from `post_reel_smart.py:post()`
   - Estimated effort: 30 min

2. **Add element_index validation to TikTokPoster**
   - File: `posters/tiktok_poster.py`
   - Add validation in `_analyze_ui()` similar to `claude_analyzer.py`
   - Estimated effort: 30 min

3. **Add loop detection to TikTokPoster**
   - File: `posters/tiktok_poster.py`
   - Port `_track_action_for_loop_detection` and `_check_and_recover_from_loop`
   - Estimated effort: 1 hour

### Documentation TODOs

4. **Create `docs/ui_navigation_flow.md`**
   - Follow outline in Part 3
   - Include architecture diagram
   - Include platform comparison table
   - Estimated effort: 2 hours

5. **Create `docs/flow_analysis_schema.md`**
   - Document JSONL schema
   - Include example queries
   - Estimated effort: 1 hour

6. **Update `docs/modules.md`**
   - Add ClaudeUIAnalyzer documentation
   - Add AppiumUIController documentation
   - Estimated effort: 1 hour

### Refactoring TODOs (Lower Priority)

7. **Extract common UI analyzer interface**
   - Create `BaseUIAnalyzer` abstract class
   - Make `ClaudeUIAnalyzer` inherit from it
   - Create `TikTokUIAnalyzer` class
   - Estimated effort: 3-4 hours

8. **Unify action execution patterns**
   - Consider creating shared `ActionExecutor` class
   - Standardize action dispatch
   - Estimated effort: 2-3 hours

9. **Create flow logging utility class**
   - Extract `FlowLogger` class
   - Use in both Instagram and TikTok
   - Estimated effort: 1-2 hours

---

## Appendix: File Location Quick Reference

```
geelark-automation/
├── claude_analyzer.py           # ClaudeUIAnalyzer class (Instagram)
├── post_reel_smart.py           # SmartInstagramPoster (main Instagram logic)
├── appium_ui_controller.py      # Low-level Appium UI operations
├── device_connection.py         # Device connection management
├── posters/
│   ├── __init__.py              # Poster factory
│   ├── base_poster.py           # BasePoster interface + PostResult
│   ├── instagram_poster.py      # InstagramPoster adapter
│   └── tiktok_poster.py         # TikTokPoster implementation
├── flow_analysis/               # Step-by-step navigation logs
│   └── {account}_{timestamp}.jsonl
└── docs/
    └── (ui_navigation_flow.md)  # TO BE CREATED
```

---

## Summary

This plan provides:
1. **Complete mapping** of all UI decision pipeline components
2. **Detailed tracing** of elementIndex through parsing → validation → logging → execution
3. **Documentation outline** ready for implementation
4. **Prioritized TODO list** for fixes and improvements
5. **Platform comparison** highlighting Instagram vs TikTok differences

The key findings are:
- Instagram has robust validation, clamping, and logging
- TikTok is missing flow logging, loop detection, and proper validation
- The flow logs capture post-validation values, but logs showing invalid indices indicate older code without validation
