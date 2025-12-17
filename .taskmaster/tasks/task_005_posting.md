# Task ID: 5

**Title:** Integrate proxy rotation before each post

**Status:** done

**Dependencies:** 1 ✓

**Priority:** medium

**Description:** Implement a simple proxy rotation step that hits the configured rotation URL before each posting job.

**Details:**

Implementation details:
- Add a `rotate_proxy()` function in a `network_utils.py` module.
- Use `requests.get(config.proxy_rotation_url, timeout=10)` or equivalent; treat non-2xx responses as failures.
- Add small backoff and retry (e.g. 3 attempts with exponential backoff) because this is a network call.
- Pseudo-code:
```python
import time, requests

def rotate_proxy(url: str, retries: int = 3, base_delay: float = 1.0) -> bool:
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=10)
            if 200 <= r.status_code < 300:
                return True
        except requests.RequestException:
            pass
        time.sleep(base_delay * (2 ** attempt))
    return False
```
- Hook `rotate_proxy()` into the main posting loop: call it before connecting to the Geelark device for each row.
- Log proxy rotation success/failure per job (but continue posting even if rotation fails if that is acceptable per requirements).

**Test Strategy:**

- Unit test `rotate_proxy` using a requests-mock server returning:
  - 200: expect success on first attempt.
  - 500: expect retries and final failure.
  - Network timeout: expect retries and final failure.
- In an integration-like test, configure a local HTTP server as rotation URL and verify that it is hit once per job in a multi-row CSV.
