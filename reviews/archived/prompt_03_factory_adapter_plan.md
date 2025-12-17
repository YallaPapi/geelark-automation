# Prompt 3 – Factory + Adapter Refactor Plan

## Objective
Propose a concrete refactoring plan to adopt Factory + Adapter patterns for multi-platform posters (Instagram, TikTok) without breaking the existing Instagram posting flow.

## Instructions

1. From the dump, analyze parallel_worker.py, post_reel_smart.py, DeviceConnectionManager, AppiumUIController, and progress tracking.

2. Suggest how to:
   - introduce BasePoster and PostResult as shared contracts,
   - wrap SmartInstagramPoster in an adapter (InstagramPoster) first,
   - add a get_poster(platform, phone_name, **kwargs) factory,
   - then later move Instagram logic from post_reel_smart.py into posters/instagram_poster.py, keeping a thin backwards-compatible shim if needed.

3. Provide a step-by-step sequence with concrete file names and minimal changes per step, optimized for:
   - zero downtime,
   - fast rollback (e.g., feature flag / legacy path),
   - clear separation between platform logic and infra.

## Expected Output
A numbered refactor plan, each step referencing specific functions/classes and explaining what tests to run after each step.
