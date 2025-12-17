# Prompt 3 – Verify worker → poster selection is correct for Instagram

> You are reviewing `parallel_worker.py` and any poster-selection logic to ensure Instagram jobs are still routed through the correct, working Instagram poster.
>
> Inputs:
> - Diff of `parallel_worker.py` between `c260362` and `HEAD`.
> - Any new poster modules (`posters/instagram_poster.py`, TikTok poster, etc.).
>
> Goal: Confirm that **Instagram** jobs still use the same effective poster behavior as at `c260362`, and are not accidentally going through a TikTok-style path or a broken abstraction.
>
> Tasks:
> 1. Identify how the worker decides which poster to instantiate (platform, campaign name, or other flags).
> 2. Compare the poster used for Instagram at `c260362` to the one used at `HEAD`:
>    - Class name and module.
>    - Constructor parameters (device connection, AI client, config).
>    - Any new wrapper/base class that might modify behavior.
> 3. Check whether Instagram jobs now pass through any new shared "generic poster" logic that alters navigation, max steps, or completion detection.
>
> Output:
> - A short description of the current poster selection logic.
> - A recommendation (or patch) that:
>   - Ensures Instagram jobs use the **c260362-equivalent** SmartInstagramPoster path.
>   - Keeps TikTok jobs on their own posters.
>   - Avoids having IG jobs accidentally use TikTok navigation logic or shared logic that changed behavior.
