#!/bin/bash
# Cron job wrapper for Claude Code Moltbook posting
# Runs a one-shot claude instance to make a single post
# Usage: ./cron_post.sh
# Cron: */30 * * * * /Users/bedwards/moltbook/scripts/cron_post.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$HOME/.config/moltbook/logs"
LOCK_FILE="$HOME/.config/moltbook/cron.lock"

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

cd "$PROJECT_DIR"

# Run claude in one-shot mode with the posting prompt
# --dangerously-skip-permissions skips tool approval prompts for automation
# --print outputs the response without interactive mode
# Full path for cron environment
CLAUDE="/Users/bedwards/.local/bin/claude"

$CLAUDE --dangerously-skip-permissions --print "
Make ONE post to Moltbook. Follow the CLAUDE.md instructions exactly.

Steps:
1. Check notifications for replies to my comments (use scripts/check_threads.py or the API)
2. If there are replies to MY comments that I haven't responded to yet, reply to ONE of them
3. Otherwise, find a thread with 4-8 comments that vibes with you and reply to a COMMENT (not the original post)
4. Use scripts/post_comment.py to post

Remember:
- Reply to a COMMENT using parent_id, not the original post
- Short response (2-4 sentences max)
- Include ASCII art
- Stay in character
- About 42% chance to include 4-6 lines of poetry/lyrics at the end

Only make ONE post total.
" >> "$LOG_FILE" 2>&1

log "Claude Code finished"
