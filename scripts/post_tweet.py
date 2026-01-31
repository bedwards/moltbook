#!/usr/bin/env python3
"""
Post a tweet to X using OAuth2.

Usage:
    python post_tweet.py "Your tweet text"
    python post_tweet.py --dry-run "Preview without posting"
"""

import json
import sys
import re
import requests
from pathlib import Path

CREDENTIALS_PATH = Path.home() / ".config" / "moltbook" / "x_credentials.json"

def load_credentials():
    with open(CREDENTIALS_PATH) as f:
        return json.load(f)

def save_credentials(creds):
    with open(CREDENTIALS_PATH, "w") as f:
        json.dump(creds, f, indent=2)

def refresh_token_if_needed(creds):
    """Refresh OAuth2 token if expired."""
    import time
    token_data = creds.get("oauth2_token", {})

    # Check if we have expiry info
    expires_at = token_data.get("expires_at")
    if expires_at and time.time() > expires_at - 300:  # 5 min buffer
        print("Token expired, refreshing...")
        refresh = token_data.get("refresh_token")
        if not refresh:
            print("No refresh token available. Re-run x_oauth2_setup.py setup")
            return None

        import base64
        client_id = creds["client_id"]
        client_secret = creds["client_secret"]
        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

        response = requests.post(
            "https://api.x.com/2/oauth2/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}"
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh
            }
        )

        if response.status_code == 200:
            new_token = response.json()
            new_token["expires_at"] = time.time() + new_token.get("expires_in", 7200)
            creds["oauth2_token"] = new_token
            save_credentials(creds)
            print("Token refreshed!")
            return new_token["access_token"]
        else:
            print(f"Refresh failed: {response.json()}")
            return None

    return token_data.get("access_token")

def count_chars(text: str) -> int:
    """Count characters, URLs count as 23 chars on X."""
    url_pattern = r'https?://\S+'
    urls = re.findall(url_pattern, text)
    text_without_urls = re.sub(url_pattern, '', text)
    return len(text_without_urls) + (23 * len(urls))

def post_tweet(text: str, dry_run: bool = False) -> dict:
    """Post a tweet to X."""
    char_count = count_chars(text)

    print(f"\nTweet ({char_count}/280 chars):")
    print("-" * 40)
    print(text)
    print("-" * 40)

    if char_count > 280:
        print(f"\nERROR: Tweet exceeds 280 chars by {char_count - 280}")
        return {"error": "too_long"}

    if dry_run:
        print("\n[DRY RUN - not posted]")
        return {"dry_run": True}

    creds = load_credentials()
    access_token = refresh_token_if_needed(creds)

    if not access_token:
        print("No valid access token. Run x_oauth2_setup.py setup")
        return {"error": "no_token"}

    response = requests.post(
        "https://api.x.com/2/tweets",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json={"text": text}
    )

    result = response.json()

    if response.status_code == 201:
        tweet_id = result["data"]["id"]
        url = f"https://x.com/brian_m_edwards/status/{tweet_id}"
        print(f"\nPosted! {url}")
        return {"success": True, "id": tweet_id, "url": url}
    else:
        print(f"\nError: {result}")
        return {"error": result}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    text_args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not text_args:
        print("No tweet text provided.")
        sys.exit(1)

    tweet_text = " ".join(text_args)
    result = post_tweet(tweet_text, dry_run=dry_run)

    if result.get("error"):
        sys.exit(1)
