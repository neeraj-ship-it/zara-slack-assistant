import os
import json
import time
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import anthropic
from datetime import datetime
import threading

# Initialize Flask app
app = Flask(__name__)

# Initialize clients
slack_client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN"))
claude_client = anthropic.Anthropic(api_key=os.environ.get("CLAUDE_API_KEY"))
YOUR_USER_ID = os.environ.get("USER_ID", "U02NX6HD7AS")

# Store for tracking
last_message_time = {}
notified_messages = set()

def analyze_message_with_claude(message_text, channel_name, user_name):
    """Analyze message relevance using Claude"""
    try:
        prompt = f"""You are analyzing a Slack message to determine if a marketing/ads professional should respond.

Channel: #{channel_name}
From: {user_name}
Message: "{message_text}"

User expertise: Marketing, Advertising, Content Strategy, Analytics, Campaign Management

Rate relevance 0-100 and provide a suggested reply if relevant.

Respond ONLY with valid JSON:
{{
  "score": 85,
  "reason": "Brief reason",
  "suggested_reply": "Professional response suggestion"
}}"""

        message = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = message.content[0].text
        # Clean response - remove markdown code blocks if present
        response_text = response_text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        analysis = json.loads(response_text)
        return analysis
    except Exception as e:
        print(f"Claude analysis error: {e}")
        return {"score": 0, "reason": "Analysis failed", "suggested_reply": ""}

def send_notification_dm(channel_id, channel_name, message_text, user_name, message_ts, analysis):
    """Send notification DM to user"""
    try:
        priority_emoji = "🔥" if analysis['score'] >= 80 else "⚡" if analysis['score'] >= 60 else "📌"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{priority_emoji} New Opportunity Detected"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Channel:* <#{channel_id}|{channel_name}>\n*From:* {user_name}\n*Priority Score:* {analysis['score']}/100\n*Time:* <!date^{int(float(message_ts))}^{{time}}|just now>"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*📝 Message:*\n{message_text[:500]}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*💡 Reason:*\n{analysis['reason']}"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*✨ Suggested Reply:*\n```{analysis['suggested_reply']}```"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📋 View Thread"
                        },
                        "url": f"https://stagedotin.slack.com/archives/{channel_id}/p{message_ts.replace('.', '')}"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Copy the suggested reply and paste it in the thread, or write your own response."
                    }
                ]
            }
        ]
        
        slack_client.chat_postMessage(
            channel=YOUR_USER_ID,
            text=f"New opportunity in #{channel_name}",
            blocks=blocks
        )
        
        print(f"✅ Notification sent for message in #{channel_name}")
        
    except SlackApiError as e:
        print(f"Error sending DM: {e.response['error']}")

def get_user_name(user_id):
    """Get user's display name"""
    try:
        user_info = slack_client.users_info(user=user_id)
        return user_info['user']['profile'].get('display_name') or user_info['user']['real_name']
    except:
        return "Unknown User"

def get_channel_name(channel_id):
    """Get channel name"""
    try:
        channel_info = slack_client.conversations_info(channel=channel_id)
        return channel_info['channel']['name']
    except:
        return "unknown-channel"

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack events"""
    data = request.json
    
    # Handle URL verification
    if data.get('type') == 'url_verification':
        return jsonify({'challenge': data['challenge']})
    
    # Handle events
    if data.get('type') == 'event_callback':
        event = data.get('event', {})
        
        # Only process message events
        if event.get('type') == 'message' and not event.get('subtype'):
            # Don't process own messages or bot messages
            if event.get('user') == YOUR_USER_ID or event.get('bot_id'):
                return jsonify({'status': 'ok'})
            
            channel_id = event.get('channel')
            message_text = event.get('text', '')
            user_id = event.get('user')
            message_ts = event.get('ts')
            
            # Create unique message ID
            message_id = f"{channel_id}_{message_ts}"
            
            # Skip if already notified
            if message_id in notified_messages:
                return jsonify({'status': 'ok'})
            
            # Rate limiting - don't process too frequently from same channel
            current_time = time.time()
            if channel_id in last_message_time:
                if current_time - last_message_time[channel_id] < 30:  # 30 seconds cooldown
                    return jsonify({'status': 'ok'})
            
            last_message_time[channel_id] = current_time
            
            # Process in background thread to not block Slack
            def process_message():
                try:
                    # Get context
                    channel_name = get_channel_name(channel_id)
                    user_name = get_user_name(user_id)
                    
                    # Analyze with Claude
                    analysis = analyze_message_with_claude(message_text, channel_name, user_name)
                    
                    # Send notification if relevant
                    if analysis['score'] >= 60:  # Threshold for notification
                        send_notification_dm(channel_id, channel_name, message_text, user_name, message_ts, analysis)
                        notified_messages.add(message_id)
                        
                        # Clean old notifications (keep last 1000)
                        if len(notified_messages) > 1000:
                            notified_messages.clear()
                    
                except Exception as e:
                    print(f"Error processing message: {e}")
            
            # Start background thread
            thread = threading.Thread(target=process_message)
            thread.daemon = True
            thread.start()
    
    return jsonify({'status': 'ok'})

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'bot_user_id': YOUR_USER_ID
    })

@app.route('/', methods=['GET'])
def home():
    """Home endpoint"""
    return """
    <h1>🤖 Zara Assistant is Running!</h1>
    <p>Slack bot is active and monitoring channels.</p>
    <p><a href="/health">Check Health Status</a></p>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Starting Zara Assistant on port {port}")
    print(f"👤 Monitoring for user: {YOUR_USER_ID}")
    app.run(host='0.0.0.0', port=port)
```

---

## 📄 **FILE 2: `requirements.txt`**
```
flask==3.0.0
slack-sdk==3.26.1
anthropic==0.18.1
gunicorn==21.2.0
```

---

## 📄 **FILE 3: `Procfile`**
```
web: gunicorn bot:app
```

---

## 📄 **FILE 4: `runtime.txt`**
```
python-3.11.7
