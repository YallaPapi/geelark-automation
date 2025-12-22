"""
Claude UI Analyzer - AI-based UI analysis for Instagram automation.

This module encapsulates all Claude AI interactions for analyzing
UI elements and deciding next actions in the posting flow.

Extracted from SmartInstagramPoster to improve separation of concerns.
"""
import json
import time
from typing import List, Dict, Any, Optional

import anthropic


class ClaudeUIAnalyzer:
    """Analyzes UI elements using Claude AI to decide next actions."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", max_tokens: int = 500):
        """
        Initialize the analyzer.

        Args:
            model: Claude model to use for analysis.
            max_tokens: Maximum tokens for response.
        """
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens

    def format_ui_elements(self, elements: List[Dict]) -> str:
        """Format UI elements into a text description for Claude.

        Args:
            elements: List of UI element dicts with text, desc, id, bounds, center, clickable.

        Returns:
            Formatted string description of UI elements.
        """
        ui_description = "Current UI elements:\n"
        for i, elem in enumerate(elements):
            parts = []
            if elem.get('text'):
                parts.append(f"text=\"{elem['text']}\"")
            if elem.get('desc'):
                parts.append(f"desc=\"{elem['desc']}\"")
            if elem.get('id'):
                parts.append(f"id={elem['id']}")
            if elem.get('clickable'):
                parts.append("CLICKABLE")
            ui_description += f"{i}. {elem.get('bounds', '')} center={elem.get('center', '')} | {' | '.join(parts)}\n"
        return ui_description

    def build_prompt(
        self,
        elements: List[Dict],
        caption: str,
        video_uploaded: bool = False,
        caption_entered: bool = False,
        share_clicked: bool = False
    ) -> str:
        """Build the analysis prompt for Claude.

        Args:
            elements: UI elements to analyze.
            caption: Caption text for the post.
            video_uploaded: Whether video has been uploaded.
            caption_entered: Whether caption has been entered.
            share_clicked: Whether share button has been clicked.

        Returns:
            Complete prompt string for Claude.
        """
        ui_description = self.format_ui_elements(elements)

        prompt = f"""You are controlling an Android phone to post a Reel to Instagram.

Current state:
- Video uploaded to phone: {video_uploaded}
- Caption entered: {caption_entered}
- Share button clicked: {share_clicked}
- Caption to post: "{caption}"

{ui_description}

Based on the UI elements, decide the next action to take.

Instagram posting flow:
1. Find and tap Create/+ button. IMPORTANT: On different Instagram versions:
   - Some have "Create" in bottom nav bar
   - Some have "Create New" in top left corner (only visible from Profile tab)
   - If you don't see Create, tap "Profile" tab first to find "Create New"
2. Select "Reel" option if a menu appears (this is the initial type selection)
3. CRITICAL - Gallery/Video Selection Screen:
   - When you see "New reel" title and video thumbnails with POST/STORY/REEL tabs at bottom:
   - PRIORITY: Tap a VIDEO THUMBNAIL in the gallery, NOT the mode selector tabs at bottom
   - Select the FIRST/TOP-LEFT video thumbnail - it's the most recently uploaded
   - The POST/STORY/REEL tabs are mode selectors - if already selected, tapping them does nothing
   - To ensure REEL mode: tap POST, then STORY, then REEL (cycle through all to guarantee selection)
   - NEVER tap the same mode tab twice in a row - this causes infinite loops
4. AFTER VIDEO IS SELECTED - Find and tap "Next":
   - The "Next" button appears in the TOP-RIGHT corner after selecting a video
   - It may show as "Next", "→" (arrow), or a forward arrow icon
   - Look for text="Next" or desc="Next" in the UI elements
   - If you see a video preview taking up most of the screen, the "Next" button should be visible
   - If "Next" is not visible, the video may not be properly selected - tap a video thumbnail first
   - CRITICAL: Do NOT keep tapping mode tabs (POST/STORY/REEL) if video is already selected - tap NEXT instead
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

=== POPUP HANDLING (CRITICAL - HANDLE FIRST) ===

"SUGGESTED FOR YOU" POPUP (MUST DISMISS):
- If you see "Suggested for you" with profile cards showing "Follow" buttons
- This popup appears on the home feed and BLOCKS the Create button
- Look for an "X" button on the popup to close it
- Or tap OUTSIDE the popup area to dismiss it
- After dismissing, look for the Create/+ button to start posting

META VERIFIED POPUP (MUST DISMISS):
- If you see "Meta Verified", "Try Meta Verified", "$1", "Get verified", "verification badge", or subscription pricing
- This is an UPSELL POPUP that must be dismissed immediately
- Look for: "Not now", "Maybe later", "X" close button, or tap OUTSIDE the popup
- Return action="back" or tap the dismiss/close button to close it
- NEVER tap "Subscribe", "Get started", or any purchase button
- After dismissing, continue with the posting flow

CAMERA VIEW TRAP (ESCAPE IT):
- If you see a full-screen camera viewfinder with a large circular RECORD button at bottom
- And NO video thumbnail selected, NO "Next" button visible
- You are in CAMERA MODE and need to access the GALLERY instead
- LOOK FOR THE GALLERY ICON: There is almost always a small square thumbnail in the BOTTOM-LEFT corner
- This small square shows the most recent photo/video from the gallery - TAP IT to open the gallery
- The gallery icon is your PRIMARY escape route - look for it first!
- If the gallery icon is not visible, return action="back" to exit camera mode
- NEVER tap the large circular record button - we want to SELECT an existing video, not record new

STORIES VIEWING TRAP (ESCAPE IT):
- If you see someone's Story playing (fullscreen image/video with username at top, progress bar)
- Or if you see "To see" / "And" text overlays on a story
- Or if the screen has story navigation controls (tap left/right to navigate stories)
- You are VIEWING STORIES, not in the posting flow!
- Return action="back" to exit Stories and return to feed
- Then find the Create/+ button to start posting

WRONG SCREEN RECOVERY:
- If you see DMs, Search, Explore, Settings, Stories, or any screen unrelated to posting:
- Return action="back" repeatedly until you reach the home feed
- Then restart by tapping Create/+ button
- If stuck for 2+ actions on same screen, try action="home" then action="open_instagram"

=== STANDARD RULES ===

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

        return prompt

    def parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Claude's response into an action dict.

        Args:
            response_text: Raw response text from Claude.

        Returns:
            Parsed action dictionary.

        Raises:
            ValueError: If response cannot be parsed as JSON.
        """
        text = response_text.strip()

        # Handle markdown code blocks (anywhere in response, not just at start)
        if "```json" in text:
            # Extract content between ```json and ```
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                text = text[start:end].strip()
        elif "```" in text:
            # Generic code block
            parts = text.split("```")
            if len(parts) >= 3:
                text = parts[1].strip()
                if text.startswith("json"):
                    text = text[4:].strip()

        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in text (handles leading natural language)
        import re
        json_match = re.search(r'\{[^{}]*"action"[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Final fallback - try to find any valid JSON object
        brace_start = text.find('{')
        if brace_start >= 0:
            # Find matching closing brace
            depth = 0
            for i, c in enumerate(text[brace_start:]):
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        json_str = text[brace_start:brace_start + i + 1]
                        try:
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            pass
                        break

        raise ValueError(f"JSON parse failed: Could not extract valid JSON. Response: {text[:100]}")

    def analyze(
        self,
        elements: List[Dict],
        caption: str,
        video_uploaded: bool = False,
        caption_entered: bool = False,
        share_clicked: bool = False,
        retries: int = 3
    ) -> Dict[str, Any]:
        """Analyze UI elements and return the next action.

        Args:
            elements: UI elements to analyze.
            caption: Caption text for the post.
            video_uploaded: Whether video has been uploaded.
            caption_entered: Whether caption has been entered.
            share_clicked: Whether share button has been clicked.
            retries: Number of retry attempts on failure.

        Returns:
            Action dictionary with action, element_index, text, reason, etc.

        Raises:
            ValueError: If analysis fails after all retries.
        """
        prompt = self.build_prompt(
            elements=elements,
            caption=caption,
            video_uploaded=video_uploaded,
            caption_entered=caption_entered,
            share_clicked=share_clicked
        )

        for attempt in range(retries):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )

                # Check for empty response
                if not response.content:
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    raise ValueError("Claude returned empty response")

                text = response.content[0].text.strip()

                # Check for empty text
                if not text:
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    raise ValueError("Claude returned empty text")

                try:
                    return self.parse_response(text)
                except ValueError as e:
                    print(f"  [JSON PARSE ERROR] attempt {attempt+1}: {e}")
                    print(f"  Raw response (full): {text}")
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    raise ValueError(f"JSON parse failed after {retries} attempts: {e}")

            except Exception as e:
                if attempt < retries - 1 and "rate" not in str(e).lower():
                    time.sleep(1)
                    continue
                raise

        raise ValueError(f"Failed to get valid response from Claude after {retries} attempts")


# Convenience function for backwards compatibility
def analyze_ui_for_instagram(
    elements: List[Dict],
    caption: str,
    video_uploaded: bool = False,
    caption_entered: bool = False,
    share_clicked: bool = False
) -> Dict[str, Any]:
    """Analyze UI elements for Instagram posting flow.

    This is a convenience function that creates a ClaudeUIAnalyzer
    and performs analysis. For repeated calls, prefer creating
    a ClaudeUIAnalyzer instance directly.
    """
    analyzer = ClaudeUIAnalyzer()
    return analyzer.analyze(
        elements=elements,
        caption=caption,
        video_uploaded=video_uploaded,
        caption_entered=caption_entered,
        share_clicked=share_clicked
    )
