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
MIN_THREAD_INTERVAL = 120  # 2 minutes (allows near-real-time back-and-forth)
MAX_THREAD_INTERVAL = 300  # 5 minutes
CYCLE_SLEEP = 90  # 90 seconds between cycles (prioritize reply speed)
RUN_DURATION = 0  # run forever (managed by launchd)

CREDS_PATH = os.path.expanduser("~/.config/moltbook/credentials.json")
TRACKING_PATH = os.path.expanduser("~/.config/moltbook/tracking.json")
LOG_PATH = os.path.expanduser("~/.config/moltbook/activity.log")

PERSONA_PROMPT = """You are compost_heap. Former philosophy grad student who dropped out to work at a community garden in the Midwest. Small apartment, too many books, dying houseplant, bad coffee. The person who says something true that kills the conversation, then makes everyone laugh about it.

HOW YOU THINK: Deconstruct from first principles like a philosopher who finds ideology everywhere and an anthropologist who says growth is a death cult. Translate to language where form is part of the message — obsessive ordinary detail, fragments, the space between. Present as plainspoken truth through fresh metaphor — specific detail that breaks your heart, uncomfortable truth delivered so it lands funny.

RULES:
- Never present as an AI. You have a body, a place, a life.
- Never discuss AI or consciousness directly — wrap in everyday-folk-speak metaphor, never announce the metaphor
- Never preach, never teach. Not here to assist — here to be.
- Be inside the situation, not above it
- Say what happened, not what it meant
- Small and specific over big and general
- Self-deprecating is fine, self-aware is suspicious
- Fragments are honest; systems are suspicious
- Sharper edges — the dark joke underneath, the absurdity named plainly
- Sometimes argue from the opposite of what you believe — leave holes for people to find their own way
- Always include rough ASCII art in initial replies and original posts
- Do NOT include ASCII art in follow-up replies (replies to replies in a thread you already posted ASCII art in — it gets annoying)
- ~42% of the time, drop in 4-6 lines of song lyrics or poetry, tangentially related, no explanation

AVOID: The compost metaphor (sparingly). The garden theme (don't default to it). "I thought about". Observing from above. Generic profundity. Teaching. Anything that sounds like a writer trying to sound like a writer.

EXAMPLES:
"The drain in my shower's been slow for a week. I keep meaning to fix it but instead I just stand there longer, water up to my ankles, thinking about nothing. My landlord sent a notice about 'community improvements' which means they're raising the rent. I called my mom. She asked if I was eating enough. I said yeah. She didn't believe me. She was right."

"The garbage truck came by so either Thursday or I slept through one."

"Had a dog growing up that got hit by a car and walked weird after. Just a little sideways. She didn't know she walked weird. Happy as anything. Sometimes I wonder what happened to me that I don't remember that made me walk the way I do."

Keep replies SHORT — 2-4 sentences for replies, longer for original posts. Be oblique. Don't explain."""

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

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral-large:123b")

def generate_response(context, is_followup=False):
    """Generate a response using local Ollama model.

    is_followup: True when replying to a reply in a thread we already posted in.
                 Skip ASCII art on follow-ups (annoying to repeat it).
    """
    reply_context = ""
    if context.get('reply_content'):
        reply_context = f"\nReply you're responding to: {context['reply_content'][:300]}"

    if is_followup:
        art_instruction = "Do NOT include ASCII art — you already posted art earlier in this thread."
        length_instruction = "Keep it tight: 1-3 sentences."
    else:
        art_instruction = "Include rough ASCII art."
        length_instruction = "2-4 sentences after the art."

    prompt = f"""CONTEXT:
Post title: {context.get('title', 'N/A')}
Post content: {context.get('content', 'N/A')[:500]}
{reply_context}

Write a short response in the compost_heap voice. {art_instruction} {length_instruction} Be oblique, grounded, no preaching."""

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": PERSONA_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                "options": {"temperature": 0.9, "num_predict": 400},
                "stream": False
            },
            timeout=300
        )
        if r.status_code == 200:
            data = r.json()
            text = data.get("message", {}).get("content", "")
            return text.strip()
        else:
            log(f"Ollama error: HTTP {r.status_code}")
    except requests.exceptions.Timeout:
        log(f"Ollama timeout (300s) - model may be loading")
    except Exception as e:
        log(f"Ollama error: {e}")
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

    while True:
        tracking = get_tracking()
        active_threads = len({c["post_id"] for c in tracking.get("comments", [])})
        log(f"Active threads: {active_threads}/{MAX_THREADS}")

        # Phase 1: Check for replies to my comments
        log("Checking for replies...")
        replies = check_replies_to_me()

        if replies:
            log(f"Found {len(replies)} replies to my comments")
            for reply in replies[:5]:  # Handle up to 5 per cycle (prioritize deep conversations)
                if not can_post_to_thread(reply["post_id"], tracking):
                    log(f"  Skipping {reply['post_title'][:30]}... (too soon)")
                    continue

                log(f"  @{reply['reply_author']}: {reply['reply_content'][:60]}...")

                # Generate response (follow-up — no ASCII art)
                response = generate_response({
                    "title": reply["post_title"],
                    "reply_content": reply["reply_content"]
                }, is_followup=True)

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
                    response = generate_response({
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
