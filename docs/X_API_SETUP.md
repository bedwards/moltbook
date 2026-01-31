# X API Setup for compost_heap

## Overview

Using OAuth2 PKCE for user context authentication. This allows posting tweets as @brian_m_edwards for the compost_heap persona.

**Status: CONFIGURED AND WORKING** (as of Jan 31, 2026)

## Prerequisites

1. X Developer account at https://console.x.com
2. Python 3.10+ with XDK: `pip install xdk`

## Setup Steps

### 1. Configure App at console.x.com

1. Go to https://console.x.com
2. Create a new app or select existing
3. Navigate to **Settings > User authentication settings**
4. Enable **OAuth 2.0**
5. Set **Type of App**: Web App (or Native App for public clients)
6. Set **Callback URI / Redirect URL**: `http://localhost:3000/callback`
7. Enable scopes: `tweet.read`, `tweet.write`, `users.read`, `offline.access`
8. Save changes
9. Copy the **Client ID** (and Client Secret if confidential client)

### 2. Update Credentials File

Edit `~/.config/moltbook/x_credentials.json`:

```json
{
  "consumer_key": "...",
  "consumer_secret": "...",
  "bearer_token": "...",
  "client_id": "YOUR_CLIENT_ID_FROM_CONSOLE",
  "client_secret": "YOUR_CLIENT_SECRET_IF_CONFIDENTIAL"
}
```

### 3. Run OAuth2 Flow

```bash
cd ~/moltbook/scripts

# Start authorization
python x_oauth2_setup.py setup

# Opens browser URL - authorize the app
# After redirect, copy the full callback URL

# Complete authorization
python x_oauth2_setup.py callback 'http://localhost:3000/callback?code=...'

# Test authentication
python x_oauth2_setup.py test
```

### 4. Post Tweets

```bash
# Post a tweet directly
python tweet.py "Your tweet text here"

# Preview without posting
python tweet.py --dry-run "Preview this tweet"

# Post from pending queue
python tweet.py --pending
```

## Scripts

| Script | Purpose |
|--------|---------|
| `x_oauth2_setup.py` | OAuth2 PKCE authentication flow |
| `post_tweet.py` | Post a single tweet |
| `publish_report.py` | Publish report to GitHub Pages + tweet |

## Workflow: Publishing Reports

When a new report is ready:

```bash
python ~/moltbook/scripts/publish_report.py report-YYYY-MM-DD.html "One punchy line for the tweet"
```

This will:
1. Git add/commit/push the report
2. Create a tinyurl
3. Post tweet with summary + link

## Token Management

- Access tokens expire after 2 hours
- Refresh tokens are stored and used automatically
- If refresh fails, re-run `x_oauth2_setup.py setup`

## Rate Limits

X API v2 rate limits (Free tier):
- 50 tweets per day
- 100 requests per 15 minutes for posting

Check status: `python x_oauth2_setup.py status` (TODO)

## Troubleshooting

### "Missing client_id"
Get client_id from https://console.x.com app settings.

### "Token expired"
Scripts auto-refresh. If that fails, re-authenticate:
```bash
python x_oauth2_setup.py setup
```

### "403 Forbidden"
Check that your app has the required scopes enabled at console.x.com.

### "Rate limit exceeded"
Wait 15 minutes or check remaining limits.

## Credentials Location

All credentials stored in: `~/.config/moltbook/x_credentials.json`

**IMPORTANT**: This file is gitignored. Never commit credentials.

## Architecture

```
console.x.com
     |
     v
OAuth2 PKCE Flow
     |
     v
~/.config/moltbook/x_credentials.json
     |
     v
XDK Client
     |
     v
X API v2
```

## XDK Documentation

- GitHub: https://github.com/xdevplatform/xdk-py
- Announcement: https://devcommunity.x.com/t/announcing-the-python-and-typescript-xdks-for-the-x-api-v2/250860
