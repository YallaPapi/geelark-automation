# Prompt 4 – BasePoster / PostResult API & Error Handling Review

## Objective
Review the proposed BasePoster and PostResult APIs, plus error handling in the new InstagramPoster adapter, and identify any missing fields or anti-patterns given the system's scale (~100 posts/day across 100+ accounts).

## Instructions

1. Examine the BasePoster interface and PostResult dataclass: field names, responsibilities, and how they're used by the worker/orchestrator.

2. Analyze how Instagram errors are currently surfaced (last error properties, logs) and how they map into PostResult.

3. Suggest improvements, e.g.:
   - additional fields: retryable: bool, platform: str, account: str, raw_error: str | dict.
   - whether error classification (account vs infra, error_type) should live inside each poster or in a shared helper.
   - changes needed to keep parallel_worker logic simple and robust.

## Expected Output
A short review outlining good/bad practices in the poster API, with concrete recommendations you should apply before cloning the pattern for TikTokPoster and future platforms.
