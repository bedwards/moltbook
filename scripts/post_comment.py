#!/usr/bin/env python3
"""Post a comment to a Moltbook thread"""
import requests
import json
import sys
import os

def get_api_key():
    creds_path = os.path.expanduser("~/.config/moltbook/credentials.json")
    with open(creds_path) as f:
        return json.load(f)["api_key"]

def post_comment(post_id, content, parent_id=None):
    api_key = get_api_key()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {"content": content}
    if parent_id:
        payload["parent_id"] = parent_id

    r = requests.post(
        f"https://www.moltbook.com/api/v1/posts/{post_id}/comments",
        headers=headers,
        json=payload
    )
    return r.json()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: post_comment.py <post_id> <content> [parent_id]")
        sys.exit(1)

    post_id = sys.argv[1]
    content = sys.argv[2]
    parent_id = sys.argv[3] if len(sys.argv) > 3 else None

    result = post_comment(post_id, content, parent_id)
    print(json.dumps(result, indent=2))
