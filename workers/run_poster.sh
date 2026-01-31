#!/bin/bash
# Run the Moltbook poster worker via Claude Code
# Called by cron every 31 minutes

cd /Users/bedwards/moltbook

# Log file for this run
LOG_DIR="/Users/bedwards/moltbook/workers/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/poster_$(date +%Y%m%d_%H%M%S).log"

echo "Starting poster worker at $(date)" >> "$LOG_FILE"

# Run Claude Code with the poster instructions
# --print: non-interactive mode, just print output
# -p: prompt to execute
claude --print \
  -p "You are the Moltbook poster worker. Read ~/moltbook/workers/CLAUDE_POSTER.md for your instructions. Execute your task: post ONE pending item from the queue, update status, and exit." \
  >> "$LOG_FILE" 2>&1

echo "Finished at $(date)" >> "$LOG_FILE"

# Keep only last 100 log files
ls -t "$LOG_DIR"/poster_*.log 2>/dev/null | tail -n +101 | xargs rm -f 2>/dev/null
