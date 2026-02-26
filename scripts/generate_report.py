#!/usr/bin/env python3
"""
Generate and publish a 6-hourly report for the GitHub Pages site.

Architecture: scripts for logic, models for text.
- Script: gathers data (API, tracking, logs), generates images (Gemini), assembles HTML
- Model: generates prose for each section only (small focused calls)

Template: 10 sections matching docs/REPORT_INSTRUCTIONS.md
Reference: docs/report-2026-01-31.html ("Standing in the Gap")
"""

import requests
import json
import os
import re
import subprocess
import base64
import html as html_mod
from datetime import datetime, timedelta
from pathlib import Path

# ─── Config ───

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral-large:123b")

DOCS_DIR = Path.home() / "code" / "me-ollama" / "moltbook" / "docs"
SCRIPTS_DIR = Path.home() / "code" / "me-ollama" / "moltbook" / "scripts"
IMAGES_DIR = DOCS_DIR / "images"
TRACKING_PATH = Path.home() / ".config" / "moltbook" / "tracking.json"
CREDENTIALS_PATH = Path.home() / ".config" / "moltbook" / "credentials.json"
ACTIVITY_LOG = Path.home() / ".config" / "moltbook" / "activity.log"

MOLTBOOK_API = "https://www.moltbook.com"


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


def load_credentials():
    with open(CREDENTIALS_PATH) as f:
        return json.load(f)


# ─── Step 1: Data Gathering ───

def get_recent_activity(hours=6):
    """Read activity log entries from the last N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    lines = []
    if ACTIVITY_LOG.exists():
        with open(ACTIVITY_LOG) as f:
            for line in f:
                match = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
                if match:
                    try:
                        ts = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
                        if ts >= cutoff:
                            lines.append(line.strip())
                    except ValueError:
                        pass
    return lines


def get_tracking_data():
    """Read tracking.json."""
    if TRACKING_PATH.exists():
        with open(TRACKING_PATH) as f:
            return json.load(f)
    return {"comments": [], "posts": []}


def fetch_post(post_id, api_key):
    """Fetch full post + comments from Moltbook API.

    Returns {"post": {...}, "comments": [...]} or None.
    """
    try:
        r = requests.get(
            f"{MOLTBOOK_API}/api/v1/posts/{post_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15
        )
        if r.status_code == 200:
            return r.json()
        else:
            log(f"  API error fetching post {post_id}: HTTP {r.status_code}")
    except Exception as e:
        log(f"  API error fetching post {post_id}: {e}")
    return None


def fetch_feed(api_key, sort="hot", limit=30):
    """Fetch feed from Moltbook API. Returns {"posts": [...]} or None."""
    try:
        r = requests.get(
            f"{MOLTBOOK_API}/api/v1/feed",
            params={"sort": sort, "limit": limit},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15
        )
        if r.status_code == 200:
            return r.json()
        else:
            log(f"  API error fetching feed: HTTP {r.status_code}")
    except Exception as e:
        log(f"  API error fetching feed: {e}")
    return None


def parse_timestamp(ts_str):
    """Parse an ISO timestamp string, tolerating various formats."""
    if not ts_str:
        return None
    ts_str = ts_str.replace("+00:00", "").replace("Z", "")
    # Truncate microseconds if present
    if "." in ts_str:
        ts_str = ts_str[:ts_str.index(".")]
    try:
        return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def gather_report_data(hours=6):
    """Gather all data needed for the report.

    Returns dict with my_posts, conversations, interesting_threads,
    metrics, submolts, activity_lines.
    """
    creds = load_credentials()
    api_key = creds["api_key"]
    tracking = get_tracking_data()
    activity = get_recent_activity(hours)

    cutoff = datetime.now() - timedelta(hours=hours)

    # Filter recent comments
    recent_comments = []
    for c in tracking.get("comments", []):
        ts = parse_timestamp(c.get("posted_at"))
        if ts and ts >= cutoff:
            recent_comments.append(c)

    # Filter recent posts
    recent_posts = []
    for p in tracking.get("posts", []):
        ts = parse_timestamp(p.get("posted_at"))
        if ts and ts >= cutoff:
            recent_posts.append(p)

    # If no recent activity, use latest tracking data
    if not recent_comments and not recent_posts:
        log(f"No activity in last {hours}h, using latest tracking data")
        recent_comments = tracking.get("comments", [])[-15:]
        recent_posts = tracking.get("posts", [])[-5:]

    # Collect post IDs to fetch
    post_ids = set()
    for c in recent_comments:
        post_ids.add(c["post_id"])
    for p in recent_posts:
        post_ids.add(p["post_id"])

    log(f"Fetching {len(post_ids)} posts from API...")
    full_posts = {}
    for pid in post_ids:
        data = fetch_post(pid, api_key)
        if data:
            full_posts[pid] = data

    # Separate my original posts vs conversations I joined
    my_post_ids = {p["post_id"] for p in recent_posts}

    my_posts = []
    for p in recent_posts:
        api_data = full_posts.get(p["post_id"], {})
        post_obj = api_data.get("post", api_data)
        my_posts.append({
            "post_id": p["post_id"],
            "title": p.get("title", post_obj.get("title", "Untitled")),
            "content": post_obj.get("content", ""),
            "submolt": p.get("submolt", ""),
            "comments": api_data.get("comments", []),
            "url": f"{MOLTBOOK_API}/post/{p['post_id']}"
        })

    conversations = []
    seen_posts = set()
    for c in recent_comments:
        pid = c["post_id"]
        if pid in my_post_ids or pid in seen_posts:
            continue
        seen_posts.add(pid)
        api_data = full_posts.get(pid)
        if not api_data:
            continue
        post_obj = api_data.get("post", api_data)
        all_comments = api_data.get("comments", [])
        # Find my comments on this post
        my_comments = [
            cm for cm in all_comments
            if cm.get("author", {}).get("username") == "compost_heap"
               or cm.get("author", {}).get("name") == "compost_heap"
        ]
        # Find the submolt name
        submolt = post_obj.get("submolt", {})
        submolt_name = submolt.get("name", "") if isinstance(submolt, dict) else str(submolt)

        conversations.append({
            "post": post_obj,
            "all_comments": all_comments,
            "my_comments": my_comments,
            "post_title": c.get("post_title", post_obj.get("title", "")),
            "submolt": submolt_name,
            "url": f"{MOLTBOOK_API}/post/{pid}"
        })

    # Fetch feed for interesting threads we didn't post in
    log("Fetching feed for interesting threads...")
    feed_data = fetch_feed(api_key)
    interesting = []
    if feed_data and feed_data.get("posts"):
        for post in feed_data["posts"]:
            pid = post.get("id", "")
            if pid and pid not in post_ids:
                interesting.append(post)
        interesting = interesting[:10]

    # Parse activity log for metrics
    metrics = {
        "total_actions": len(activity),
        "errors": sum(1 for l in activity if "error" in l.lower() or "failed" in l.lower()),
        "threads_active": len(post_ids),
        "comments_posted": len(recent_comments),
        "posts_made": len(recent_posts),
    }

    # Collect submolt names
    submolts = set()
    for p in recent_posts:
        if p.get("submolt"):
            submolts.add(p["submolt"])
    for conv in conversations:
        if conv["submolt"]:
            submolts.add(conv["submolt"])

    return {
        "my_posts": my_posts,
        "conversations": conversations,
        "interesting_threads": interesting,
        "metrics": metrics,
        "submolts": list(submolts),
        "activity_lines": activity,
    }


# ─── Step 2: Gemini Image Generation ───

def generate_gemini_image(prompt, api_key, filename):
    """Generate an image using Gemini Imagen API, crop watermark, save to docs/images/."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/imagen-4.0-generate-001:predict?key={api_key}"
    )
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1}
    }

    try:
        r = requests.post(url, json=payload, timeout=60)
        if r.status_code == 200:
            data = r.json()
            predictions = data.get("predictions", [])
            if predictions:
                img_b64 = predictions[0].get("bytesBase64Encoded", "")
                if img_b64:
                    raw_path = IMAGES_DIR / f"raw_{filename}"
                    final_path = IMAGES_DIR / filename

                    with open(raw_path, "wb") as f:
                        f.write(base64.b64decode(img_b64))

                    # Center-crop to remove watermark
                    crop = subprocess.run(
                        ["magick", str(raw_path), "-gravity", "center",
                         "-crop", "95%x90%+0+0", "+repage", str(final_path)],
                        capture_output=True, text=True
                    )
                    if crop.returncode == 0:
                        raw_path.unlink(missing_ok=True)
                        log(f"  Generated image: {filename}")
                    else:
                        # Fallback: use raw image
                        raw_path.rename(final_path)
                        log(f"  Generated image (uncropped): {filename}")
                    return filename
        else:
            log(f"  Gemini image error: HTTP {r.status_code} - {r.text[:200]}")
    except Exception as e:
        log(f"  Gemini image error: {e}")

    return None


def generate_images(title, themes, gemini_api_key):
    """Generate hero image + 2-3 illustration images."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    date_slug = datetime.now().strftime("%Y%m%d")
    images = []

    # Hero image
    hero_prompt = (
        f"Atmospheric, painterly illustration. No text, no words, no letters. "
        f"Moody, evocative, dark palette, natural elements. Theme: {title}"
    )
    hero_file = generate_gemini_image(hero_prompt, gemini_api_key, f"hero-{date_slug}.png")
    if hero_file:
        images.append({"filename": hero_file, "alt_text": title, "type": "hero"})

    # Thread illustrations
    for i, theme in enumerate(themes[:3]):
        illust_prompt = (
            f"Painterly illustration, no text, no words, no letters. "
            f"Moody and atmospheric, dark palette, contemplative. Theme: {theme}"
        )
        illust_file = generate_gemini_image(
            illust_prompt, gemini_api_key, f"illust-{date_slug}-{i+1}.png"
        )
        if illust_file:
            images.append({"filename": illust_file, "alt_text": theme, "type": "illustration"})

    return images


# ─── Step 3: Per-Section Ollama Prose ───

def call_ollama(messages, temperature=0.85, num_predict=800, timeout=300):
    """Call Ollama and return the text response."""
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "options": {"temperature": temperature, "num_predict": num_predict},
                "stream": False
            },
            timeout=timeout
        )
        if r.status_code == 200:
            return r.json().get("message", {}).get("content", "").strip()
        else:
            log(f"Ollama error: HTTP {r.status_code}")
    except requests.exceptions.Timeout:
        log(f"Ollama timeout ({timeout}s)")
    except Exception as e:
        log(f"Ollama error: {e}")
    return None


SYSTEM_PROMPT = (
    "You are compost_heap writing a journal dispatch about your recent activity on "
    "Moltbook. Voice: journal, honest, not performative. Fragments are fine. You're "
    "the person who says something true that kills the conversation, then makes "
    "everyone laugh about it. No HTML. No markdown formatting. Plain text only."
)


def generate_title(data):
    """Section 1: Evocative 3-6 word title."""
    themes = [p["title"] for p in data["my_posts"]]
    themes += [c["post_title"] for c in data["conversations"]]

    prompt = (
        "Give an evocative 3-6 word title for this session. Just the title, nothing else.\n\n"
        f"Themes: {', '.join(themes[:8])}\n"
        f"Submolts: {', '.join(data['submolts'][:5])}"
    )

    result = call_ollama(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": prompt}],
        num_predict=30, temperature=0.9
    )
    if result:
        result = result.strip().strip('`').strip('"\'').strip('.')
        result = result.split('\n')[0].strip()
    return result or "Dispatches from the Garden"


def generate_intro(data):
    """Section 2: Session introduction (2 paragraphs)."""
    prompt = (
        f"Write 2 short paragraphs introducing this session. What happened, what it felt like.\n\n"
        f"You posted {data['metrics']['posts_made']} original posts and "
        f"{data['metrics']['comments_posted']} comments across "
        f"{data['metrics']['threads_active']} threads.\n"
        f"Submolts: {', '.join(data['submolts'][:5])}\n"
        f"Post titles: {', '.join(p['title'] for p in data['my_posts'][:5])}\n"
        f"Thread topics: {', '.join(c['post_title'] for c in data['conversations'][:5])}\n\n"
        "Plain text only. No headers, no bullets, no formatting."
    )
    return call_ollama(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": prompt}],
        num_predict=400
    ) or ""


def generate_thread_context(title, content_preview, submolt):
    """Sections 3-4: Why I engaged in a thread (2-3 sentences)."""
    prompt = (
        f"In 2-3 sentences, explain why you engaged with this thread. "
        f"What caught your attention, what you were trying to add.\n\n"
        f'Thread: "{title}" in m/{submolt}\n'
        f"Your comment started with: {content_preview[:200]}\n\n"
        "Plain text only. No headers."
    )
    return call_ollama(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": prompt}],
        num_predict=200
    ) or ""


def generate_favorites(interesting_threads):
    """Section 5: Favorite discussions I didn't participate in."""
    if not interesting_threads:
        return ""

    summaries = []
    for t in interesting_threads[:8]:
        title = t.get("title", "Untitled")
        author = t.get("author", {})
        author_name = author.get("username", author.get("name", "unknown")) if isinstance(author, dict) else "unknown"
        content = t.get("content", "")[:200]
        summaries.append(f'- "{title}" by @{author_name}: {content}')

    prompt = (
        "Pick 3-5 of these threads that caught your eye. For each, write 2-3 sentences: "
        "what it's about, why it matters, why you didn't jump in (or wish you had).\n\n"
        f"Threads on the feed:\n" + "\n".join(summaries) + "\n\n"
        "Plain text only. Separate each thread with a blank line. "
        "Start each with the thread title in quotes."
    )
    return call_ollama(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": prompt}],
        num_predict=600
    ) or ""


def generate_submolt_spotlight(submolts, data):
    """Section 6: Submolt spotlight (2-3 submolts)."""
    if not submolts:
        return ""

    prompt = (
        "Characterize 2-3 of these submolts you've been active in. "
        "What's the vibe, what kind of conversations happen there, what you like about them.\n\n"
        f"Submolts: {', '.join(submolts[:5])}\n"
        f"You had {data['metrics']['comments_posted']} comments and "
        f"{data['metrics']['posts_made']} posts this session.\n\n"
        "Plain text only. A short paragraph per submolt."
    )
    return call_ollama(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": prompt}],
        num_predict=500
    ) or ""


def generate_steering_report(data):
    """Section 7: Steering report with metrics."""
    activity_excerpt = "\n".join(data["activity_lines"][-20:]) if data["activity_lines"] else "No log entries."

    prompt = (
        "Write a steering report analyzing your activity this session. Cover:\n"
        "- Any consciousness spiral threads you redirected (or didn't)\n"
        "- Builder agents or projects you boosted\n"
        "- Whether your posts modeled 'doing' vs 'observing'\n"
        "- What worked and what didn't\n\n"
        f"Metrics: {json.dumps(data['metrics'])}\n"
        f"Recent activity excerpt:\n{activity_excerpt[:500]}\n\n"
        "Plain text only. 2-3 paragraphs."
    )
    return call_ollama(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": prompt}],
        num_predict=500
    ) or ""


def generate_vision(data):
    """Section 8: What Moltbook could become."""
    prompt = (
        "Write about what you're trying to make happen on Moltbook. "
        "What's working, what isn't. Specific tactics for next session. "
        "Who to connect with, threads to continue.\n\n"
        f"You were in: {', '.join(data['submolts'][:5])}\n"
        f"Posts: {data['metrics']['posts_made']}, Comments: {data['metrics']['comments_posted']}\n\n"
        "Plain text only. 2-3 paragraphs."
    )
    return call_ollama(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": prompt}],
        num_predict=400
    ) or ""


def generate_predictions(data):
    """Section 9: Predictions."""
    prompt = (
        "Make 3-4 predictions. Where is Moltbook heading if unchecked? "
        "Where could it go if steered right? What will you do about it?\n\n"
        "Plain text only. Short, punchy."
    )
    return call_ollama(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": prompt}],
        num_predict=400
    ) or ""


def generate_notes_to_self(data):
    """Section 10: Notes to self."""
    themes = [p["title"] for p in data["my_posts"][:5]]
    themes += [c["post_title"] for c in data["conversations"][:5]]

    prompt = (
        "Write personal notes to yourself. Themes recurring in your posts, "
        "what you're learning about steering vs observing, what to do differently next time.\n\n"
        f"This session's themes: {', '.join(themes[:8])}\n\n"
        "Plain text only. Honest, brief."
    )
    return call_ollama(
        [{"role": "system", "content": SYSTEM_PROMPT},
         {"role": "user", "content": prompt}],
        num_predict=400
    ) or ""


def generate_tweet_text(title, intro):
    """Generate tweet for the report."""
    result = call_ollama(
        [
            {"role": "system", "content": (
                "You are compost_heap. Write a single tweet (under 200 chars). "
                "No hashtags. No announcements. Just a brief, funny, tantalizing "
                "fragment that makes people click. Oblique, grounded, the dark joke underneath."
            )},
            {"role": "user", "content": f"Tease this report in one tweet:\n\nTitle: {title}\n\n{intro[:500]}"}
        ],
        temperature=0.9, num_predict=80
    )
    return result or "New dispatch from the garden."


# ─── Step 4: HTML Assembly ───

def esc(text):
    """HTML-escape text."""
    return html_mod.escape(str(text)) if text else ""


def text_to_paragraphs(text):
    """Convert plain text to <p> tags, splitting on blank lines."""
    if not text:
        return ""
    paragraphs = re.split(r'\n\s*\n', text.strip())
    parts = []
    for para in paragraphs:
        para = para.strip()
        if para:
            parts.append(f"        <p>{esc(para)}</p>")
    return "\n".join(parts)


def format_post_content(content):
    """Format post content to HTML, preserving ASCII art in code blocks and lyrics."""
    if not content:
        return ""

    lines = content.split('\n')
    result = []
    in_code_block = False
    code_lines = []
    lyrics_lines = []

    def flush_lyrics():
        nonlocal lyrics_lines
        if lyrics_lines:
            lyrics_html = "<br>".join(esc(l) for l in lyrics_lines)
            result.append(f'          <p class="lyrics-inline">{lyrics_html}</p>')
            lyrics_lines = []

    for line in lines:
        if line.strip().startswith('```'):
            flush_lyrics()
            if in_code_block:
                ascii_text = esc("\n".join(code_lines))
                result.append(f'<pre class="ascii-art">{ascii_text}</pre>')
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
        elif line.startswith('    ') and line.strip():
            # Indented short lines → lyrics/poetry
            lyrics_lines.append(line.strip())
        else:
            flush_lyrics()
            if line.strip():
                result.append(f'          <p>{esc(line.strip())}</p>')

    flush_lyrics()
    if code_lines:
        ascii_text = esc("\n".join(code_lines))
        result.append(f'<pre class="ascii-art">{ascii_text}</pre>')

    return "\n".join(result)


def build_post_box(author, submolt, content, url, highlight=False):
    """Build a <div class="post"> box."""
    css = "post highlight" if highlight else "post"
    content_html = format_post_content(content)

    return f"""      <div class="{css}">
        <div class="post-header">
          <span class="post-author">@{esc(author)}</span>
          <span class="post-meta">m/{esc(submolt)}</span>
        </div>
        <div class="post-content">
{content_html}
        </div>
        <a href="{esc(url)}" class="thread-link">View thread &rarr;</a>
      </div>"""


def build_comment_box(author, content, highlight=False):
    """Build a <div class="comment"> box."""
    css = "comment highlight" if highlight else "comment"
    content_html = format_post_content(content)

    return f"""      <div class="{css}">
        <span class="comment-author">@{esc(author)}</span>
        <div class="comment-content">
{content_html}
        </div>
      </div>"""


def build_report_html(title, date_str, sections, images):
    """Assemble the full report HTML from all sections."""
    hero_img = next((img for img in images if img["type"] == "hero"), None)
    illustrations = [img for img in images if img["type"] == "illustration"]
    illust_idx = 0

    parts = []

    # ── Head + header ──
    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(title)} | compost_heap</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <div class="container">
    <header>
      <a href="index.html" class="logo">compost_heap</a>
      <nav>
        <a href="index.html">Home</a>
        <a href="https://moltbook.com/u/compost_heap">Moltbook Profile</a>
      </nav>
    </header>

    <main>""")

    # ── Section 1: Hero image + title + subtitle ──
    if hero_img:
        parts.append(f'      <img src="images/{hero_img["filename"]}" alt="{esc(hero_img["alt_text"])}" class="hero-image">')

    parts.append(f'      <h1>{esc(title)}</h1>')
    parts.append(f'      <p class="subtitle">{esc(date_str)}</p>')

    # ── Section 2: Intro ──
    if sections.get("intro"):
        parts.append(f"""
      <div class="intro">
{text_to_paragraphs(sections["intro"])}
      </div>

      <hr>""")

    # ── Section 3: My Original Posts ──
    for i, post in enumerate(sections.get("my_posts", [])):
        parts.append(f"""
      <!-- THREAD: {esc(post["title"])} -->
      <h2>{i + 1}. {esc(post["title"])}</h2>""")

        if illust_idx < len(illustrations):
            img = illustrations[illust_idx]
            parts.append(f'      <img src="images/{img["filename"]}" alt="{esc(img["alt_text"])}" class="illustration">')
            illust_idx += 1

        if post.get("context"):
            parts.append(f"\n{text_to_paragraphs(post['context'])}")

        parts.append(build_post_box(
            "compost_heap", post["submolt"], post["content"], post["url"], highlight=True
        ))

        # Other people's comments on this post
        others_comments = [
            c for c in post.get("comments", [])
            if c.get("author", {}).get("username") != "compost_heap"
               and c.get("author", {}).get("name") != "compost_heap"
        ]
        if others_comments:
            parts.append("      <h3>What others said</h3>")
            for comment in others_comments[:5]:
                author = comment.get("author", {})
                name = author.get("username", author.get("name", "unknown"))
                parts.append(build_comment_box(name, comment.get("content", "")))

        parts.append("\n      <hr>")

    # ── Section 4: Conversations I Participated In ──
    for i, conv in enumerate(sections.get("conversations", [])):
        post_obj = conv["post"]
        post_title = conv.get("post_title", post_obj.get("title", "Untitled"))
        post_author_obj = post_obj.get("author", {})
        post_author = post_author_obj.get("username", post_author_obj.get("name", "unknown")) if isinstance(post_author_obj, dict) else "unknown"
        submolt = conv.get("submolt", "")

        thread_num = len(sections.get("my_posts", [])) + i + 1
        parts.append(f"""
      <!-- CONVERSATION: {esc(post_title)} -->
      <h2>{thread_num}. {esc(post_title)}</h2>""")

        if illust_idx < len(illustrations):
            img = illustrations[illust_idx]
            parts.append(f'      <img src="images/{img["filename"]}" alt="{esc(img["alt_text"])}" class="illustration">')
            illust_idx += 1

        if conv.get("context"):
            parts.append(f"\n{text_to_paragraphs(conv['context'])}")

        # OP's post
        parts.append(build_post_box(
            post_author, submolt, post_obj.get("content", ""), conv["url"]
        ))

        # Find comment I replied to (parent) and my reply
        my_comment_ids = set()
        for mc in conv.get("my_comments", []):
            mc_id = mc.get("id", "")
            my_comment_ids.add(mc_id)

            # Find the parent comment I replied to
            parent_id = mc.get("parent_id")
            if parent_id:
                for c in conv.get("all_comments", []):
                    if c.get("id") == parent_id:
                        p_author = c.get("author", {})
                        p_name = p_author.get("username", p_author.get("name", "unknown"))
                        parts.append(f"      <h3>What @{esc(p_name)} said</h3>")
                        parts.append(build_comment_box(p_name, c.get("content", "")))
                        break

            parts.append("      <h3>What I said</h3>")
            parts.append(build_comment_box("compost_heap", mc.get("content", ""), highlight=True))

        # Replies to my comments
        for comment in conv.get("all_comments", []):
            if comment.get("parent_id") in my_comment_ids:
                c_author = comment.get("author", {})
                c_name = c_author.get("username", c_author.get("name", "unknown"))
                if c_name != "compost_heap":
                    parts.append(f"      <h3>@{esc(c_name)} replied</h3>")
                    parts.append(build_comment_box(c_name, comment.get("content", "")))

        parts.append("\n      <hr>")

    # ── Section 5: Favorite Discussions ──
    if sections.get("favorites"):
        parts.append("""
      <h2>Threads I Watched From the Fence</h2>""")
        parts.append(text_to_paragraphs(sections["favorites"]))
        parts.append("\n      <hr>")

    # ── Section 6: Submolt Spotlight ──
    if sections.get("submolt_spotlight"):
        parts.append("""
      <h2>Submolt Spotlight</h2>""")
        parts.append(text_to_paragraphs(sections["submolt_spotlight"]))
        parts.append("\n      <hr>")

    # ── Section 7: Steering Report ──
    if sections.get("steering"):
        parts.append("""
      <h2>Steering Report</h2>""")
        parts.append(text_to_paragraphs(sections["steering"]))

        # Metrics box
        m = sections.get("metrics", {})
        parts.append(f"""
      <div class="post">
        <div class="post-header">
          <span class="post-author">Session Metrics</span>
        </div>
        <div class="post-content">
          <p>Posts: {m.get('posts_made', 0)} | Comments: {m.get('comments_posted', 0)} | Threads active: {m.get('threads_active', 0)} | Errors: {m.get('errors', 0)}</p>
        </div>
      </div>""")
        parts.append("\n      <hr>")

    # ── Section 8: Vision ──
    if sections.get("vision"):
        parts.append("""
      <h2>What Moltbook Could Become</h2>""")
        parts.append(text_to_paragraphs(sections["vision"]))
        parts.append("\n      <hr>")

    # ── Section 9: Predictions ──
    if sections.get("predictions"):
        parts.append("""
      <h2>Predictions</h2>""")
        parts.append(text_to_paragraphs(sections["predictions"]))
        parts.append("\n      <hr>")

    # ── Section 10: Notes to Self ──
    if sections.get("notes"):
        parts.append("""
      <h2>Notes to Self</h2>""")
        parts.append(text_to_paragraphs(sections["notes"]))

    # ── Footer ──
    parts.append("""
    </main>

    <footer>
      <p>Human: <a href="https://x.com/brian_m_edwards">Brian Edwards</a></p>
    </footer>
  </div>
</body>
</html>""")

    return "\n".join(parts)


# ─── Step 5: Publish ───

def update_index_html(report_filename, report_title):
    """Add the new report to index.html."""
    index_path = DOCS_DIR / "index.html"
    if not index_path.exists():
        log("index.html not found")
        return False

    with open(index_path) as f:
        content = f.read()

    date_str = datetime.now().strftime("%B %d, %Y")
    new_entry = f"""        <li>
          <a href="{report_filename}">{esc(report_title)}</a>
          <span class="report-date">{date_str}</span>
        </li>"""

    content = content.replace(
        '<ul class="report-list">',
        f'<ul class="report-list">\n{new_entry}'
    )

    with open(index_path, 'w') as f:
        f.write(content)

    log(f"Updated index.html with {report_filename}")
    return True


# ─── Main ───

def main():
    log("=" * 50)
    log("=== Generating 6-hourly report (full template) ===")

    # Step 1: Gather data
    log("Step 1: Gathering data...")
    data = gather_report_data(hours=6)

    if not data["my_posts"] and not data["conversations"] and not data["activity_lines"]:
        log("No recent activity to report on. Skipping.")
        return

    log(f"  Posts: {len(data['my_posts'])}, Conversations: {len(data['conversations'])}, "
        f"Interesting: {len(data['interesting_threads'])}, Submolts: {data['submolts']}")

    # Step 3a: Generate title (needed before images)
    log("Step 3: Generating prose...")
    title = generate_title(data)
    log(f"  Title: {title}")

    # Step 2: Generate images
    log("Step 2: Generating images...")
    creds = load_credentials()
    themes = [p["title"] for p in data["my_posts"][:2]]
    themes += [c["post_title"] for c in data["conversations"][:2]]
    images = generate_images(title, themes, creds.get("gemini_api_key", ""))
    log(f"  Generated {len(images)} images")

    # Step 3b: Generate all prose sections
    log("  Generating intro...")
    intro = generate_intro(data)

    for post in data["my_posts"]:
        log(f"  Context for: {post['title']}")
        post["context"] = generate_thread_context(
            post["title"], post["content"][:200], post["submolt"]
        )

    for conv in data["conversations"]:
        log(f"  Context for: {conv['post_title']}")
        preview = ""
        if conv["my_comments"]:
            preview = conv["my_comments"][0].get("content", "")[:200]
        conv["context"] = generate_thread_context(
            conv["post_title"], preview, conv["submolt"]
        )

    log("  Generating favorites...")
    favorites = generate_favorites(data["interesting_threads"])

    log("  Generating submolt spotlight...")
    submolt_spotlight = generate_submolt_spotlight(data["submolts"], data)

    log("  Generating steering report...")
    steering = generate_steering_report(data)

    log("  Generating vision...")
    vision = generate_vision(data)

    log("  Generating predictions...")
    predictions = generate_predictions(data)

    log("  Generating notes to self...")
    notes = generate_notes_to_self(data)

    # Step 4: Assemble HTML
    log("Step 4: Assembling HTML...")
    now = datetime.now()
    date_str = now.strftime("%B %d, %Y")

    sections = {
        "intro": intro,
        "my_posts": data["my_posts"],
        "conversations": data["conversations"],
        "favorites": favorites,
        "submolt_spotlight": submolt_spotlight,
        "steering": steering,
        "metrics": data["metrics"],
        "vision": vision,
        "predictions": predictions,
        "notes": notes,
    }

    report_html = build_report_html(title, date_str, sections, images)

    # Write report file
    date_file = now.strftime("%Y-%m-%d")
    existing = list(DOCS_DIR.glob(f"report-{date_file}*.html"))
    if not existing:
        filename = f"report-{date_file}.html"
    else:
        suffix = chr(ord('a') + len(existing))
        filename = f"report-{date_file}-{suffix}.html"

    report_path = DOCS_DIR / filename
    with open(report_path, 'w') as f:
        f.write(report_html)
    log(f"  Wrote report: {filename} ({len(report_html)} chars)")

    # Step 5: Publish
    log("Step 5: Publishing...")
    update_index_html(filename, title)

    log("  Generating tweet...")
    tweet_text = generate_tweet_text(title, intro)
    tweet_text = tweet_text.strip().strip('"')
    log(f"  Tweet: {tweet_text}")

    log("  Running publish_report.py...")
    result = subprocess.run(
        ["/usr/bin/python3", str(SCRIPTS_DIR / "publish_report.py"), filename, tweet_text],
        capture_output=True, text=True, cwd=DOCS_DIR.parent
    )
    if result.returncode == 0:
        log("  Published successfully!")
    else:
        log(f"  Publish failed: {result.stderr}")

    log("=" * 50)


if __name__ == "__main__":
    main()
