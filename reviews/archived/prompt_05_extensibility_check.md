# Prompt 5 – Multi-Platform Architecture & Extensibility Check

## Objective
Validate the final multi-platform design (Instagram + TikTok, future YouTube Shorts) and ensure adding new platforms does not require touching orchestrator/worker logic beyond config + factory mapping.

## Instructions

1. Using the updated codebase (with BasePoster, InstagramPoster, TikTokPoster, factory, and platform in campaign configs), generate an updated architectural diagram that includes:
   - parallel_orchestrator, parallel_worker.
   - BasePoster, InstagramPoster, TikTokPoster, and a hypothetical YouTubeShortsPoster.
   - shared infra modules (Geelark client, DeviceConnectionManager, AppiumUIController, Claude navigator).

2. Analyze what changes are required to add a new platform (e.g., YouTube Shorts):
   - new poster class file,
   - one new entry in factory mapping,
   - new campaign config with "platform": "youtube_shorts".

3. Highlight any places where platform-specific branching still exists outside posters/ (e.g., if parallel_worker or infra code checks platform explicitly).

4. Recommend any final refactors needed to:
   - remove platform-specific logic from worker/orchestrator,
   - keep each platform's Claude prompts, UI flows, and error heuristics fully encapsulated.

## Expected Output
An updated diagram and a brief analysis confirming that the system is truly "plug-in" for new platforms, or listing the remaining hotspots that must be cleaned up to achieve that.

---

**Recommended sequence:** 1 → 2 → 3 → (implement Instagram adapter + factory + worker change) → 4 → (implement TikTokPoster) → 5.
