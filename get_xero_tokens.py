"""
One-time script to complete Xero OAuth and obtain your first refresh token.
Run this locally ONCE, copy the tokens into your .env file, then deploy the app.

Usage:
  python get_xero_tokens.py
"""

import os
import json
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.getenv("XERO_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET", "")
REDIRECT_URI  = "http://localhost:8080/callback"
SCOPE         = "accounting.transactions accounting.contacts offline_access"

AUTH_URL = (
    "https://login.xero.com/identity/connect/authorize"
    f"?response_type=code"
    f"&client_id={CLIENT_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    f"&scope={urllib.parse.quote(SCOPE)}"
    f"&state=xerosetup"
)

auth_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        auth_code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Authorised! You can close this tab.</h2>")

    def log_message(self, *args):
        pass  # silence server logs


def exchange_code(code: str) -> dict:
    resp = requests.post(
        "https://identity.xero.com/connect/token",
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": REDIRECT_URI,
            "client_id":    CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_tenant_id(access_token: str) -> str:
    resp = requests.get(
        "https://api.xero.com/connections",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    connections = resp.json()
    if not connections:
        raise RuntimeError("No Xero organisations found for this account.")
    if len(connections) == 1:
        return connections[0]["tenantId"]
    print("\nMultiple Xero organisations found:")
    for i, c in enumerate(connections):
        print(f"  [{i}] {c['tenantName']} — {c['tenantId']}")
    idx = int(input("Select organisation number: "))
    return connections[idx]["tenantId"]


if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Set XERO_CLIENT_ID and XERO_CLIENT_SECRET in your .env first.")
        raise SystemExit(1)

    print("Opening Xero authorisation page in your browser...")
    print(f"If it doesn't open automatically, visit:\n  {AUTH_URL}\n")
    webbrowser.open(AUTH_URL)

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    print("Waiting for Xero callback on http://localhost:8080/callback ...")
    server.handle_request()

    if not auth_code:
        print("ERROR: No auth code received.")
        raise SystemExit(1)

    print("Exchanging auth code for tokens...")
    tokens = exchange_code(auth_code)

    access_token  = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    print("Fetching Xero Tenant ID...")
    tenant_id = get_tenant_id(access_token)

    print("\n✅  Success! Add these to your .env file:\n")
    print(f"XERO_REFRESH_TOKEN={refresh_token}")
    print(f"XERO_TENANT_ID={tenant_id}")
    print()

    # Optionally save directly
    save = input("Save these to xero_token.json automatically? [y/N]: ").strip().lower()
    if save == "y":
        import time
        with open("xero_token.json", "w") as f:
            json.dump({
                "access_token":  access_token,
                "refresh_token": refresh_token,
                "expires_at":    time.time() + tokens.get("expires_in", 1800),
            }, f, indent=2)
        print("Saved to xero_token.json ✓")
