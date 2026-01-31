#!/usr/bin/env python3
"""X (Twitter) posting tools for compost_heap"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
import requests
from requests_oauthlib import OAuth1

# Credentials path
CREDS_PATH = Path.home() / ".config/moltbook/x_credentials.json"
POSTED_PATH = Path.home() / ".config/moltbook/x_posted.json"

def load_credentials():
    """Load X API credentials"""
    if not CREDS_PATH.exists():
        print(f"Error: No credentials found at {CREDS_PATH}")
        sys.exit(1)

    with open(CREDS_PATH) as f:
        return json.load(f)

def get_oauth():
    """Get OAuth1 auth object for user-context requests"""
    creds = load_credentials()
    return OAuth1(
        creds["consumer_key"],
        creds["consumer_secret"],
        creds.get("access_token"),
        creds.get("access_token_secret")
    )

def get_bearer_auth():
    """Get bearer token auth for app-context requests"""
    creds = load_credentials()
    return {"Authorization": f"Bearer {creds['bearer_token']}"}

def load_posted():
    """Load history of posted tweets"""
    if POSTED_PATH.exists():
        with open(POSTED_PATH) as f:
            return json.load(f)
    return {"tweets": []}

def save_posted(data):
    """Save posted tweets history"""
    with open(POSTED_PATH, 'w') as f:
        json.dump(data, f, indent=2)

def post_tweet(text: str, dry_run: bool = False) -> dict:
    """Post a tweet using OAuth1 (requires access token/secret)

    Args:
        text: Tweet content (max 280 chars)
        dry_run: If True, just print what would be posted

    Returns:
        API response dict
    """
    if len(text) > 280:
        print(f"Error: Tweet too long ({len(text)} chars, max 280)")
        return {"error": "too_long"}

    if dry_run:
        print(f"[DRY RUN] Would post ({len(text)} chars):")
        print(text)
        return {"dry_run": True}

    creds = load_credentials()
    if not creds.get("access_token") or not creds.get("access_token_secret"):
        print("Error: access_token and access_token_secret required for posting")
        print("Generate them in X Developer Portal under 'Keys and Tokens'")
        return {"error": "missing_access_tokens"}

    oauth = get_oauth()
    url = "https://api.x.com/2/tweets"

    resp = requests.post(url, auth=oauth, json={"text": text})

    if resp.status_code == 201:
        result = resp.json()
        # Log the post
        posted = load_posted()
        posted["tweets"].append({
            "text": text,
            "posted_at": datetime.now().isoformat(),
            "tweet_id": result.get("data", {}).get("id")
        })
        save_posted(posted)
        print(f"Posted: {text[:50]}...")
        return result
    else:
        print(f"Error {resp.status_code}: {resp.text}")
        return {"error": resp.status_code, "detail": resp.text}

def get_rate_limit_status():
    """Check rate limit status using bearer token (doesn't require user auth)"""
    headers = get_bearer_auth()

    # Check rate limits endpoint
    url = "https://api.x.com/2/users/me"
    resp = requests.get(url, headers=headers)

    if resp.status_code == 200:
        print("Bearer token: Valid")
        # Check rate limit headers
        remaining = resp.headers.get("x-rate-limit-remaining", "?")
        reset = resp.headers.get("x-rate-limit-reset", "?")
        print(f"Rate limit remaining: {remaining}")
        if reset != "?":
            from datetime import datetime
            reset_time = datetime.fromtimestamp(int(reset))
            print(f"Resets at: {reset_time}")
        return {"status": "ok"}
    elif resp.status_code == 401:
        print("Bearer token: Invalid or expired")
        return {"error": "invalid_bearer"}
    else:
        print(f"Status check returned {resp.status_code}: {resp.text}")
        return {"error": resp.status_code}

def check_access_tokens():
    """Check if we have valid access tokens for posting"""
    creds = load_credentials()
    if not creds.get("access_token") or not creds.get("access_token_secret"):
        print("Missing access_token and/or access_token_secret")
        print("\nTo post tweets, you need to generate these in X Developer Portal:")
        print("1. Go to your app in developer.x.com")
        print("2. Click 'Keys and Tokens'")
        print("3. Under 'Authentication Tokens', generate Access Token and Secret")
        print("4. Add them to ~/.config/moltbook/x_credentials.json")
        return False

    # Test the tokens
    oauth = get_oauth()
    resp = requests.get("https://api.x.com/2/users/me", auth=oauth)
    if resp.status_code == 200:
        user = resp.json().get("data", {})
        print(f"Access tokens valid! Logged in as: @{user.get('username')}")
        return True
    else:
        print(f"Access tokens invalid: {resp.status_code}")
        return False

def shorten_url(url: str) -> str:
    """Shorten URL using TinyURL"""
    import requests
    try:
        resp = requests.get(f"https://tinyurl.com/api-create.php?url={url}")
        if resp.status_code == 200:
            return resp.text
    except:
        pass
    return url

def format_post_tweet(teaser: str, url: str) -> str:
    """Format a tweet for a new post

    Args:
        teaser: One line teaser
        url: Full URL to shorten
    """
    short_url = shorten_url(url)

    # Calculate available space
    url_len = len(short_url)
    available = 280 - url_len - 2  # 2 for newlines

    # Use teaser if it fits, otherwise truncate
    if len(teaser) <= available:
        text = teaser
    else:
        text = teaser[:available-3] + "..."

    return f"{text}\n\n{short_url}"

def format_report_tweet(mood: str, url: str) -> str:
    """Format a tweet for a new report"""
    short_url = shorten_url(url)
    available = 280 - len(short_url) - 2

    if len(mood) <= available:
        text = mood
    else:
        text = mood[:available-3] + "..."

    return f"{text}\n\n{short_url}"

def batch_post(tweets: list, delay_seconds: int = 120, dry_run: bool = True):
    """Post multiple tweets with delay between them

    Free tier: ~50 tweets per day, recommend spacing 2+ minutes apart
    """
    print(f"Batch posting {len(tweets)} tweets with {delay_seconds}s delay")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()

    for i, tweet in enumerate(tweets):
        print(f"[{i+1}/{len(tweets)}]")
        post_tweet(tweet, dry_run=dry_run)

        if i < len(tweets) - 1:
            if not dry_run:
                print(f"Waiting {delay_seconds}s...")
                time.sleep(delay_seconds)
            else:
                print(f"[Would wait {delay_seconds}s]")
        print()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="X posting tools for compost_heap")
    parser.add_argument("command", choices=["status", "post", "test"],
                       help="Command to run")
    parser.add_argument("--text", "-t", help="Tweet text (for post command)")
    parser.add_argument("--dry-run", "-n", action="store_true",
                       help="Don't actually post")

    args = parser.parse_args()

    if args.command == "status":
        get_rate_limit_status()
    elif args.command == "post":
        if not args.text:
            print("Error: --text required for post command")
            sys.exit(1)
        post_tweet(args.text, dry_run=args.dry_run)
    elif args.command == "test":
        print("Testing credentials...")
        get_rate_limit_status()
