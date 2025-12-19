# Switch from Claude Sonnet API to OpenAI GPT-5 mini API

## Goal
Reduce API costs by 12x by switching from Claude Sonnet ($3/MTok) to GPT-5 mini ($0.25/MTok).

## Background
- Currently spending ~$20 per 127 successful posts
- ~2,200 tokens per API call (prompt + UI dump + caption)
- ~19 steps per successful post
- Using Claude Sonnet 4 via Anthropic SDK

## Requirements
1. Change ONLY the model/API - keep exact same prompt text
2. Modify claude_analyzer.py to use OpenAI SDK instead of Anthropic SDK
3. Modify post_reel_smart.py vision calls to use OpenAI vision API
4. Keep all logic identical - no prompt changes

## Technical Details Needed
- OpenAI Python SDK usage (openai library)
- GPT-5 mini model ID for API calls (likely "gpt-5-mini")
- Message format differences between Anthropic and OpenAI APIs
- Response structure differences (how to extract response text)
- Vision API differences for screenshot analysis

## Files to Modify
- claude_analyzer.py - main UI analysis API calls
- post_reel_smart.py - vision calls for failure screenshots

## API Differences to Handle
### Anthropic (current):
```python
client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=500,
    messages=[{"role": "user", "content": prompt}]
)
text = response.content[0].text
```

### OpenAI (target):
```python
client = openai.OpenAI()
response = client.chat.completions.create(
    model="gpt-5-mini",
    max_tokens=500,
    messages=[{"role": "user", "content": prompt}]
)
text = response.choices[0].message.content
```

## Success Criteria
- Same prompt produces equivalent quality responses
- Posting flow works identically
- Costs reduced to ~$1.67 per 127 posts (down from $20)
