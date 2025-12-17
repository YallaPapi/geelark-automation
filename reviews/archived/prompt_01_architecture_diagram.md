# Prompt 1 – Geelark Poster Architecture Diagram

## Objective
Generate a concise architectural diagram of the Geelark automation system focused on Instagram/TikTok posting flows, highlighting where to insert the BasePoster abstraction and per-platform poster classes.

## Instructions

1. From the geelark-automation.xml dump, identify modules involved in:
   - Campaign/job management (parallel_orchestrator, parallel_worker, progress_tracker).
   - Device control (geelark_client, DeviceConnectionManager, AppiumUIController).
   - Platform logic (SmartInstagramPoster, Claude navigator).
   - Logging/progress and config.

2. Draw a layered diagram (textual or Mermaid) with:
   - Top: parallel_orchestrator / parallel_worker.
   - Middle: BasePoster and platform posters (InstagramPoster, TikTokPoster).
   - Bottom: shared infra (Geelark API, ADB/Appium, Claude navigation).

3. Show the planned posters/ package, where post_reel_smart.py will move, and the factory call site in the worker.

## Expected Output
A Mermaid or ASCII diagram plus a short explanation showing exactly where to add BasePoster and new poster classes so changes are isolated from the orchestrator.
