"""
Claude UI Analyzer - AI-based UI analysis for Instagram automation.

This module encapsulates all Claude AI interactions for analyzing
UI elements and deciding next actions in the posting flow.

Optimized for cost efficiency with:
- Haiku 4.5 model
- UI element summarization (reduces prompt size by 70-80%)
- Response caching for repeated UI states
- Token usage logging and cost estimation
"""
import json
import time
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime

import openai

# Import config for model settings
try:
    from config import Config
    AI_MODEL = Config.AI_MODEL
    AI_MAX_TOKENS = Config.AI_MAX_TOKENS
    AI_INPUT_PRICE = Config.AI_INPUT_PRICE
    AI_OUTPUT_PRICE = Config.AI_OUTPUT_PRICE
except ImportError:
    # Fallback defaults
    AI_MODEL = "gpt-5-mini"
    AI_MAX_TOKENS = 300
    AI_INPUT_PRICE = 0.25
    AI_OUTPUT_PRICE = 2.0


class ClaudeUIAnalyzer:
    """Analyzes UI elements using Claude AI to decide next actions."""

    # Track total API usage for this session (class-level)
    total_input_tokens = 0
    total_output_tokens = 0
    total_calls = 0
    total_cache_hits = 0

    # Response cache (class-level for cross-instance sharing)
    _cache: Dict[str, Dict] = {}

    def __init__(self, model: str = None, max_tokens: int = None):
        """
        Initialize the analyzer.

        Args:
            model: Model to use (default: from config).
            max_tokens: Maximum tokens for response (default: from config).
        """
        # 10 second timeout to prevent hanging
        self.client = openai.OpenAI(timeout=10.0)
        self.model = model or AI_MODEL
        self.max_tokens = max_tokens or AI_MAX_TOKENS
        self.log_file = "api_calls.log"

    def summarize_elements(self, elements: List[Dict]) -> List[Dict]:
        """Summarize UI elements to reduce prompt size.

        Filters to key elements only and truncates text.

        Args:
            elements: Full list of UI elements.

        Returns:
            Summarized list with only essential info.
        """
        # Filter to clickable/editable or elements with key text
        key_elements = []
        for el in elements:
            text = el.get('text', '').lower()
            desc = el.get('desc', '').lower()

            # Include if clickable, editable, or has important text
            is_important = (
                el.get('clickable') or
                el.get('editable') or
                any(kw in text or kw in desc for kw in [
                    'create', 'next', 'share', 'post', 'reel', 'caption',
                    'profile', 'home', 'ok', 'done', 'gallery', 'video',
                    'write', 'add', 'new', 'story', 'back', 'close'
                ])
            )
            if is_important:
                key_elements.append(el)

        # Limit to top 25 elements
        key_elements = key_elements[:25]

        # Summarize each element
        summarized = []
        for i, el in enumerate(key_elements):
            summ = {
                'i': i,  # Shortened key
                't': el.get('text', '')[:50],  # Truncate text
                'd': el.get('desc', '')[:50],  # Truncate desc
                'b': el.get('bounds'),
                'c': el.get('center'),
                'click': el.get('clickable', False)
            }
            # Remove empty values to save tokens
            summarized.append({k: v for k, v in summ.items() if v})

        return summarized

    def get_cache_key(self, elements: List[Dict], caption: str, state: tuple) -> str:
        """Generate cache key from UI state.

        Args:
            elements: UI elements (will be hashed).
            caption: Caption text.
            state: Tuple of (video_uploaded, caption_entered, share_clicked).

        Returns:
            Cache key string.
        """
        # Hash the elements to create a compact key
        el_str = json.dumps(elements, sort_keys=True)
        el_hash = hashlib.md5(el_str.encode()).hexdigest()[:12]
        state_str = f"{state[0]}_{state[1]}_{state[2]}"
        return f"{el_hash}_{state_str}"

    def format_ui_elements(self, elements: List[Dict]) -> str:
        """Format UI elements into a compact text description for Claude.

        Args:
            elements: List of UI element dicts.

        Returns:
            Formatted string description of UI elements.
        """
        # Use summarized elements for smaller prompt
        summarized = self.summarize_elements(elements)

        ui_description = "UI elements:\n"
        for elem in summarized:
            parts = []
            if elem.get('t'):
                parts.append(f"'{elem['t']}'")
            if elem.get('d'):
                parts.append(f"desc='{elem['d']}'")
            if elem.get('click'):
                parts.append("CLICK")
            ui_description += f"{elem.get('i', '?')}. {elem.get('b', '')} {' | '.join(parts)}\n"
        return ui_description

    def build_prompt(
        self,
        elements: List[Dict],
        caption: str,
        video_uploaded: bool = False,
        caption_entered: bool = False,
        share_clicked: bool = False
    ) -> str:
        """Build a compact analysis prompt for Claude.

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

        # Compact prompt - reduced from ~2000 tokens to ~800
        prompt = f"""Post Reel to Instagram. State: video={video_uploaded}, caption_entered={caption_entered}, share_clicked={share_clicked}
Caption: "{caption[:100]}"

{ui_description}

Flow: Create/+ -> Reel -> Select video thumbnail -> Next -> Next -> Type caption -> Share -> Done

Rules:
- Tap Create/+ or Profile first to find it
- On gallery: tap VIDEO THUMBNAIL (top-left), not mode tabs
- See "Next"? Tap it
- Caption field visible & caption_entered=False? Use tap_and_type
- See "Share" & caption_entered=True? Tap Share
- "Sharing to Reels" + share_clicked=True? Return done
- Popup/dialog? Tap back or X to dismiss
- Stuck? Try back, home, open_instagram

Respond JSON only:
{{"action":"tap"|"tap_and_type"|"back"|"scroll_down"|"home"|"open_instagram"|"done","element_index":<int>,"text":"<if tap_and_type>","reason":"<brief>","video_selected":bool,"caption_entered":bool,"share_clicked":bool}}"""

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

        # Method 1: Try to extract JSON from markdown code block
        if "```json" in text:
            try:
                json_start = text.index("```json") + 7
                json_end = text.index("```", json_start)
                text = text[json_start:json_end].strip()
                return json.loads(text)
            except (ValueError, json.JSONDecodeError):
                pass

        # Method 2: Try generic code block
        if "```" in text:
            try:
                parts = text.split("```")
                for part in parts[1::2]:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("{"):
                        return json.loads(part)
            except (ValueError, json.JSONDecodeError):
                pass

        # Method 3: Find raw JSON object
        brace_start = text.find("{")
        if brace_start != -1:
            depth = 0
            for i, c in enumerate(text[brace_start:], brace_start):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[brace_start:i+1])
                        except json.JSONDecodeError:
                            pass
                        break

        # Method 4: Direct parse
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
        retries: int = 2  # Reduced from 3
    ) -> Dict[str, Any]:
        """Analyze UI elements and return the next action.

        Uses caching to avoid redundant API calls for repeated UI states.

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
        # Check cache first
        state = (video_uploaded, caption_entered, share_clicked)
        cache_key = self.get_cache_key(elements, caption, state)

        if cache_key in ClaudeUIAnalyzer._cache:
            ClaudeUIAnalyzer.total_cache_hits += 1
            print(f"  [CACHE HIT] Reusing cached response")
            return ClaudeUIAnalyzer._cache[cache_key]

        prompt = self.build_prompt(
            elements=elements,
            caption=caption,
            video_uploaded=video_uploaded,
            caption_entered=caption_entered,
            share_clicked=share_clicked
        )

        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_completion_tokens=self.max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )

                # Track token usage
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
                ClaudeUIAnalyzer.total_input_tokens += input_tokens
                ClaudeUIAnalyzer.total_output_tokens += output_tokens
                ClaudeUIAnalyzer.total_calls += 1

                # Calculate cost
                cost = (input_tokens / 1e6 * AI_INPUT_PRICE) + (output_tokens / 1e6 * AI_OUTPUT_PRICE)

                # Log API call
                with open(self.log_file, "a") as f:
                    f.write(f"{datetime.now().isoformat()}|{self.model}|{input_tokens}|{output_tokens}|${cost:.4f}|calls={ClaudeUIAnalyzer.total_calls}|cache_hits={ClaudeUIAnalyzer.total_cache_hits}\n")

                # Check for empty response
                if not response.choices:
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    raise ValueError("GPT returned empty response")

                text = response.choices[0].message.content.strip()

                if not text:
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    raise ValueError("GPT returned empty text")

                try:
                    result = self.parse_response(text)

                    # Cache successful response
                    ClaudeUIAnalyzer._cache[cache_key] = result

                    # Limit cache size
                    if len(ClaudeUIAnalyzer._cache) > 100:
                        # Remove oldest entries
                        keys = list(ClaudeUIAnalyzer._cache.keys())
                        for k in keys[:50]:
                            del ClaudeUIAnalyzer._cache[k]

                    return result
                except ValueError as e:
                    print(f"  [JSON PARSE ERROR] attempt {attempt+1}: {e}")
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    raise ValueError(f"JSON parse failed after {retries} attempts: {e}")

            except Exception as e:
                if attempt < retries - 1 and "rate" not in str(e).lower():
                    time.sleep(1)
                    continue
                raise

        raise ValueError(f"Failed to get valid response from GPT after {retries} attempts")

    @classmethod
    def get_session_stats(cls) -> Dict[str, Any]:
        """Get session statistics for API usage."""
        total_cost = (cls.total_input_tokens / 1e6 * AI_INPUT_PRICE) + \
                     (cls.total_output_tokens / 1e6 * AI_OUTPUT_PRICE)
        return {
            'total_calls': cls.total_calls,
            'total_cache_hits': cls.total_cache_hits,
            'total_input_tokens': cls.total_input_tokens,
            'total_output_tokens': cls.total_output_tokens,
            'estimated_cost': f"${total_cost:.4f}",
            'cache_hit_rate': f"{(cls.total_cache_hits / max(1, cls.total_calls + cls.total_cache_hits)) * 100:.1f}%"
        }

    @classmethod
    def clear_cache(cls):
        """Clear the response cache."""
        cls._cache.clear()

    @classmethod
    def reset_stats(cls):
        """Reset session statistics."""
        cls.total_input_tokens = 0
        cls.total_output_tokens = 0
        cls.total_calls = 0
        cls.total_cache_hits = 0


# Convenience function for backwards compatibility
def analyze_ui_for_instagram(
    elements: List[Dict],
    caption: str,
    video_uploaded: bool = False,
    caption_entered: bool = False,
    share_clicked: bool = False
) -> Dict[str, Any]:
    """Analyze UI elements for Instagram posting flow."""
    analyzer = ClaudeUIAnalyzer()
    return analyzer.analyze(
        elements=elements,
        caption=caption,
        video_uploaded=video_uploaded,
        caption_entered=caption_entered,
        share_clicked=share_clicked
    )
