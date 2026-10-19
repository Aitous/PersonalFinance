# Bank Sync — Design Spec

## Goal

Automate end-to-end transaction ingestion for Chase, Discover, and Amex by using Playwright to log in, navigate to the transaction export page, and download a CSV — which is then fed into the existing import pipeline. Sync can be triggered manually ("Sync Now" button) or automatically on a nightly schedule via macOS launchd.

## Architecture

Playwright browser scrapers navigate each bank's website and download a CSV to a temp file. The CSV is passed to the existing `SyncService.import_transactions()` pipeline (which handles parsing, enrichment, deduplication, and subscription detection). Session state (cookies + localStorage) is persisted per bank in `~/.finance_sessions/` so the browser only needs to re-login when a session expires. A `POST /sync/run` endpoint triggers sync on demand; a macOS launchd plist triggers the same runner script nightly.

## Tech Stack

- **Playwright** (Python, `playwright` package) — browser automation
- **FastAPI** — new `POST /sync/run` endpoint
- **macOS launchd** — nightly schedule (plist installed via setup script)
- **Existing**: `SyncService.import_transactions()`, `parse_csv()`, `credentials_store` (Keychain), `syncs` table

---

## Session Management

**Session store path:** `~/.finance_sessions/<bank>.json`

Playwright's `browser_context.storage_state()` serializes cookies + localStorage to JSON. On each scraper run:
1. If `~/.finance_sessions/<bank>.json` exists → load it via `context.storage_state` parameter when creating the browser context.
2. Navigate to a "requires auth" page. If redirected to login → session expired.
3. If session expired → open a **visible** (non-headless) browser window, wait for the user to log in + complete 2FA, then detect when the authenticated page loads and save the new session.
4. If session valid → proceed headless.

Session files are excluded from git (add `~/.finance_sessions/` note to README; it's outside the repo so not in `.gitignore`).

---

## Bank Scrapers

Each scraper lives in `backend/sync/scrapers/<bank>.py` and implements:

```python
def download_csv(context: BrowserContext, days: int = 90) -> Path:
    """Navigate to export page and return path to downloaded CSV temp file."""
```

### Chase (`chase.py`)
1. Navigate to `https://chase.com`
2. If not logged in → raise `SessionExpiredError`
3. Navigate to account activity page
4. Set date range: today − `days` to today
5. Click "Download account activity" → select CSV format → download
6. Return path to downloaded file

### Discover (`discover.py`)
1. Navigate to `https://discover.com`
2. If not logged in → raise `SessionExpiredError`
3. Navigate to account → Download Center
4. Select date range → CSV format → download
5. Return path to downloaded file

### Amex (`amex.py`)
1. Navigate to `https://americanexpress.com`
2. If not logged in → raise `SessionExpiredError`
3. Navigate to Statements & Activity → export
4. Select date range → CSV format → download
5. Return path to downloaded file

### `SessionExpiredError`
Custom exception raised when any scraper detects it's been redirected to a login page. The runner catches this and opens a visible browser for re-login.

---

## Runner (`backend/sync/runner.py`)

```python
def run_sync(banks: list[str] = ["chase", "discover", "amex"], days: int = 90) -> dict:
```

For each bank:
1. Load session from `~/.finance_sessions/<bank>.json` if it exists
2. Try scraper headless → if `SessionExpiredError` → open visible browser, wait for login, save session, retry headless
3. Parse downloaded CSV via existing `parse_csv(path, source=bank)`
4. Pass transactions to `SyncService.import_transactions()`
5. Record result (new tx count, errors)

Returns `{"results": [{"bank": "chase", "tx_count": N}, ...], "errors": [...]}`.

Can be run directly: `python -m backend.sync.runner` (for launchd).

---

## API Endpoint

`POST /sync/run`

Request body:
```json
{ "banks": ["chase", "discover", "amex"], "days": 90 }
```
Both fields optional — defaults to all three banks, 90 days.

Response:
```json
{
  "results": [
    {"bank": "chase", "tx_count": 12, "status": "ok"},
    {"bank": "discover", "tx_count": 5, "status": "ok"},
    {"bank": "amex", "tx_count": 0, "status": "session_expired"}
  ],
  "total_new": 17
}
```

`status` values: `"ok"` | `"session_expired"` | `"error"`.

`session_expired` means the scraper opened a visible browser and is waiting for the user to log in. The endpoint returns immediately with this status rather than hanging — the user re-logs in manually and re-triggers the sync.

Registered in `backend/main.py` alongside existing routers.

---

## Frontend

### Overview page — Sync section

Add a "Sync" card to `frontend/src/pages/Overview.tsx` (below the import section):

- **"Sync Now" button** — calls `POST /sync/run`, shows spinner during request
- **Last synced** — shows the most recent `syncs` table entry per bank (from existing `GET /sync/status` or a new lightweight endpoint)
- **Per-bank status row** — Chase | Discover | Amex, each showing last sync time and new tx count from last run
- If any bank returns `session_expired` → yellow banner: "Chase session expired — open the app and log in again"

### New endpoint: `GET /sync/status`

Returns last sync record per bank:
```json
{
  "chase":    {"last_synced": "2026-05-20T23:00:00Z", "tx_count": 12},
  "discover": {"last_synced": "2026-05-20T23:00:00Z", "tx_count": 5},
  "amex":     {"last_synced": "2026-05-19T23:00:00Z", "tx_count": 0}
}
```

---

## macOS launchd Schedule

A plist file `scripts/com.personalfinance.sync.plist` installed via `scripts/install-sync-schedule.sh`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.personalfinance.sync</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/.venv/bin/python</string>
    <string>-m</string>
    <string>backend.sync.runner</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>0</integer></dict>
  <key>WorkingDirectory</key><string>/path/to/PersonalFinance</string>
  <key>StandardOutPath</key><string>/tmp/personalfinance-sync.log</string>
  <key>StandardErrorPath</key><string>/tmp/personalfinance-sync-error.log</string>
</dict>
</plist>
```

`install-sync-schedule.sh`:
1. Substitutes actual project path and venv path into the plist
2. Copies to `~/Library/LaunchAgents/`
3. Runs `launchctl load`

`uninstall-sync-schedule.sh` — reverses this.

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `backend/sync/__init__.py` | Create | Package init |
| `backend/sync/runner.py` | Create | Orchestrates multi-bank sync |
| `backend/sync/session_store.py` | Create | Load/save Playwright session state |
| `backend/sync/scrapers/__init__.py` | Create | Package init |
| `backend/sync/scrapers/base.py` | Create | `SessionExpiredError`, shared helpers |
| `backend/sync/scrapers/chase.py` | Create | Chase CSV downloader |
| `backend/sync/scrapers/discover.py` | Create | Discover CSV downloader |
| `backend/sync/scrapers/amex.py` | Create | Amex CSV downloader |
| `backend/routes/sync.py` | Modify | Add `POST /sync/run` + `GET /sync/status` |
| `frontend/src/pages/Overview.tsx` | Modify | Add Sync card |
| `frontend/src/api/sync.ts` | Create | API client for sync endpoints |
| `scripts/com.personalfinance.sync.plist` | Create | launchd plist template |
| `scripts/install-sync-schedule.sh` | Create | Install nightly schedule |
| `scripts/uninstall-sync-schedule.sh` | Create | Remove nightly schedule |

---

## Deduplication

No new logic needed. `SyncService.import_transactions()` already checks `Transaction.id` (a SHA-256 hash of `source:date:description:amount`) against the DB before inserting. Pulling 90 days every sync is safe.

---

## Out of Scope

- Windows/Linux scheduling (launchd is macOS-only)
- Bank credential storage changes (Keychain already used; session cookies are separate)
- Plaid or OFX-based sync (Playwright scraping is the chosen approach)
- Retry logic for transient network failures (fail fast, re-trigger manually)
- Multi-account support per bank (one primary account per bank)
