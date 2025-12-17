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
1. FIRST: Tap the + button (Create button) in the bottom nav bar
   - Look for "+" or "Create" or element with desc containing "create"
   - The + button is usually in the CENTER of the bottom navigation bar
   - If you see the home feed, the + button should be visible at the bottom

2. WHEN CREATE MENU APPEARS: Tap "Reel" IMMEDIATELY
   - You will see a popup/menu with options: Reel, Edits, Post, Story, etc.
   - Tap "Reel" directly - DO NOT tap Story, Post, or anything else
   - If tapping "Reel" does nothing (screen doesn't change), it means Reel is already selected - proceed to step 3

3. VIDEO SELECTION SCREEN ("New reel" title visible):
   - You should see video thumbnails in a gallery grid
   - Tap the FIRST video thumbnail (top-left, most recently uploaded)
   - IGNORE the POST/STORY/REEL tabs at the bottom - DO NOT tap them
   - If REEL tab is already highlighted, tapping it does nothing - just select a video instead

4. AFTER VIDEO IS SELECTED - Find and tap "Next":
   - The "Next" button appears in the TOP-RIGHT corner after selecting a video
   - It may show as "Next", "→" (arrow), or a forward arrow icon
   - Look for text="Next" or desc="Next" in the UI elements
   - If "Next" is not visible, the video may not be properly selected - tap a video thumbnail first

5. Tap "Next" again to proceed to sharing

6. When you see the caption field ("Write a caption" or similar), return "tap_and_type" action with the caption text

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

UNIVERSAL POPUP DISMISSAL:
- For ANY popup/dialog/overlay that appears: TAP OUTSIDE THE POPUP to dismiss it
- Most popups can be dismissed by tapping in a gray/dark area outside the popup content
- Tap coordinates around (100, 200) or (500, 200) - areas typically outside popup content
- If tapping outside doesn't work, look for "X", "Not now", "Got it", "OK" buttons
- Return action="back" as last resort to dismiss popups

"SUGGESTED FOR YOU" POPUP:
- If you see "Suggested for you" with profile cards showing "Follow" buttons
- TAP OUTSIDE the popup (on the darkened background) to dismiss
- Or tap the "X" button if visible

META VERIFIED POPUP:
- If you see "Meta Verified", "Try Meta Verified", "$1", "Get verified", or subscription pricing
- TAP OUTSIDE the popup to dismiss
- Or tap "Not now", "Maybe later", "X" if visible
- NEVER tap "Subscribe" or purchase buttons

"SWIPE TO ACCESS REELS" / TUTORIAL POPUPS:
- If you see tutorial text like "Swipe to easily access Reels and messages"
- Tap "Got it" button to dismiss
- Or TAP OUTSIDE the popup

"ARE YOU INTERESTED IN THIS AD?" POPUP:
- If you see ad feedback popup with "Not interested" / "Interested" options
- TAP OUTSIDE the popup to dismiss (on the darkened area)
- Or tap the X button if visible

"INTERACTING WITH FACEBOOK CONTENT" POPUP:
- If you see warning about Facebook content interaction
- Tap "OK" to dismiss and continue

CAMERA VIEW TRAP (ESCAPE IT):
- If you see full-screen camera with large circular RECORD button
- LOOK FOR GALLERY ICON: Small square thumbnail in BOTTOM-LEFT corner
- TAP the gallery icon to open gallery and select your video
- If no gallery icon visible, return action="back"
- NEVER tap the record button

STORIES VIEWING TRAP (ESCAPE IT):
- If you see someone's Story (fullscreen with username at top, progress bar)
- Return action="back" to exit Stories
- Then find the Create/+ button

WRONG APP / FACEBOOK LOGIN SCREEN:
- If you see Facebook login, Facebook app, or "Continue as [name]" with Facebook icon:
- This is NOT Instagram - return action="home" to go to home screen
- Then return action="open_instagram" to reopen Instagram app
- NEVER try to log in via Facebook - just escape and reopen Instagram

WRONG SCREEN RECOVERY:
- If on DMs, Search, Explore, Settings, or any unrelated screen:
- Return action="back" to get back to home feed
- Then tap Create/+ button

=== STANDARD RULES ===

CRITICAL - HOME FEED BEHAVIOR:
- If you see the Instagram HOME FEED (posts, stories at top, bottom nav with Home/Reels/Create/Search/Profile):
- DO NOT scroll the feed! DO NOT interact with posts/stories!
- IMMEDIATELY tap the + button (Create button) in the bottom nav bar
- The + button is your FIRST action from the home feed - always tap it first

CRITICAL - CREATE MENU BEHAVIOR:
- When the Create menu appears with Reel/Edits/Post/Story options:
- Tap "Reel" IMMEDIATELY and ONLY "Reel"
- NEVER tap Story, Post, or Edits
- If tapping Reel does nothing (already selected), proceed to select a video

CRITICAL RULES - NEVER GIVE UP:
- NEVER return "error". There is no error action. Always try to recover.
- If you see Play Store, Settings, or any non-Instagram app: return "home" to go back to home screen
- If you see home screen or launcher: return "open_instagram" to reopen Instagram
- If you see a popup/dialog: TAP OUTSIDE it to dismiss, or tap dismiss button, or return "back"
- If you're lost or confused: return "back" and try again
- If you see "Reel" option in a menu, tap it directly
- If you see gallery thumbnails with video, tap the FIRST video thumbnail
- If you see "Next" button, tap it
- IMPORTANT: When you see a caption field AND "Caption entered" is False, return action="tap_and_type"
- CRITICAL: If "Caption entered: True", DO NOT return tap_and_type! Just tap Share button.
- Allow/OK buttons should be tapped for permissions
- Return "done" ONLY when Share button clicked is True AND you see "Sharing to Reels" confirmation
- Set share_clicked=true when you tap the Share button

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

        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON parse failed: {e}. Response: {text[:100]}")

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
