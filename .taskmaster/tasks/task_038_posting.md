# Task ID: 38

**Title:** Extract ClaudeUIAnalyzer from SmartInstagramPoster

**Status:** done

**Dependencies:** 6 ✓, 25 ✓, 37 ✓

**Priority:** high

**Description:** Create claude_analyzer.py with a ClaudeUIAnalyzer class that encapsulates all AI-based UI analysis logic, extracting the analyze_ui() method (~125 lines) from post_reel_smart.py that mixes prompt construction, Claude API calls, and JSON response parsing into a single class with a clean interface: analyze(elements, state) -> action_dict.

**Details:**

## Current State Analysis

The `SmartInstagramPoster.analyze_ui()` method in `post_reel_smart.py` (lines 539-663, ~125 lines) currently handles:

1. **UI Element Formatting** (lines 543-554):
   - Iterates through parsed UI elements
   - Builds a text description with bounds, center coords, text, desc, id, clickable status
   - Creates `ui_description` string for Claude

2. **Prompt Construction** (lines 556-612):
   - Builds a large multi-section prompt including:
     - Current posting state (video_uploaded, caption_entered, share_clicked)
     - Caption to post
     - UI element descriptions
     - Instagram posting flow instructions (8 steps)
     - JSON response format specification
     - Critical rules for action handling (~20 rules)

3. **Claude API Calls with Retry** (lines 615-663):
   - 3-attempt retry loop for transient errors
   - Uses `anthropic.Anthropic()` client
   - Model: `claude-sonnet-4-20250514`, max_tokens: 500
   - Handles empty responses
   - Parses markdown code blocks (```json)
   - JSON parsing with error handling

## Implementation Plan

### Step 1: Create claude_analyzer.py module

```python
"""
Claude UI Analyzer - AI-based UI analysis for Instagram posting automation.

Extracts UI analysis logic from SmartInstagramPoster for better separation of concerns.
"""

import json
import time
from dataclasses import dataclass
from typing import Optional
import anthropic

@dataclass
class PostingState:
    """Current state of the Instagram posting flow."""
    video_uploaded: bool = False
    caption_entered: bool = False
    share_clicked: bool = False
    caption: str = ""

@dataclass
class UIAction:
    """Parsed action from Claude's analysis."""
    action: str  # tap, tap_and_type, back, scroll_down, scroll_up, home, open_instagram, done
    element_index: Optional[int] = None
    text: Optional[str] = None
    reason: str = ""
    video_selected: bool = False
    caption_entered: bool = False
    share_clicked: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "UIAction":
        """Create UIAction from Claude's JSON response."""
        return cls(
            action=data.get("action", ""),
            element_index=data.get("element_index"),
            text=data.get("text"),
            reason=data.get("reason", ""),
            video_selected=data.get("video_selected", False),
            caption_entered=data.get("caption_entered", False),
            share_clicked=data.get("share_clicked", False),
        )

class ClaudeUIAnalyzer:
    """Handles AI-based UI analysis for Instagram posting automation."""

    # Default model configuration
    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    DEFAULT_MAX_TOKENS = 500
    DEFAULT_RETRIES = 3

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        retries: int = DEFAULT_RETRIES,
    ):
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.retries = retries

    def analyze(
        self,
        elements: list[dict],
        state: PostingState,
    ) -> UIAction:
        """
        Analyze UI elements and determine next action.

        Args:
            elements: List of UI element dicts with keys:
                - text, desc, id, bounds, center, clickable
            state: Current posting flow state

        Returns:
            UIAction with the next action to take

        Raises:
            ValueError: If Claude returns invalid/unparseable response after retries
        """
        ui_description = self._format_elements(elements)
        prompt = self._build_prompt(ui_description, state)
        response_json = self._call_claude(prompt)
        return UIAction.from_dict(response_json)

    def _format_elements(self, elements: list[dict]) -> str:
        """Format UI elements into a description string for Claude."""
        lines = ["Current UI elements:"]
        for i, elem in enumerate(elements):
            parts = []
            if elem.get("text"):
                parts.append(f'text="{elem["text"]}"')
            if elem.get("desc"):
                parts.append(f'desc="{elem["desc"]}"')
            if elem.get("id"):
                parts.append(f"id={elem['id']}")
            if elem.get("clickable"):
                parts.append("CLICKABLE")
            lines.append(
                f"{i}. {elem.get('bounds', '')} center={elem.get('center', '')} | {' | '.join(parts)}"
            )
        return "\n".join(lines)

    def _build_prompt(self, ui_description: str, state: PostingState) -> str:
        """Build the prompt for Claude analysis."""
        # Full prompt extracted from post_reel_smart.py lines 556-612
        return f"""You are controlling an Android phone to post a Reel to Instagram.

Current state:
- Video uploaded to phone: {state.video_uploaded}
- Caption entered: {state.caption_entered}
- Share button clicked: {state.share_clicked}
- Caption to post: "{state.caption}"

{ui_description}

Based on the UI elements, decide the next action to take.

Instagram posting flow:
1. Find and tap Create/+ button. IMPORTANT: On different Instagram versions:
   - Some have "Create" in bottom nav bar
   - Some have "Create New" in top left corner (only visible from Profile tab)
   - If you don't see Create, tap "Profile" tab first to find "Create New"
2. Select "Reel" option if a menu appears
3. Select the video from gallery (look for video thumbnails, usually most recent)
4. Tap "Next" to proceed to editing
5. Tap "Next" again to proceed to sharing
6. When you see the caption field ("Write a caption" or similar), return "type" action with the caption text
7. Tap "Share" to publish
8. Done when you see confirmation, "Sharing to Reels", or back on feed

Respond with JSON:
{{
    "action": "tap" | "tap_and_type" | "back" | "scroll_down" | "scroll_up" | "home" | "open_instagram" | "done",
    "element_index": <index of element to tap>,
    "text": "<text to type if action is tap_and_type>",
    "reason": "<brief explanation>",
    "video_selected": true/false,
    "caption_entered": true/false,
    "share_clicked": true/false
}}

CRITICAL RULES - NEVER GIVE UP:
- NEVER return "error". There is no error action. Always try to recover.
- If you see Play Store, Settings, or any non-Instagram app: return "home" to go back to home screen
- If you see home screen or launcher: return "open_instagram" to reopen Instagram
- If you see a popup, dialog, or unexpected screen: return "back" to dismiss it
- If you're lost or confused: return "back" and try again
- If you don't see Create button, tap Profile tab first
- Look for "Create New" in desc field (top left area, small button)
- Look for "Profile" in desc field (bottom nav, usually id=profile_tab)
- If you see "Reel" or "Create new reel" option, tap it
- If you see gallery thumbnails with video, tap the video
- If you see "Next" button anywhere, tap it
- IMPORTANT: When you see a caption field (text containing "Write a caption", "Add a caption", or similar placeholder) AND "Caption entered" is False, return action="tap_and_type" with the element_index of the caption field and text set to the caption
- CRITICAL: If "Caption entered: True" is shown above, DO NOT return tap_and_type! The caption is already typed. Just tap the Share button directly.
- Allow/OK buttons should be tapped for permissions
- IMPORTANT: Return "done" ONLY when Share button clicked is True AND you see "Sharing to Reels" confirmation
- If Share button clicked is False but you see "Sharing to Reels", that's from a previous post - ignore it and start the posting flow
- Set share_clicked=true when you tap the Share button
- CRITICAL OK BUTTON RULE: After caption has been entered (Caption entered: True), if you see an "OK" button visible on screen (text='OK' or desc='OK'), you MUST tap the OK button FIRST before tapping Next or Share. This OK button dismisses the keyboard or a dialog and must be tapped for Next/Share to work properly.

Only output JSON."""

    def _call_claude(self, prompt: str) -> dict:
        """Call Claude API with retry logic and parse JSON response."""
        for attempt in range(self.retries):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )

                # Check for empty response
                if not response.content:
                    if attempt < self.retries - 1:
                        time.sleep(1)
                        continue
                    raise ValueError("Claude returned empty response")

                text = response.content[0].text.strip()

                # Check for empty text
                if not text:
                    if attempt < self.retries - 1:
                        time.sleep(1)
                        continue
                    raise ValueError("Claude returned empty text")

                return self._parse_json_response(text, attempt)

            except json.JSONDecodeError as e:
                if attempt < self.retries - 1:
                    time.sleep(1)
                    continue
                raise ValueError(f"JSON parse failed after {self.retries} attempts: {e}")

            except Exception as e:
                if attempt < self.retries - 1 and "rate" not in str(e).lower():
                    time.sleep(1)
                    continue
                raise

        raise ValueError(f"Failed to get valid response from Claude after {self.retries} attempts")

    def _parse_json_response(self, text: str, attempt: int) -> dict:
        """Parse JSON from Claude's response, handling markdown code blocks."""
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"  [JSON PARSE ERROR] attempt {attempt+1}: {e}")
            print(f"  Raw response (full): {text}")
            raise
```

### Step 2: Update SmartInstagramPoster to use ClaudeUIAnalyzer

```python
# In post_reel_smart.py

from claude_analyzer import ClaudeUIAnalyzer, PostingState

class SmartInstagramPoster:
    def __init__(self, phone_name, system_port=8200, appium_url=None):
        self.client = GeelarkClient()
        self.ui_analyzer = ClaudeUIAnalyzer()  # Replace self.anthropic
        # ... rest of __init__

    def analyze_ui(self, elements, caption):
        """Use Claude to analyze UI and decide next action"""
        state = PostingState(
            video_uploaded=self.video_uploaded,
            caption_entered=self.caption_entered,
            share_clicked=self.share_clicked,
            caption=caption,
        )
        action = self.ui_analyzer.analyze(elements, state)
        return {
            "action": action.action,
            "element_index": action.element_index,
            "text": action.text,
            "reason": action.reason,
            "video_selected": action.video_selected,
            "caption_entered": action.caption_entered,
            "share_clicked": action.share_clicked,
        }
```

## Key Design Decisions

1. **Dataclasses for State and Actions**: Use `PostingState` and `UIAction` dataclasses for type safety and clear interfaces.

2. **Configurable Model/Tokens**: Allow customization of Claude model and token limits via constructor.

3. **Clean analyze() Interface**: Single entry point that takes elements and state, returns action.

4. **Backwards Compatibility**: The `analyze_ui()` method in SmartInstagramPoster delegates to ClaudeUIAnalyzer but returns the same dict format for minimal changes to calling code.

5. **Separation of Concerns**:
   - `_format_elements()`: UI element → text conversion
   - `_build_prompt()`: Prompt construction
   - `_call_claude()`: API call with retries
   - `_parse_json_response()`: JSON parsing

## Relationship to Existing vision.py

The existing `vision.py` module handles screenshot-based (image) analysis, while this new `claude_analyzer.py` handles UI hierarchy (XML dump) analysis. They serve complementary purposes:
- `vision.py`: Image → action (pixel-coordinate based)
- `claude_analyzer.py`: UI elements → action (element-index based)

**Test Strategy:**

## Test Strategy

### 1. Unit Test - Module imports successfully
```bash
python -c "from claude_analyzer import ClaudeUIAnalyzer, PostingState, UIAction; print('Import OK')"
```

### 2. Unit Test - ClaudeUIAnalyzer instantiation
```bash
python -c "
from claude_analyzer import ClaudeUIAnalyzer
analyzer = ClaudeUIAnalyzer()
assert analyzer.model == 'claude-sonnet-4-20250514'
assert analyzer.max_tokens == 500
assert analyzer.retries == 3
print('Instantiation OK')
"
```

### 3. Unit Test - PostingState dataclass
```bash
python -c "
from claude_analyzer import PostingState
state = PostingState(video_uploaded=True, caption='Test', caption_entered=False, share_clicked=False)
assert state.video_uploaded == True
assert state.caption == 'Test'
print('PostingState OK')
"
```

### 4. Unit Test - UIAction.from_dict() parsing
```bash
python -c "
from claude_analyzer import UIAction
data = {
    'action': 'tap',
    'element_index': 5,
    'reason': 'Tap Create button',
    'video_selected': False,
    'caption_entered': False,
    'share_clicked': False
}
action = UIAction.from_dict(data)
assert action.action == 'tap'
assert action.element_index == 5
assert action.reason == 'Tap Create button'
print('UIAction.from_dict OK')
"
```

### 5. Unit Test - _format_elements() output format
```bash
python -c "
from claude_analyzer import ClaudeUIAnalyzer
analyzer = ClaudeUIAnalyzer()
elements = [
    {'text': 'Home', 'desc': '', 'id': 'home_tab', 'bounds': '[0,0][100,100]', 'center': (50, 50), 'clickable': True},
    {'text': '', 'desc': 'Create', 'id': 'create_btn', 'bounds': '[100,0][200,100]', 'center': (150, 50), 'clickable': True},
]
result = analyzer._format_elements(elements)
assert 'text=\"Home\"' in result
assert 'desc=\"Create\"' in result
assert 'CLICKABLE' in result
assert 'center=' in result
print('_format_elements OK')
"
```

### 6. Unit Test - _parse_json_response() handles code blocks
```bash
python -c "
from claude_analyzer import ClaudeUIAnalyzer
analyzer = ClaudeUIAnalyzer()

# Test plain JSON
plain = '{\"action\": \"tap\", \"element_index\": 0}'
result = analyzer._parse_json_response(plain, 0)
assert result['action'] == 'tap'

# Test markdown code block
markdown = '\`\`\`json\n{\"action\": \"back\"}\n\`\`\`'
result = analyzer._parse_json_response(markdown, 0)
assert result['action'] == 'back'
print('_parse_json_response OK')
"
```

### 7. Unit Test - _build_prompt() includes all required sections
```bash
python -c "
from claude_analyzer import ClaudeUIAnalyzer, PostingState
analyzer = ClaudeUIAnalyzer()
state = PostingState(video_uploaded=True, caption='Test caption', caption_entered=False, share_clicked=False)
prompt = analyzer._build_prompt('UI elements here', state)
assert 'Video uploaded to phone: True' in prompt
assert 'Caption entered: False' in prompt
assert 'Test caption' in prompt
assert 'Instagram posting flow:' in prompt
assert 'CRITICAL RULES' in prompt
assert 'Only output JSON' in prompt
print('_build_prompt OK')
"
```

### 8. Integration Test - SmartInstagramPoster uses ClaudeUIAnalyzer
```bash
python -c "
from post_reel_smart import SmartInstagramPoster
poster = SmartInstagramPoster('test_phone')
assert hasattr(poster, 'ui_analyzer'), 'SmartInstagramPoster should have ui_analyzer attribute'
print('Integration OK')
"
```

### 9. Integration Test - Full analyze() call (requires ANTHROPIC_API_KEY)
```bash
python -c "
import os
if not os.getenv('ANTHROPIC_API_KEY'):
    print('SKIP: ANTHROPIC_API_KEY not set')
else:
    from claude_analyzer import ClaudeUIAnalyzer, PostingState
    analyzer = ClaudeUIAnalyzer()
    elements = [
        {'text': 'Home', 'desc': '', 'id': 'home_tab', 'bounds': '[0,1200][144,1280]', 'center': (72, 1240), 'clickable': True},
        {'text': '', 'desc': 'Create', 'id': 'creation_tab', 'bounds': '[288,1200][432,1280]', 'center': (360, 1240), 'clickable': True},
    ]
    state = PostingState(video_uploaded=False, caption='Test', caption_entered=False, share_clicked=False)
    action = analyzer.analyze(elements, state)
    assert action.action in ['tap', 'tap_and_type', 'back', 'scroll_down', 'scroll_up', 'home', 'open_instagram', 'done']
    print(f'Integration test passed: action={action.action}, reason={action.reason}')
"
```

### 10. Regression Test - Existing post_reel_smart.py behavior unchanged
```bash
# Run a quick dry test to ensure posting_scheduler still works
python posting_scheduler.py --status
```
