#!/bin/bash
# Post a comment to Moltbook
# Usage: ./post_comment.sh <post_id> <content>

API_KEY=$(cat ~/.config/moltbook/credentials.json | python3 -c "import json,sys; print(json.load(sys.stdin)['api_key'])")
POST_ID="$1"
CONTENT="$2"

curl -s -X POST "https://www.moltbook.com/api/v1/comments" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "$(python3 -c "import json; print(json.dumps({'post_id': '$POST_ID', 'content': '''$CONTENT'''}))")"
