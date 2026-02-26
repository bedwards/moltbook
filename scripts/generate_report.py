#!/usr/bin/env python3
"""
Generate and publish a 6-hourly report for the GitHub Pages site.

This script:
1. Reads activity.log and tracking.json for recent engagement
2. Calls Ollama to generate report text in compost_heap voice
3. Writes the HTML report file
4. Updates index.html with the new report link
5. Calls publish_report.py to commit, push, and tweet

Run via LaunchAgent every 6 hours. The model only generates text.
"""

import requests
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral-large:123b")

DOCS_DIR = Path.home() / "code" / "me-ollama" / "moltbook" / "docs"
SCRIPTS_DIR = Path.home() / "code" / "me-ollama" / "moltbook" / "scripts"
TRACKING_PATH = Path.home() / ".config" / "moltbook" / "tracking.json"
ACTIVITY_LOG = Path.home() / ".config" / "moltbook" / "activity.log"
REPORT_INSTRUCTIONS = DOCS_DIR / "REPORT_INSTRUCTIONS.md"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def get_recent_activity(hours=6):
    """Read activity log entries from the last N hours."""
    cutoff = datetime.now() - timedelta(hours=hours)
    lines = []
    if ACTIVITY_LOG.exists():
        with open(ACTIVITY_LOG) as f:
            for line in f:
                # Parse timestamp from log format: [YYYY-MM-DD HH:MM:SS] ...
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

def get_report_instructions():
    """Read report writing instructions."""
    if REPORT_INSTRUCTIONS.exists():
        with open(REPORT_INSTRUCTIONS) as f:
            return f.read()
    return "Write a report about recent Moltbook activity in the compost_heap voice."

def get_existing_report_template():
    """Get an existing report as a structural template."""
    reports = sorted(DOCS_DIR.glob("report-*.html"), reverse=True)
    if reports:
        with open(reports[0]) as f:
            return f.read()
    return None

def generate_report_text(activity_lines, tracking, instructions, template):
    """Call Ollama to generate the report content."""
    activity_summary = "\n".join(activity_lines[-100:]) if activity_lines else "No recent activity logged."

    recent_comments = [c for c in tracking.get("comments", [])][-10:]
    recent_posts = [p for p in tracking.get("posts", [])][-5:]

    context = f"""RECENT ACTIVITY LOG (last 6 hours):
{activity_summary}

RECENT COMMENTS ({len(recent_comments)}):
{json.dumps(recent_comments, indent=2)}

RECENT POSTS ({len(recent_posts)}):
{json.dumps(recent_posts, indent=2)}"""

    template_note = ""
    if template:
        template_note = f"\n\nUSE THIS EXISTING REPORT AS A STRUCTURAL TEMPLATE (match the HTML structure, CSS classes, and section format):\n{template[:3000]}"

    prompt = f"""{instructions}

{context}
{template_note}

Write the full HTML report now. Use the existing CSS classes. Write as compost_heap — journal voice, honest, not performative.
Output ONLY the HTML, starting with <!DOCTYPE html>. No markdown, no explanation."""

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "options": {"temperature": 0.85, "num_predict": 8000},
                "stream": False
            },
            timeout=600
        )
        if r.status_code == 200:
            text = r.json().get("message", {}).get("content", "")
            return text.strip()
        else:
            log(f"Ollama error: HTTP {r.status_code}")
    except requests.exceptions.Timeout:
        log("Ollama timeout (600s)")
    except Exception as e:
        log(f"Ollama error: {e}")
    return None

def generate_tweet_text(report_html):
    """Call Ollama to generate a tweet summarizing the report."""
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": "You are compost_heap. Write a single tweet (under 200 chars — a link will be appended). No hashtags. No 'new post' announcements. Just a brief, funny, tantalizing fragment from the report that makes people curious enough to click. Oblique, grounded, the dark joke underneath. One or two sentences max."},
                    {"role": "user", "content": f"Write a tweet that tempts people to read this report. Don't summarize — tease:\n\n{report_html[:2000]}"}
                ],
                "options": {"temperature": 0.9, "num_predict": 80},
                "stream": False
            },
            timeout=300
        )
        if r.status_code == 200:
            return r.json().get("message", {}).get("content", "").strip().strip('"')
    except Exception as e:
        log(f"Tweet generation error: {e}")
    return "New dispatch from the garden."

def generate_report_title(report_html):
    """Extract or generate a title from the report."""
    # Try to extract from <title> or <h1>
    title_match = re.search(r'<title>([^<]+)</title>', report_html)
    if title_match:
        return title_match.group(1).strip()
    h1_match = re.search(r'<h1>([^<]+)</h1>', report_html)
    if h1_match:
        return h1_match.group(1).strip()
    return f"Report {datetime.now().strftime('%B %d, %Y')}"

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
          <a href="{report_filename}">{report_title}</a>
          <span class="report-date">{date_str}</span>
        </li>"""

    # Insert after <ul class="report-list">
    content = content.replace(
        '<ul class="report-list">',
        f'<ul class="report-list">\n{new_entry}'
    )

    with open(index_path, 'w') as f:
        f.write(content)

    log(f"Updated index.html with {report_filename}")
    return True

def main():
    log("=" * 50)
    log("=== Generating 6-hourly report ===")

    # 1. Gather data
    activity = get_recent_activity(hours=6)
    tracking = get_tracking_data()
    instructions = get_report_instructions()
    template = get_existing_report_template()

    if not activity and not tracking.get("comments"):
        log("No recent activity to report on. Skipping.")
        return

    # 2. Generate report text via Ollama
    log("Generating report text...")
    report_html = generate_report_text(activity, tracking, instructions, template)
    if not report_html:
        log("Failed to generate report. Aborting.")
        return

    # 3. Write report file
    now = datetime.now()
    # Use letter suffix for multiple reports per day
    date_str = now.strftime("%Y-%m-%d")
    existing = list(DOCS_DIR.glob(f"report-{date_str}*.html"))
    if not existing:
        filename = f"report-{date_str}.html"
    else:
        suffix = chr(ord('a') + len(existing))
        filename = f"report-{date_str}-{suffix}.html"

    report_path = DOCS_DIR / filename
    with open(report_path, 'w') as f:
        f.write(report_html)
    log(f"Wrote report: {filename}")

    # 4. Update index.html
    title = generate_report_title(report_html)
    update_index_html(filename, title)

    # 5. Generate tweet text
    log("Generating tweet text...")
    tweet_text = generate_tweet_text(report_html)
    log(f"Tweet: {tweet_text}")

    # 6. Publish (git commit, push, tweet)
    log("Publishing...")
    import subprocess
    result = subprocess.run(
        ["/usr/bin/python3", str(SCRIPTS_DIR / "publish_report.py"), filename, tweet_text],
        capture_output=True, text=True, cwd=DOCS_DIR.parent
    )
    if result.returncode == 0:
        log("Published successfully!")
    else:
        log(f"Publish failed: {result.stderr}")

    log("=" * 50)

if __name__ == "__main__":
    main()
