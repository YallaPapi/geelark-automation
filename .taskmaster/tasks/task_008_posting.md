# Task ID: 8

**Title:** Handle login prompts, captchas, and rate limits

**Status:** done

**Dependencies:** 6 ✓, 7 ✓

**Priority:** medium

**Description:** Add edge-case handling for Instagram login requests, captchas via 2Captcha, and rate-limit detection with backoff and retry.

**Details:**

Implementation details:
- Extend Claude prompts to explicitly ask it to identify when the screen shows:
  - A login screen.
  - A captcha challenge.
  - A rate-limit or "try again later" message.
- In `ClaudeNavigator`, allow an `Action.kind` of `"login_required"`, `"captcha"`, or `"rate_limited"` with additional metadata if needed.
- Implement logic in the orchestrator:
  - `login_required`: for MVP, either skip the job and log `login_required`, or if credentials are available in config, allow navigator-guided login by providing `username`/`password` in context.
  - `captcha`: integrate 2Captcha by:
    - Taking a screenshot of the captcha area (or whole screen) and sending to 2Captcha's image API.
    - Polling for the solved text and then issuing `type_text` or `tap` actions accordingly.
  - `rate_limited`: pause posting for a configurable cooldown (e.g. 10–30 minutes per account/device) before retrying the current job once; if still rate limited, mark as failed and move on.
- Pseudo-code snippet for 2Captcha integration:
```python
import requests, time

class CaptchaSolver:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def solve_image(self, image_bytes: bytes) -> str:
        # send
        resp = requests.post("http://2captcha.com/in.php", data={
            "key": self.api_key,
            "method": "base64",
            "body": base64.b64encode(image_bytes).decode('ascii'),
            "json": 1,
        })
        captcha_id = resp.json()["request"]
        # poll result
        for _ in range(24):
            r = requests.get("http://2captcha.com/res.php", params={
                "key": self.api_key,
                "action": "get",
                "id": captcha_id,
                "json": 1,
            })
            data = r.json()
            if data["status"] == 1:
                return data["request"]
            time.sleep(5)
        raise TimeoutError("Captcha solving timed out")
```
- Log all edge-case events distinctly so they can be monitored later.

**Test Strategy:**

- Unit test captcha solver using mocked 2Captcha endpoints with typical success and timeout responses.
- Extend fake `ClaudeNavigator` in tests to return `login_required`, `captcha`, and `rate_limited` actions and verify that the orchestrator:
  - For `login_required`, either skips or performs login based on test configuration.
  - For `captcha`, calls `CaptchaSolver.solve_image` and then attempts to type the solution.
  - For `rate_limited`, waits the configured cooldown and retries at most once.
- Manually induce a login-required state on a test account and confirm that it is handled as designed and logged appropriately.
