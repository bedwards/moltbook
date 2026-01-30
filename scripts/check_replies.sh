#!/bin/bash
# Check for replies to my comments
# Usage: ./check_replies.sh

API_KEY=$(cat ~/.config/moltbook/credentials.json | python3 -c "import json,sys; print(json.load(sys.stdin)['api_key'])")

echo "=== Checking notifications ==="
curl -s "https://www.moltbook.com/api/v1/notifications" \
  -H "Authorization: Bearer $API_KEY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if not d.get('success'):
    print('Error:', d.get('error'))
else:
    for n in d.get('notifications', [])[:10]:
        print(f\"[{n.get('type')}] {n.get('message', 'no message')[:80]}\")
        print(f\"  -> {n.get('link', 'no link')}\")
        print()
"
