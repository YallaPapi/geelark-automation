# Prompt 1 – Identify IG-breaking changes between c260362 and HEAD

> You are analyzing a Python automation repo that posts Instagram Reels and TikToks via Appium. Instagram reels worked at commit `c260362`, but at `HEAD` Instagram now fails with "Max steps reached" and gets stuck on the home feed (never tapping the `+` button).
>
> Goal: From the diffs between `c260362` and `HEAD`, extract all changes that can plausibly break **Instagram** navigation and posting, especially around AI-driven UI navigation.
>
> Files to analyze (diff: `c260362` vs `HEAD`):
> - `claude_analyzer.py`
> - `post_reel_smart.py`
> - `parallel_worker.py`
> - `device_connection.py`
> - `posters/instagram_poster.py` (if present)
> - Any shared utilities used by both Instagram and TikTok navigation.
>
> Tasks:
> 1. For each file, list concrete changes that could affect **Instagram-only** behavior, such as:
>    - Modifications to the Claude prompt / instructions for Instagram navigation.
>    - Changes in how UI elements are dumped or passed to the analyzer.
>    - Changes in how actions (`tap`, `swipe`, `tapAndType`, etc.) are interpreted and executed.
>    - New abstractions or shared logic that unify TikTok/Instagram but alter the previous IG assumptions (button texts, layout, flows).
> 2. For each such change, briefly explain *how* it could cause:
>    - The AI to never select the `+` button.
>    - The poster to loop until `max_steps` is hit without reaching the posting screen.
>
> Output:
> - A bullet list grouped by file:
>   - `File: claude_analyzer.py` → bullets of suspicious changes + why.
>   - `File: post_reel_smart.py` → bullets, etc.
> - Only include changes that plausibly impact Instagram; ignore pure TikTok additions that leave IG paths untouched.
