"""
Vision module - uses Claude to analyze screenshots and determine actions
"""
import anthropic
import base64
import os


def encode_image(image_path):
    """Encode image to base64"""
    with open(image_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def analyze_screen(image_path, task_context):
    """
    Analyze screenshot and return action to take.

    Args:
        image_path: Path to screenshot image
        task_context: What we're trying to do (e.g., "post a video to Instagram")

    Returns:
        dict with:
            - action: "tap", "type", "swipe", "back", "done", "error"
            - x, y: coordinates for tap
            - text: text to type
            - message: explanation
    """
    client = anthropic.Anthropic()

    image_data = encode_image(image_path)

    prompt = f"""You are controlling an Android phone to {task_context}.

Look at this screenshot and tell me exactly what action to take next.

Respond in this exact JSON format:
{{
    "action": "tap" | "type" | "swipe" | "back" | "done" | "wait" | "error",
    "x": <x coordinate for tap>,
    "y": <y coordinate for tap>,
    "text": "<text to type if action is type>",
    "swipe": {{"x1": 0, "y1": 0, "x2": 0, "y2": 0}} if swipe,
    "message": "<brief explanation of what you see and why this action>"
}}

Important:
- Give exact pixel coordinates based on what you see
- If you see the target completed (e.g., post was shared), return "done"
- If something is wrong (error dialog, unexpected screen), return "error"
- If loading/processing, return "wait"
- Be precise with coordinates - aim for center of buttons/fields

Only output the JSON, nothing else."""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_data
                    }
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        }]
    )

    # Parse JSON response
    import json
    text = response.content[0].text.strip()

    # Handle markdown code blocks
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        return {
            "action": "error",
            "message": f"JSON parse error: {e}. Raw response: {text[:200]}"
        }


def analyze_for_instagram_post(image_path, caption, video_uploaded=False):
    """
    Specialized analyzer for Instagram posting flow.

    Args:
        image_path: Screenshot path
        caption: The caption to post
        video_uploaded: Whether video has been selected already
    """
    client = anthropic.Anthropic()

    image_data = encode_image(image_path)

    if not video_uploaded:
        context = """posting a Reel/video to Instagram.
Current step: Need to tap the + button to create a new post, then select Reel, then select the video from gallery."""
    else:
        context = f"""posting a Reel/video to Instagram.
The video has been selected. Now we need to:
1. Add this caption: {caption}
2. Tap Share/Post to publish

If you see a caption field, type the caption.
If you see Share/Post button and caption is entered, tap it."""

    prompt = f"""You are controlling an Android phone to {context}

Look at this screenshot and tell me exactly what action to take next.

Respond in this exact JSON format:
{{
    "action": "tap" | "type" | "swipe" | "back" | "done" | "wait" | "error",
    "x": <x coordinate for tap>,
    "y": <y coordinate for tap>,
    "text": "<text to type if action is type>",
    "swipe": {{"x1": 0, "y1": 0, "x2": 0, "y2": 0}},
    "message": "<brief explanation of what you see and why this action>",
    "video_selected": true/false (set true if video appears to be selected/uploaded)
}}

Common Instagram UI elements:
- + button (create): usually bottom center
- Reel option: after tapping +
- Gallery: shows recent videos
- Next button: top right
- Caption field: text input area
- Share button: top right on final screen

Only output the JSON, nothing else."""

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": image_data
                    }
                },
                {
                    "type": "text",
                    "text": prompt
                }
            ]
        }]
    )

    import json
    text = response.content[0].text.strip()

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        return {
            "action": "error",
            "message": f"JSON parse error: {e}. Raw response: {text[:200]}",
            "video_selected": False
        }


if __name__ == "__main__":
    print("Vision module loaded successfully")
    print("Usage: result = analyze_screen('screenshot.png', 'post video to Instagram')")
