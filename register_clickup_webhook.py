"""
One-time script to register the ClickUp webhook for your target folder.

Usage:
  python register_clickup_webhook.py
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_TOKEN", "")  # your personal/team API token
CLICKUP_FOLDER_ID = os.getenv("CLICKUP_FOLDER_ID", "")
PUBLIC_URL        = os.getenv("PUBLIC_URL", "")          # e.g. https://yourapp.railway.app

if not all([CLICKUP_API_TOKEN, CLICKUP_FOLDER_ID, PUBLIC_URL]):
    print("ERROR: Set CLICKUP_API_TOKEN, CLICKUP_FOLDER_ID, and PUBLIC_URL in your .env first.")
    raise SystemExit(1)

endpoint = f"{PUBLIC_URL.rstrip('/')}/webhook/clickup"

# ClickUp webhooks are registered at the workspace (team) level
# First, get the workspace ID
teams_resp = requests.get(
    "https://api.clickup.com/api/v2/team",
    headers={"Authorization": CLICKUP_API_TOKEN},
    timeout=10,
)
teams_resp.raise_for_status()
teams = teams_resp.json().get("teams", [])

if not teams:
    print("ERROR: No ClickUp workspaces found.")
    raise SystemExit(1)

if len(teams) == 1:
    team_id = teams[0]["id"]
    print(f"Using workspace: {teams[0]['name']} ({team_id})")
else:
    print("Multiple workspaces found:")
    for i, t in enumerate(teams):
        print(f"  [{i}] {t['name']} — {t['id']}")
    idx = int(input("Select workspace number: "))
    team_id = teams[idx]["id"]

payload = {
    "endpoint": endpoint,
    "events":   ["taskCreated"],
    "folder_id": int(CLICKUP_FOLDER_ID),
}

resp = requests.post(
    f"https://api.clickup.com/api/v2/team/{team_id}/webhook",
    headers={
        "Authorization": CLICKUP_API_TOKEN,
        "Content-Type":  "application/json",
    },
    json=payload,
    timeout=10,
)
resp.raise_for_status()
result = resp.json()

webhook_id = result.get("id") or result.get("webhook", {}).get("id")
secret     = result.get("webhook", {}).get("secret", "(check ClickUp dashboard)")

print(f"\n✅  Webhook registered!")
print(f"   Webhook ID : {webhook_id}")
print(f"   Endpoint   : {endpoint}")
print(f"   Secret     : {secret}")
print(f"\nAdd this to your .env:\n  CLICKUP_WEBHOOK_SECRET={secret}")
