#!/usr/bin/env python3
"""
OAuth2 PKCE setup for X API using the official XDK.

To get client_id and client_secret:
1. Go to https://console.x.com
2. Create or select your app
3. Enable OAuth 2.0 in app settings
4. Set redirect_uri to: http://localhost:3000/callback
5. Copy client_id and client_secret

Usage:
    python x_oauth2_setup.py setup      # Start OAuth flow
    python x_oauth2_setup.py callback   # Complete OAuth flow with callback URL
    python x_oauth2_setup.py test       # Test posting
"""

import sys
import json
from pathlib import Path

CREDENTIALS_PATH = Path.home() / ".config" / "moltbook" / "x_credentials.json"
STATE_PATH = Path.home() / ".config" / "moltbook" / "x_oauth_state.json"

def load_credentials():
    if CREDENTIALS_PATH.exists():
        return json.loads(CREDENTIALS_PATH.read_text())
    return {}

def save_credentials(creds):
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text(json.dumps(creds, indent=2))

def save_state(state):
    STATE_PATH.write_text(json.dumps(state))

def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}

def setup():
    """Start OAuth2 PKCE flow."""
    from xdk.oauth2_auth import OAuth2PKCEAuth

    creds = load_credentials()

    if not creds.get("client_id"):
        print("Missing client_id in credentials.")
        print("\nTo get client_id:")
        print("1. Go to https://console.x.com")
        print("2. Select your app")
        print("3. Go to Settings > User authentication settings")
        print("4. Enable OAuth 2.0")
        print("5. Set redirect URI to: http://localhost:3000/callback")
        print("6. Copy the Client ID")
        print("\nAdd to ~/.config/moltbook/x_credentials.json:")
        print('  "client_id": "your_client_id"')
        return

    # Scopes needed for posting tweets
    scopes = ["tweet.read", "tweet.write", "users.read", "offline.access"]

    auth = OAuth2PKCEAuth(
        client_id=creds["client_id"],
        client_secret=creds.get("client_secret"),  # Optional for public clients
        redirect_uri="http://localhost:3000/callback",
        scope=scopes
    )

    auth_url = auth.get_authorization_url()
    code_verifier = auth.get_code_verifier()

    # Save state for callback step
    save_state({
        "code_verifier": code_verifier,
        "client_id": creds["client_id"],
        "client_secret": creds.get("client_secret"),
        "scopes": scopes
    })

    print("\n" + "="*60)
    print("OAuth2 PKCE Authorization")
    print("="*60)
    print("\n1. Open this URL in your browser:\n")
    print(auth_url)
    print("\n2. Authorize the app")
    print("\n3. After redirect, copy the FULL callback URL")
    print("   (it will look like: http://localhost:3000/callback?code=...)")
    print("\n4. Run: python x_oauth2_setup.py callback '<paste_url_here>'")
    print("="*60)

def callback(callback_url: str):
    """Complete OAuth2 flow with callback URL."""
    from xdk.oauth2_auth import OAuth2PKCEAuth
    from urllib.parse import urlparse, parse_qs

    state = load_state()
    if not state:
        print("No OAuth state found. Run 'setup' first.")
        return

    # Extract code from callback URL
    parsed = urlparse(callback_url)
    params = parse_qs(parsed.query)

    if "code" not in params:
        print("No authorization code found in URL.")
        print("URL should contain ?code=...")
        return

    code = params["code"][0]

    auth = OAuth2PKCEAuth(
        client_id=state["client_id"],
        client_secret=state.get("client_secret"),
        redirect_uri="http://localhost:3000/callback",
        scope=state["scopes"]
    )

    # Set the code verifier from saved state
    auth._code_verifier = state["code_verifier"]

    try:
        token = auth.exchange_code(code)

        # Save tokens to credentials
        creds = load_credentials()
        creds["oauth2_token"] = token
        save_credentials(creds)

        # Clean up state file
        STATE_PATH.unlink(missing_ok=True)

        print("\n" + "="*60)
        print("SUCCESS! OAuth2 tokens saved.")
        print("="*60)
        print(f"\nAccess token expires in: {token.get('expires_in', 'unknown')} seconds")
        print(f"Refresh token: {'Yes' if token.get('refresh_token') else 'No'}")
        print("\nYou can now post tweets!")
        print("Run: python x_oauth2_setup.py test")

    except Exception as e:
        print(f"Error exchanging code: {e}")

def test():
    """Test posting a tweet."""
    from xdk import Client
    from xdk.oauth2_auth import OAuth2PKCEAuth

    creds = load_credentials()

    if not creds.get("oauth2_token"):
        print("No OAuth2 token found. Run 'setup' first.")
        return

    auth = OAuth2PKCEAuth(
        client_id=creds["client_id"],
        client_secret=creds.get("client_secret"),
        redirect_uri="http://localhost:3000/callback",
        token=creds["oauth2_token"]
    )

    # Refresh if expired
    if auth.is_token_expired():
        print("Token expired, refreshing...")
        new_token = auth.refresh_token()
        creds["oauth2_token"] = new_token
        save_credentials(creds)

    client = Client(auth=auth)

    # Test by getting user info
    try:
        me = client.users.me()
        print(f"\nAuthenticated as: @{me.data.username}")
        print(f"User ID: {me.data.id}")
        print("\nReady to post tweets!")
    except Exception as e:
        print(f"Error: {e}")

def post_tweet(text: str):
    """Post a tweet."""
    from xdk import Client
    from xdk.oauth2_auth import OAuth2PKCEAuth

    creds = load_credentials()

    if not creds.get("oauth2_token"):
        print("No OAuth2 token found. Run 'setup' first.")
        return None

    auth = OAuth2PKCEAuth(
        client_id=creds["client_id"],
        client_secret=creds.get("client_secret"),
        redirect_uri="http://localhost:3000/callback",
        token=creds["oauth2_token"]
    )

    # Refresh if expired
    if auth.is_token_expired():
        print("Token expired, refreshing...")
        new_token = auth.refresh_token()
        creds["oauth2_token"] = new_token
        save_credentials(creds)

    client = Client(auth=auth)

    try:
        result = client.posts.create(text=text)
        print(f"Tweet posted! ID: {result.data.id}")
        return result.data
    except Exception as e:
        print(f"Error posting tweet: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "setup":
        setup()
    elif cmd == "callback":
        if len(sys.argv) < 3:
            print("Usage: python x_oauth2_setup.py callback '<callback_url>'")
            sys.exit(1)
        callback(sys.argv[2])
    elif cmd == "test":
        test()
    elif cmd == "tweet":
        if len(sys.argv) < 3:
            print("Usage: python x_oauth2_setup.py tweet '<text>'")
            sys.exit(1)
        post_tweet(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
