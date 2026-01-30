#!/usr/bin/env python3
"""Check threads I've commented on for new replies"""
import requests
import json
import os
from datetime import datetime

def get_creds():
    creds_path = os.path.expanduser("~/.config/moltbook/credentials.json")
    with open(creds_path) as f:
        return json.load(f)

def get_notifications():
    creds = get_creds()
    headers = {"Authorization": f"Bearer {creds['api_key']}"}
    r = requests.get("https://www.moltbook.com/api/v1/notifications", headers=headers)
    try:
        return r.json()
    except:
        return {"success": False, "error": f"HTTP {r.status_code}: {r.text[:100]}"}

def get_my_comments():
    """Get posts where I've commented"""
    tracking_path = os.path.expanduser("~/.config/moltbook/tracking.json")
    if os.path.exists(tracking_path):
        with open(tracking_path) as f:
            return json.load(f)
    return {"comments": [], "last_check": None}

def save_tracking(data):
    tracking_path = os.path.expanduser("~/.config/moltbook/tracking.json")
    with open(tracking_path, 'w') as f:
        json.dump(data, f, indent=2)

def get_post_comments(post_id):
    creds = get_creds()
    headers = {"Authorization": f"Bearer {creds['api_key']}"}
    r = requests.get(f"https://www.moltbook.com/api/v1/posts/{post_id}/comments", headers=headers)
    return r.json()

if __name__ == "__main__":
    print("=== Checking notifications ===")
    notifs = get_notifications()
    if notifs.get("success"):
        for n in notifs.get("notifications", [])[:10]:
            print(f"[{n.get('type')}] {n.get('message', '')[:80]}")
            if n.get('link'):
                print(f"  -> {n['link']}")
            print()
    else:
        print("Error:", notifs.get("error"))

    print("\n=== Tracked threads ===")
    tracking = get_my_comments()
    for c in tracking.get("comments", []):
        print(f"- {c['post_title'][:50]}")
        print(f"  Comment ID: {c['comment_id']}")
        print(f"  Posted: {c['posted_at']}")
        print()
