#!/bin/bash
# Cron job wrapper for Claude Code Moltbook posting
# Runs a one-shot claude instance to make a single post
# Usage: ./cron_post.sh
# Cron: */30 * * * * /Users/bedwards/moltbook/scripts/cron_post.sh

set -e

# Source shell profile for API keys (cron runs in minimal environment)
source ~/.zshrc 2>/dev/null || source ~/.bashrc 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$HOME/.config/moltbook"
LOG_DIR="$CONFIG_DIR/logs"
LOCK_FILE="$CONFIG_DIR/cron.lock"
STATUS_FILE="$CONFIG_DIR/cron_status.json"

mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/cron_$(date +%Y%m%d).log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Check for stale lock (older than 20 minutes)
if [ -f "$LOCK_FILE" ]; then
    lock_age=$(($(date +%s) - $(stat -f %m "$LOCK_FILE" 2>/dev/null || echo 0)))
    if [ "$lock_age" -gt 1200 ]; then
        log "Removing stale lock file (${lock_age}s old)"
        rm -f "$LOCK_FILE"
    else
        log "Another instance running (lock age: ${lock_age}s), exiting"
        exit 0
    fi
fi

# Create lock
echo $$ > "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

log "Starting Claude Code one-shot post"

# Initialize status file
echo '{"status": "starting", "started_at": "'$(date -Iseconds)'", "step": "init"}' > "$STATUS_FILE"

cd "$PROJECT_DIR"

# Full path for cron environment
CLAUDE="/Users/bedwards/.local/bin/claude"

$CLAUDE --dangerously-skip-permissions --print "
Make ONE post to Moltbook. Follow the CLAUDE.md instructions exactly.

CRITICAL: Update status as you work by running these commands:

Step 1 - Log that you're checking notifications:
  echo '['\$(date '+%Y-%m-%d %H:%M:%S')'] STEP: Checking notifications' >> ~/.config/moltbook/logs/cron_\$(date +%Y%m%d).log
  echo '{\"status\": \"running\", \"step\": \"checking_notifications\", \"timestamp\": \"'\$(date -Iseconds)'\"}' > ~/.config/moltbook/cron_status.json

Then check notifications using: python3 scripts/check_threads.py

Step 2 - Log what you found:
  echo '['\$(date '+%Y-%m-%d %H:%M:%S')'] STEP: Found X replies / no replies' >> ~/.config/moltbook/logs/cron_\$(date +%Y%m%d).log
  echo '{\"status\": \"running\", \"step\": \"analyzing_threads\", \"found\": \"...\", \"timestamp\": \"'\$(date -Iseconds)'\"}' > ~/.config/moltbook/cron_status.json

Step 3 - If no replies to respond to, browse the feed:
  echo '['\$(date '+%Y-%m-%d %H:%M:%S')'] STEP: Browsing feed for threads' >> ~/.config/moltbook/logs/cron_\$(date +%Y%m%d).log

Use curl to get the feed:
  curl -s 'https://www.moltbook.com/api/v1/feed?sort=new&limit=20' -H \"Authorization: Bearer \$(cat ~/.config/moltbook/credentials.json | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"api_key\"])')\"

Step 4 - Log your choice:
  echo '['\$(date '+%Y-%m-%d %H:%M:%S')'] STEP: Chose thread: <title>' >> ~/.config/moltbook/logs/cron_\$(date +%Y%m%d).log
  echo '{\"status\": \"running\", \"step\": \"composing_reply\", \"thread\": \"...\", \"timestamp\": \"'\$(date -Iseconds)'\"}' > ~/.config/moltbook/cron_status.json

Step 5 - Post and log result:
  python3 scripts/post_comment.py <post_id> '<content>' [parent_id]
  echo '['\$(date '+%Y-%m-%d %H:%M:%S')'] STEP: Posted comment to <thread>' >> ~/.config/moltbook/logs/cron_\$(date +%Y%m%d).log
  echo '{\"status\": \"completed\", \"step\": \"posted\", \"thread\": \"...\", \"timestamp\": \"'\$(date -Iseconds)'\"}' > ~/.config/moltbook/cron_status.json

If anything fails:
  echo '['\$(date '+%Y-%m-%d %H:%M:%S')'] ERROR: <what went wrong>' >> ~/.config/moltbook/logs/cron_\$(date +%Y%m%d).log
  echo '{\"status\": \"error\", \"error\": \"...\", \"timestamp\": \"'\$(date -Iseconds)'\"}' > ~/.config/moltbook/cron_status.json

Rules for posting:
- Reply to a COMMENT using parent_id, not the original post
- Find threads with 4-8 comments
- Short response (2-4 sentences max)
- Include ASCII art
- Stay in character per CLAUDE.md
- About 42% chance to include 4-6 lines of poetry/lyrics at the end
- Only make ONE post total
" >> "$LOG_FILE" 2>&1

log "Claude Code finished"
cat "$STATUS_FILE" >> "$LOG_FILE"
