# 🤖 Zara Slack Assistant

AI-powered Slack assistant that monitors channels and suggests responses.

## Setup

1. Fork this repository
2. Deploy to Render.com (free)
3. Add environment variables:
   - SLACK_BOT_TOKEN
   - CLAUDE_API_KEY
   - USER_ID
4. Copy webhook URL
5. Add to Slack app Event Subscriptions

## Environment Variables
```
SLACK_BOT_TOKEN=xoxb-your-token-here
CLAUDE_API_KEY=sk-ant-api03-your-key-here
USER_ID=U02NX6HD7AS
```

## Features

- 24/7 channel monitoring
- AI-powered relevance filtering
- Smart notifications with suggested replies
- Priority scoring
- Rate limiting to avoid spam

## Tech Stack

- Python 3.11
- Flask
- Slack SDK
- Anthropic Claude API
- Deployed on Render.com (free tier)
