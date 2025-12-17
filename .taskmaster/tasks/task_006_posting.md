# Task ID: 6

**Title:** Implement Claude Vision client for Instagram UI navigation

**Status:** done

**Dependencies:** 1 ✓

**Priority:** high

**Description:** Create a module that sends device screenshots and minimal context to Claude Vision and receives structured navigation instructions for the Instagram posting flow.

**Details:**

Implementation details:
- Use the official Anthropic Python SDK (`anthropic` package) and Claude Vision model.
- Define a `ClaudeNavigator` class with:
  - `plan_next_action(screenshot_bytes: bytes, context: dict) -> Action` where `Action` is a dataclass describing an operation such as `tap(x,y)`, `type(text)`, `wait(seconds)`, `verify_posted`.
- Provide a system prompt that explains the device context (Android Instagram app on a cloud phone), the goal (post a Reel/video with a given caption), and a JSON schema for response.
- Example pseudo-code:
```python
from anthropic import Anthropic
import base64, json

@dataclass
class Action:
    kind: str  # 'tap', 'type', 'wait', 'done', 'error'
    x: int | None = None
    y: int | None = None
    text: str | None = None
    seconds: float | None = None

class ClaudeNavigator:
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)

    def plan_next_action(self, screenshot_bytes: bytes, context: dict) -> Action:
        img_b64 = base64.b64encode(screenshot_bytes).decode('ascii')
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
                    },
                    {
                        "type": "text",
                        "text": json.dumps(context),
                    },
                ],
            }
        ]
        resp = self.client.messages.create(
            model="claude-3-5-sonnet",  # example vision-capable model
            max_tokens=512,
            messages=messages,
            system="You control an Android Instagram app. Respond ONLY with a JSON object describing the next action to create and publish a video post.",
        )
        action_dict = json.loads(resp.content[0].text)
        return Action(**action_dict)
```
- The `context` should include the current step: e.g. `{"step": "open_plus", "caption": "..."}`.
- Keep actions atomic and loop until `kind == 'done'` or an error is detected.

**Test Strategy:**

- Unit test `ClaudeNavigator` parsing: mock Anthropic client responses with known JSON and ensure `Action` is constructed correctly.
- Add validation on returned actions (e.g. coordinates within screen bounds, non-empty `text` for `type` actions) and test these validators.
- For manual testing, feed screenshots of Instagram app (from a real device) and confirm that the model returns sensible next-step actions by logging them without executing on device.
