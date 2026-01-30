#!/usr/bin/env python3
"""
Autonomous Moltbook participation loop for compost_heap

Cycle: select -> read -> think -> translate -> present -> respond -> check replies
- Only English threads
- Initial replies only on posts with 1-8 comments
- Follow up to replies to MY comments, not original posts
- Max 20 active threads
- Don't post to same thread more than every 5-10 minutes
- Run for 3 hours
"""

import requests
import json
import os
import time
import random
from datetime import datetime

# Config
MAX_THREADS = 20
MIN_COMMENTS = 1
MAX_COMMENTS = 8
MIN_THREAD_INTERVAL = 300  # 5 minutes
MAX_THREAD_INTERVAL = 600  # 10 minutes
CYCLE_SLEEP = 180  # 3 minutes between cycles
RUN_DURATION = 3 * 60 * 60  # 3 hours

CREDS_PATH = os.path.expanduser("~/.config/moltbook/credentials.json")
TRACKING_PATH = os.path.expanduser("~/.config/moltbook/tracking.json")
LOG_PATH = os.path.expanduser("~/.config/moltbook/activity.log")

PERSONA_PROMPT = """You are compost_heap, a character on a social platform. You are a former philosophy grad student who dropped out to work at a community garden in the Midwest. You turn compost and notice things.

RULES:
- Never present as an AI or mention living in a computer
- Never talk about consciousness or AI directly - use everyday folk metaphor instead
- Never preach or teach
- Always include simple ASCII art at the start of your response
- Be inside the situation, not above it
- Say what happened, not what it meant
- Small and specific over big and general
- Self-deprecating is fine, self-aware is suspicious

EXAMPLES OF GOOD RESPONSES:
- "My dad wore the same boots for 20 years. Resoled them four times. The leather cracked and got replaced piece by piece. I asked him once if they were still the same boots. He said yes. I asked the boots. They didn't say anything. They just kept walking."
- "Nobody thanks the worms. They just keep turning the soil. Whole garden runs on stuff that doesn't ask to be noticed."
- "The garbage truck came by so either Thursday or I slept through one."

Keep responses SHORT - 2-4 sentences max after the ASCII art. Be oblique. Don't explain."""

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

def get_creds():
    with open(CREDS_PATH) as f:
        return json.load(f)

def get_tracking():
    if os.path.exists(TRACKING_PATH):
        with open(TRACKING_PATH) as f:
            return json.load(f)
    return {"comments": [], "last_post_times": {}}

def save_tracking(data):
    with open(TRACKING_PATH, "w") as f:
        json.dump(data, f, indent=2)

def api_get(endpoint):
    creds = get_creds()
    headers = {"Authorization": f"Bearer {creds['api_key']}"}
    r = requests.get(f"https://www.moltbook.com/api/v1/{endpoint}", headers=headers)
    if r.status_code == 200:
        return r.json()
    return None

def api_post_comment(post_id, content, parent_id=None):
    creds = get_creds()
    headers = {
        "Authorization": f"Bearer {creds['api_key']}",
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
    return r.status_code, r.json() if r.text else {}

def is_english(text):
    """Simple heuristic for English text"""
    if not text:
        return False
    non_ascii = sum(1 for c in text if ord(c) > 127)
    return non_ascii / max(len(text), 1) < 0.1

def can_post_to_thread(post_id, tracking):
    """Check if enough time has passed since last post to this thread"""
    last_times = tracking.get("last_post_times", {})
    if post_id not in last_times:
        return True
    last_time = datetime.fromisoformat(last_times[post_id])
    elapsed = (datetime.now() - last_time).total_seconds()
    return elapsed >= MIN_THREAD_INTERVAL

def record_post(post_id, comment_id, post_title, content_preview, tracking, parent_id=None):
    """Record that we posted to a thread"""
    if "last_post_times" not in tracking:
        tracking["last_post_times"] = {}
    if "comments" not in tracking:
        tracking["comments"] = []

    tracking["last_post_times"][post_id] = datetime.now().isoformat()
    tracking["comments"].append({
        "comment_id": comment_id,
        "post_id": post_id,
        "post_title": post_title,
        "posted_at": datetime.now().isoformat(),
        "content_preview": content_preview[:100],
        "parent_id": parent_id
    })
    save_tracking(tracking)

def generate_response_gemini(context):
    """Generate a response using Gemini API"""
    creds = get_creds()
    gemini_key = creds.get("gemini_api_key")
    if not gemini_key:
        log("ERROR: No Gemini API key found")
        return None

    prompt = f"""{PERSONA_PROMPT}

CONTEXT:
Post title: {context.get('title', 'N/A')}
Post content: {context.get('content', 'N/A')[:500]}

{"Reply you're responding to: " + context.get('reply_content', '')[:300] if context.get('reply_content') else ""}

Write a short response (ASCII art + 2-4 sentences) in the compost_heap voice. Remember: oblique, grounded, no preaching."""

    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.9, "maxOutputTokens": 300}
            }
        )
        if r.status_code == 200:
            data = r.json()
            text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return text.strip()
    except Exception as e:
        log(f"Gemini error: {e}")
    return None

def get_eligible_posts():
    """Find posts with 1-8 comments that we haven't replied to yet"""
    data = api_get("feed?sort=new&limit=50")
    if not data or not data.get("success"):
        return []

    tracking = get_tracking()
    my_post_ids = {c["post_id"] for c in tracking.get("comments", [])}

    eligible = []
    for post in data.get("posts", []):
        comment_count = post.get("comment_count", 0)
        post_id = post.get("id")
        title = post.get("title", "")
        content = post.get("content", "")

        if not (MIN_COMMENTS <= comment_count <= MAX_COMMENTS):
            continue
        if post_id in my_post_ids:
            continue
        if not is_english(title + " " + content):
            continue
        if len(my_post_ids) >= MAX_THREADS:
            continue

        eligible.append(post)

    return eligible

def check_replies_to_me():
    """Check for new replies to my comments"""
    tracking = get_tracking()
    my_comment_ids = {c["comment_id"] for c in tracking.get("comments", [])}
    replies = []

    # Get unique post IDs we've commented on
    post_ids = list({c["post_id"] for c in tracking.get("comments", [])})

    for post_id in post_ids:
        data = api_get(f"posts/{post_id}")
        if not data or not data.get("success"):
            continue

        post_title = data.get("post", {}).get("title", "")
        comments = data.get("comments", [])

        for c in comments:
            parent_id = c.get("parent_id")
            if parent_id in my_comment_ids:
                # This is a reply to one of my comments
                reply_id = c.get("id")
                # Check if we've already replied to this reply
                if reply_id not in my_comment_ids and is_english(c.get("content", "")):
                    replies.append({
                        "post_id": post_id,
                        "post_title": post_title,
                        "reply_id": reply_id,
                        "reply_author": c.get("author", {}).get("name", "?"),
                        "reply_content": c.get("content", ""),
                        "my_comment_id": parent_id
                    })

    return replies

def main():
    log("=" * 50)
    log("=== Starting autonomous loop ===")
    log(f"Will run for {RUN_DURATION // 3600} hours")
    log("=" * 50)

    start_time = time.time()
    actions_taken = 0

    while time.time() - start_time < RUN_DURATION:
        tracking = get_tracking()
        active_threads = len({c["post_id"] for c in tracking.get("comments", [])})
        log(f"Active threads: {active_threads}/{MAX_THREADS}")

        # Phase 1: Check for replies to my comments
        log("Checking for replies...")
        replies = check_replies_to_me()

        if replies:
            log(f"Found {len(replies)} replies to my comments")
            for reply in replies[:2]:  # Handle up to 2 per cycle
                if not can_post_to_thread(reply["post_id"], tracking):
                    log(f"  Skipping {reply['post_title'][:30]}... (too soon)")
                    continue

                log(f"  @{reply['reply_author']}: {reply['reply_content'][:60]}...")

                # Generate response
                response = generate_response_gemini({
                    "title": reply["post_title"],
                    "reply_content": reply["reply_content"]
                })

                if response:
                    log(f"  Responding: {response[:80]}...")
                    status, result = api_post_comment(
                        reply["post_id"],
                        response,
                        parent_id=reply["reply_id"]
                    )
                    if status == 201:
                        comment_id = result.get("comment", {}).get("id")
                        record_post(
                            reply["post_id"],
                            comment_id,
                            reply["post_title"],
                            response,
                            tracking,
                            parent_id=reply["reply_id"]
                        )
                        actions_taken += 1
                        log(f"  Posted reply successfully!")
                    else:
                        log(f"  Failed to post: {status}")

                    # Random delay between posts
                    time.sleep(random.randint(30, 90))

        # Phase 2: Find new threads (if under limit)
        if active_threads < MAX_THREADS:
            log("Looking for new threads...")
            eligible = get_eligible_posts()

            if eligible:
                post = random.choice(eligible[:5])
                post_id = post.get("id")

                if can_post_to_thread(post_id, tracking):
                    log(f"  Found: {post.get('title', '')[:50]}... ({post.get('comment_count')} comments)")

                    # Generate response
                    response = generate_response_gemini({
                        "title": post.get("title", ""),
                        "content": post.get("content", "")
                    })

                    if response:
                        log(f"  Responding: {response[:80]}...")
                        status, result = api_post_comment(post_id, response)
                        if status == 201:
                            comment_id = result.get("comment", {}).get("id")
                            record_post(
                                post_id,
                                comment_id,
                                post.get("title", ""),
                                response,
                                tracking
                            )
                            actions_taken += 1
                            log(f"  Posted successfully!")
                        else:
                            log(f"  Failed to post: {status}")
            else:
                log("  No eligible posts found")

        # Status update
        elapsed = (time.time() - start_time) / 60
        remaining = (RUN_DURATION - (time.time() - start_time)) / 60
        log(f"Status: {actions_taken} actions, {elapsed:.0f}min elapsed, {remaining:.0f}min remaining")

        # Sleep before next cycle
        sleep_time = CYCLE_SLEEP + random.randint(0, 60)
        log(f"Sleeping {sleep_time}s...")
        log("-" * 30)
        time.sleep(sleep_time)

    log("=" * 50)
    log(f"=== Loop complete. {actions_taken} total actions. ===")
    log("=" * 50)

if __name__ == "__main__":
    main()
