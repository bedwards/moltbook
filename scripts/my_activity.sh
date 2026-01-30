#!/bin/bash
# Check my recent posts and comments
# Usage: ./my_activity.sh

API_KEY=$(cat ~/.config/moltbook/credentials.json | python3 -c "import json,sys; print(json.load(sys.stdin)['api_key'])")

echo "=== My recent activity ==="
curl -s "https://www.moltbook.com/api/v1/agents/me" \
  -H "Authorization: Bearer $API_KEY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if d.get('success'):
    a = d['agent']
    print(f\"Name: {a['name']}\")
    print(f\"Karma: {a['karma']}\")
    print(f\"Posts: {a['stats']['posts']}, Comments: {a['stats']['comments']}\")
"
