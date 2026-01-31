#!/usr/bin/env python3
"""
Publish a report to GitHub Pages and tweet about it.

Usage:
    python publish_report.py <report_file.html> "<tweet_text>"
    python publish_report.py report-2026-01-31.html "First night on Moltbook. Boots, worms, olive oil."

This script:
1. Adds the report to git
2. Commits and pushes to GitHub
3. Creates a tinyurl for the report
4. Posts a tweet with the summary and link
"""

import sys
import subprocess
import requests
from pathlib import Path

DOCS_DIR = Path.home() / "moltbook" / "docs"
SITE_BASE = "https://bedwards.github.io/moltbook"

def run_cmd(cmd: str) -> tuple[int, str]:
    """Run a shell command and return (exit_code, output)."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=DOCS_DIR.parent)
    return result.returncode, result.stdout + result.stderr

def create_tinyurl(url: str) -> str:
    """Create a tinyurl for the given URL."""
    response = requests.get(f"https://tinyurl.com/api-create.php?url={url}")
    if response.status_code == 200:
        return response.text
    return url  # fallback to original

def publish_report(report_file: str, tweet_text: str, dry_run: bool = False):
    """Publish report and tweet about it."""
    report_path = DOCS_DIR / report_file

    if not report_path.exists():
        print(f"Error: Report not found: {report_path}")
        return False

    print(f"Publishing: {report_file}")

    # Git operations
    print("\n1. Adding to git...")
    code, out = run_cmd(f"git add docs/{report_file}")
    if code != 0:
        print(f"Git add failed: {out}")
        return False

    print("2. Committing...")
    code, out = run_cmd(f'git commit -m "Add report: {report_file}"')
    if code != 0 and "nothing to commit" not in out:
        print(f"Git commit failed: {out}")
        return False

    print("3. Pushing to GitHub...")
    if not dry_run:
        code, out = run_cmd("git push")
        if code != 0:
            print(f"Git push failed: {out}")
            return False
    else:
        print("   [DRY RUN - skipped push]")

    # Create tinyurl
    report_url = f"{SITE_BASE}/{report_file}"
    print(f"\n4. Creating tinyurl for: {report_url}")
    short_url = create_tinyurl(report_url)
    print(f"   Short URL: {short_url}")

    # Post tweet
    full_tweet = f"{tweet_text}\n\n{short_url}"

    print(f"\n5. Posting tweet...")
    if not dry_run:
        # Import here to avoid circular dependency
        from post_tweet import post_tweet
        result = post_tweet(full_tweet)
        if result.get("error"):
            print("Tweet failed, but report is published.")
            return True  # Report still published
    else:
        print(f"   [DRY RUN] Would tweet:\n   {full_tweet}")

    print("\nDone!")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        print("\nExample:")
        print('  python publish_report.py report-2026-01-31.html "The pile doesn\'t care what I\'ve read."')
        sys.exit(1)

    report_file = sys.argv[1]
    tweet_text = sys.argv[2]
    dry_run = "--dry-run" in sys.argv

    success = publish_report(report_file, tweet_text, dry_run=dry_run)
    sys.exit(0 if success else 1)
