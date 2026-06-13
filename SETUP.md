# ClickUp → Xero Quote Integration — Setup Guide

When a task is created in a specific ClickUp folder, this Flask app automatically
creates a **Draft Quote** in Xero using the task name, description, and assignee.

---

## Prerequisites

- Python 3.11+
- A **Xero Developer** account with an app created at https://developer.xero.com/app/manage
- A **ClickUp** account with API access
- A public URL for your server (Railway, Render, Fly.io, ngrok for local testing)

---

## Step 1 — Install dependencies

```bash
pip install -r requirements.txt
```

---

## Step 2 — Configure your Xero Developer App

1. Go to https://developer.xero.com/app/manage and create a new app (or use an existing one).
2. Set the **Redirect URI** to `http://localhost:8080/callback`.
3. Copy your **Client ID** and **Client Secret**.
4. Add them to `.env` (copy `.env.example` → `.env`).

---

## Step 3 — Get your Xero tokens (one-time)

```bash
python get_xero_tokens.py
```

This opens a browser window for Xero OAuth. After authorising, it prints your
`XERO_REFRESH_TOKEN` and `XERO_TENANT_ID` — add both to your `.env`.

---

## Step 4 — Find your ClickUp Folder ID

Open ClickUp in your browser and navigate to the folder you want to watch.
The URL will look like:

```
https://app.clickup.com/12345678/v/li/901234567890
```

The folder ID is visible in **Space Settings → Folder → right-click → Copy link**,
or you can call the ClickUp API:

```bash
curl -H "Authorization: YOUR_API_TOKEN" \
  "https://api.clickup.com/api/v2/space/YOUR_SPACE_ID/folder"
```

Add the folder ID to your `.env` as `CLICKUP_FOLDER_ID`.

---

## Step 5 — Deploy the Flask app

### Option A — Railway (recommended, free tier available)

1. Push this folder to a GitHub repo.
2. Go to https://railway.app → New Project → Deploy from GitHub.
3. Add all `.env` variables in the Railway dashboard under **Variables**.
4. Railway auto-detects the `Procfile` and deploys. Note your public URL.

### Option B — Render

1. Create a new **Web Service** pointing to your repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
4. Add environment variables in the Render dashboard.

### Option C — Local testing with ngrok

```bash
# Terminal 1
python app.py

# Terminal 2
ngrok http 5000
# Copy the https://xxxx.ngrok.io URL as your PUBLIC_URL
```

---

## Step 6 — Register the ClickUp webhook

Once your server is live with a public URL, add it to `.env`:

```
PUBLIC_URL=https://your-app.railway.app
CLICKUP_API_TOKEN=your_clickup_personal_api_token
```

Then run:

```bash
python register_clickup_webhook.py
```

This registers the webhook and prints the `CLICKUP_WEBHOOK_SECRET`. Add it to
your `.env` and redeploy (or restart the server).

---

## Step 7 — Test it

1. Go to your watched ClickUp folder.
2. Create a new task with a name, description, and assignee.
3. Check your Xero account under **Accounts → Sales → Quotes** — a Draft quote
   should appear within seconds.

---

## Environment Variables Reference

| Variable                  | Description                                      |
|---------------------------|--------------------------------------------------|
| `CLICKUP_WEBHOOK_SECRET`  | Secret from ClickUp webhook registration         |
| `CLICKUP_FOLDER_ID`       | ClickUp Folder ID to watch                       |
| `XERO_CLIENT_ID`          | Xero app Client ID                              |
| `XERO_CLIENT_SECRET`      | Xero app Client Secret                          |
| `XERO_REFRESH_TOKEN`      | Initial Xero refresh token (updated automatically)|
| `XERO_TENANT_ID`          | Xero organisation tenant ID                     |
| `PORT`                    | Server port (default: 5000)                     |

---

## Troubleshooting

**Xero 401 errors**: Your refresh token may have expired. Re-run `get_xero_tokens.py`.

**Webhook not firing**: Check the ClickUp webhook dashboard under
Workspace Settings → Integrations → Webhooks.

**Wrong folder**: Double-check `CLICKUP_FOLDER_ID` — tasks in sub-lists of the
folder will have the folder ID in `task.folder.id`.

**Quote has £0 amount**: That's expected — the task carries no pricing info.
Open the quote in Xero and add line item amounts before sending to a client.
