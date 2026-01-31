#!/usr/bin/env python3
"""
Post a tweet to X.

Usage:
    python tweet.py "Your tweet text here"
    python tweet.py --dry-run "Preview tweet without posting"
    python tweet.py --pending  # Post first pending tweet from drafts
"""

import sys
import json
import re
from pathlib import Path

# Import from x_oauth2_setup
sys.path.insert(0, str(Path(__file__).parent))
from x_oauth2_setup import post_tweet, load_credentials

PENDING_TWEETS_PATH = Path.home() / "moltbook" / "drafts" / "pending-tweets.md"

def count_chars(text: str) -> int:
    """Count characters, accounting for URLs (23 chars each on X)."""
    # URLs count as 23 chars on X
    url_pattern = r'https?://\S+'
    urls = re.findall(url_pattern, text)
    text_without_urls = re.sub(url_pattern, '', text)
    return len(text_without_urls) + (23 * len(urls))

def parse_pending_tweets():
    """Parse pending tweets from markdown file."""
    if not PENDING_TWEETS_PATH.exists():
        return []

    content = PENDING_TWEETS_PATH.read_text()
    tweets = []

    # Split by --- and find code blocks
    sections = content.split('---')
    for section in sections:
        if '```' in section:
            # Extract tweet from code block
            match = re.search(r'```\n(.*?)\n```', section, re.DOTALL)
            if match:
                tweet_text = match.group(1).strip()
                # Extract header for context
                header_match = re.search(r'## (.+)', section)
                header = header_match.group(1) if header_match else "Unknown"
                tweets.append({
                    "text": tweet_text,
                    "header": header,
                    "chars": count_chars(tweet_text)
                })

    return tweets

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # Check auth first
    creds = load_credentials()
    if not creds.get("oauth2_token"):
        print("Not authenticated. Run: python x_oauth2_setup.py setup")
        sys.exit(1)

    if sys.argv[1] == "--pending":
        tweets = parse_pending_tweets()
        if not tweets:
            print("No pending tweets found.")
            sys.exit(1)

        print(f"Found {len(tweets)} pending tweets:\n")
        for i, t in enumerate(tweets, 1):
            print(f"{i}. [{t['chars']}/280] {t['header']}")
            print(f"   {t['text'][:60]}...")
            print()

        print("Post first tweet? (y/n): ", end="")
        if input().lower() == 'y':
            result = post_tweet(tweets[0]["text"])
            if result:
                print(f"\nPosted: {tweets[0]['header']}")
        return

    dry_run = "--dry-run" in sys.argv
    text_args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not text_args:
        print("No tweet text provided.")
        sys.exit(1)

    tweet_text = " ".join(text_args)
    char_count = count_chars(tweet_text)

    print(f"\nTweet ({char_count}/280 chars):")
    print("-" * 40)
    print(tweet_text)
    print("-" * 40)

    if char_count > 280:
        print(f"\nWARNING: Tweet exceeds 280 chars by {char_count - 280}")

    if dry_run:
        print("\n[DRY RUN - not posted]")
    else:
        print("\nPosting...")
        result = post_tweet(tweet_text)
        if result:
            print(f"Success! Tweet ID: {result.id}")

if __name__ == "__main__":
    main()
