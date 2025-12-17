# UI Decision Pipeline Fix - Product Requirements Document

## Overview

This PRD describes the work needed to map, document, and fix the UI decision pipeline used for posting to Instagram and TikTok in the geelark-automation codebase. The core issue is that the AI UI agent returns invalid `element_index` values, causing navigation failures.

## Background

The pipeline follows: UI dump → Claude analysis → action execution → logging pattern. Currently:
- Instagram has robust validation, clamping, and logging
- TikTok is missing flow logging, loop detection, and proper validation
- Flow logs sometimes show invalid indices despite validation code

## Requirements

### Phase 1: Deep Code Reading and Analysis

#### Task 1.1: Analyze claude_analyzer.py
Read and document the complete `claude_analyzer.py` file:
- Trace the full `analyze()` flow
- Document all retry/validation logic paths
- Identify model-specific handling (OpenAI vs Anthropic)
- Document the `format_elements()` function
- Document the `build_prompt()` function
- Document the `parse_response()` function
- Document the index validation and clamping logic

#### Task 1.2: Analyze post_reel_smart.py
Read and document the complete `post_reel_smart.py` file:
- Map the `post()` method's full control flow
- Document all action handlers (`_get_action_handlers()`)
- Trace error detection and recovery paths
- Document the flow logging implementation
- Document the loop detection mechanism

#### Task 1.3: Analyze posters/tiktok_poster.py
Read and document the complete TikTok poster:
- Compare structure to Instagram implementation
- Document the inline `_analyze_ui()` implementation
- Document `_execute_action()` method
- Identify missing features (loop detection, flow logging)
- Document the `TIKTOK_NAVIGATION_PROMPT` constant

#### Task 1.4: Analyze appium_ui_controller.py
Read and document the UI controller:
- Document the `dump_ui()` method
- Document all available UI operations (tap, type_text, swipe, press_key)
- Note error handling in UI methods
- Document the element schema produced

### Phase 2: Log Analysis

#### Task 2.1: Analyze flow_analysis logs
Create a script to analyze flow_analysis/*.jsonl files:
- Extract all invalid element_index occurrences
- Correlate with successful vs failed outcomes
- Identify patterns in invalid indices
- Quantify: What % of steps have invalid indices?
- Document which actions most commonly have invalid indices

#### Task 2.2: Correlate runtime logs
Analyze worker logs for validation messages:
- Search for `[INVALID INDEX]` and `[INDEX CLAMPED]` messages
- Correlate with flow_analysis logs by timestamp/account
- Document findings

### Phase 3: TikTok Fixes (High Priority)

#### Task 3.1: Add flow logging to TikTokPoster
Port flow logging from `post_reel_smart.py:post()` to TikTok:
- Create flow_analysis directory handling
- Log step data with ui_elements and action
- Log success/failure outcomes
- Match the JSONL schema used by Instagram

#### Task 3.2: Add element_index validation to TikTokPoster
Add proper validation in `_analyze_ui()`:
- Validate element_index is an integer
- Validate element_index is within bounds (0 to len(elements)-1)
- Add retry logic on invalid index
- Add clamping on final attempt
- Add logging for `[INVALID INDEX]` and `[INDEX CLAMPED]`

#### Task 3.3: Add loop detection to TikTokPoster
Port loop detection from Instagram:
- Implement `_track_action_for_loop_detection()` equivalent
- Implement `_check_and_recover_from_loop()` equivalent
- Track (state, element_index, screen_signature) tuples
- Add recovery action when stuck

### Phase 4: Documentation

#### Task 4.1: Create docs/ui_navigation_flow.md
Create comprehensive documentation:
- Architecture diagram (text-based)
- Document all main functions in execution order
- Create platform differences table (Instagram vs TikTok)
- Document error handling
- Document how to extend for new platforms

#### Task 4.2: Create docs/flow_analysis_schema.md
Document the flow logging schema:
- Document JSONL schema with all fields
- Provide example entries
- Document how to query/analyze logs
- Include sample analysis queries

### Phase 5: Refactoring (Lower Priority)

#### Task 5.1: Extract common UI analyzer interface
Create a base class for analyzers:
- Create `BaseUIAnalyzer` abstract class
- Define common interface methods
- Refactor `ClaudeUIAnalyzer` to inherit from it
- Consider creating `TikTokUIAnalyzer` class

#### Task 5.2: Create FlowLogger utility class
Extract logging into reusable class:
- Create `FlowLogger` class
- Support JSONL format
- Support step logging, success, failure
- Use in both Instagram and TikTok posters

## Success Criteria

1. All code paths from UI dump to action execution are documented
2. TikTok has feature parity with Instagram for:
   - Flow logging
   - Index validation
   - Loop detection
3. Documentation exists in docs/ folder
4. Invalid element_index can never be executed (validation catches all cases)
5. Flow logs reflect validated actions actually executed

## Priority Order

1. Phase 1 (Code Reading) - Required to understand current state
2. Phase 3 (TikTok Fixes) - High priority fixes
3. Phase 2 (Log Analysis) - Validates fixes are working
4. Phase 4 (Documentation) - Required deliverable
5. Phase 5 (Refactoring) - Nice to have
