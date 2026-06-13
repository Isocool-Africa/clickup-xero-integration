import os
import json
import logging
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
CLICKUP_SECRET       = os.getenv("CLICKUP_WEBHOOK_SECRET", "")
CLICKUP_FOLDER_ID    = os.getenv("CLICKUP_FOLDER_ID", "")          # watched folder
XERO_CLIENT_ID       = os.getenv("XERO_CLIENT_ID", "")
XERO_CLIENT_SECRET   = os.getenv("XERO_CLIENT_SECRET", "")
XERO_REFRESH_TOKEN   = os.getenv("XERO_REFRESH_TOKEN", "")         # stored, updated each refresh
XERO_TENANT_ID       = os.getenv("XERO_TENANT_ID", "")
XERO_TOKEN_FILE      = "xero_token.json"                           # persists refreshed tokens

# ── Xero token management ─────────────────────────────────────────────────────

def _load_token() -> dict:
    """Load persisted token data from file."""
    if os.path.exists(XERO_TOKEN_FILE):
        with open(XERO_TOKEN_FILE) as f:
            return json.load(f)
    return {"refresh_token": XERO_REFRESH_TOKEN, "access_token": None, "expires_at": 0}


def _save_token(data: dict):
    with open(XERO_TOKEN_FILE, "w") as f:
        json.dump(data, f)


def get_xero_access_token() -> str:
    """Return a valid Xero access token, refreshing if needed."""
    token_data = _load_token()
    now = datetime.utcnow().timestamp()

    if token_data.get("access_token") and now < token_data.get("expires_at", 0) - 60:
        return token_data["access_token"]

    # Refresh
    resp = requests.post(
        "https://identity.xero.com/connect/token",
        data={
            "grant_type":    "refresh_token",
            "refresh_token": token_data.get("refresh_token") or XERO_REFRESH_TOKEN,
            "client_id":     XERO_CLIENT_ID,
            "client_secret": XERO_CLIENT_SECRET,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()

    token_data = {
        "access_token":  result["access_token"],
        "refresh_token": result.get("refresh_token", token_data["refresh_token"]),
        "expires_at":    now + result.get("expires_in", 1800),
    }
    _save_token(token_data)
    logger.info("Xero token refreshed successfully.")
    return token_data["access_token"]


# ── Xero quote creation ───────────────────────────────────────────────────────

def create_xero_quote(task_name: str, description: str, assignee: str) -> dict:
    """Create a quote in Xero and return the API response."""
    access_token = get_xero_access_token()

    quote_date  = datetime.utcnow().strftime("%Y-%m-%d")
    expiry_date = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")

    payload = {
        "QuoteNumber":  f"QU-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "Title":        task_name,
        "Summary":      description or "",
        "Reference":    f"ClickUp Task — Assignee: {assignee or 'Unassigned'}",
        "Date":         f"/Date({int(datetime.utcnow().timestamp() * 1000)}+0000)/",
        "ExpiryDate":   f"/Date({int((datetime.utcnow() + timedelta(days=30)).timestamp() * 1000)}+0000)/",
        "Status":       "DRAFT",
        "LineItems": [
            {
                "Description": description or task_name,
                "Quantity":    1,
                "UnitAmount":  0.00,
                "AccountCode": "200",  # update to your Xero revenue account
            }
        ],
    }

    resp = requests.post(
        "https://api.xero.com/api.xro/2.0/Quotes",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Xero-Tenant-Id": XERO_TENANT_ID,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        },
        json={"Quotes": [payload]},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── ClickUp helpers ───────────────────────────────────────────────────────────

def get_task_folder_id(task: dict) -> str | None:
    """Extract the folder ID from a ClickUp task object (best-effort)."""
    # Try multiple locations ClickUp uses depending on webhook version
    return (
        task.get("folder", {}).get("id")
        or task.get("list", {}).get("folder", {}).get("id")
        or task.get("folder_id")
        or task.get("list", {}).get("folder_id")
    )


def extract_assignee(task: dict) -> str:
    assignees = task.get("assignees", [])
    if assignees:
        a = assignees[0]
        return a.get("username") or a.get("email") or str(a.get("id", ""))
    return "Unassigned"


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.route("/webhook/clickup", methods=["POST"])
def clickup_webhook():
    """Receives ClickUp webhook events and creates a Xero quote on task creation."""

    # Optional: validate ClickUp webhook signature
    if CLICKUP_SECRET:
        sig = request.headers.get("X-Signature", "")
        import hmac, hashlib
        expected = hmac.new(
            CLICKUP_SECRET.encode(), request.data, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            logger.warning("Webhook signature mismatch — request rejected.")
            return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Empty payload"}), 400

    event = data.get("event", "")
    logger.info(f"Received ClickUp event: {event}")

    # Only act on task creation
    if event != "taskCreated":
        return jsonify({"status": "ignored", "reason": "not a taskCreated event"}), 200

    task = data.get("task", {})
    logger.info(f"Task payload keys: {list(task.keys())}")
    logger.info(f"Task list: {task.get('list', {})} | folder: {task.get('folder', {})} | folder_id: {task.get('folder_id')}")

    # Filter by folder if CLICKUP_FOLDER_ID is set
    if CLICKUP_FOLDER_ID:
        folder_id = get_task_folder_id(task)
        # Also check if the list's folder matches via the list_id → lookup not needed
        # ClickUp sometimes sends list_id only — check if task list id is 901523176905 (Job Cards)
        list_id = str(task.get("list", {}).get("id") or task.get("list_id") or "")
        if str(folder_id) != str(CLICKUP_FOLDER_ID) and list_id != "901523176905":
            logger.info(f"Task folder {folder_id!r} / list {list_id!r} != watched folder {CLICKUP_FOLDER_ID!r} — skipping.")
            return jsonify({"status": "ignored", "reason": "wrong folder"}), 200

    task_name   = task.get("name", "Unnamed Task")
    description = task.get("description", "") or task.get("text_content", "")
    assignee    = extract_assignee(task)

    logger.info(f"Creating Xero quote for task: {task_name!r} — assignee: {assignee}")

    try:
        result = create_xero_quote(task_name, description, assignee)
        quotes = result.get("Quotes", [])
        quote_id = quotes[0].get("QuoteID") if quotes else None
        logger.info(f"Xero quote created: {quote_id}")
        return jsonify({"status": "success", "xero_quote_id": quote_id}), 201
    except requests.HTTPError as e:
        logger.error(f"Xero API error: {e.response.text}")
        return jsonify({"error": "Xero API error", "detail": e.response.text}), 502
    except Exception as e:
        logger.exception("Unexpected error creating Xero quote")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
