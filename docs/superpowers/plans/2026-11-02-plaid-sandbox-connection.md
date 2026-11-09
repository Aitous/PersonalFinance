# Plaid Sandbox Connection Implementation Plan

> **For agentic workers:** Implement the two tasks below in order. Do not commit or revert unrelated workspace changes.

**Goal:** Add a local Plaid Sandbox connection flow that validates Link and incremental transaction sync without changing real finance data.

**Architecture:** FastAPI creates Link tokens, exchanges public tokens, calls Plaid's Sandbox API, and stores Item tokens in macOS Keychain. SQLite stores non-secret Item metadata, account display data, cursor, and latest sync summary. The React Settings page lets the user configure Sandbox credentials, link multiple test Items, sync update counts, and remove Items.

**Tech Stack:** FastAPI, requests, SQLAlchemy, macOS Keychain via keyring, React, TypeScript, Plaid Link Web SDK.

**Spec:** `docs/superpowers/specs/2026-11-02-plaid-sandbox-connection-design.md`

## Global Constraints

- This phase supports Plaid Sandbox only; do not add Production connections.
- Plaid Client ID, Secret, access tokens, and public tokens must never be returned to the browser after use, stored in SQLite, or logged.
- Sandbox transaction rows must never be inserted into the main `transactions` table or a separate row store.
- Store each Item's cursor only after every page of `/transactions/sync` has completed.
- Do not add a public webhook endpoint; sync is user-triggered.
- Preserve existing CSV inbox and OFX behaviors.
- Do not commit or revert unrelated workspace changes.

## Review Focus

- Plaid API errors, logs, and UI responses must not disclose secrets or token payloads.
- A failed paginated sync must leave the prior cursor intact.
- Switching or reconnecting Items must not reuse a cursor or token across Items.
- Removing an Item must not erase its local token if remote revocation fails.
- Multiple accounts within one Item and multiple Items must display and remove independently.
- Sandbox API access must never create synthetic rows in the main transaction table.

---

### Task 1: Plaid Sandbox backend and secure state

**Files:**
- Create: `backend/plaid_client.py`
- Create: `backend/routes/plaid.py`
- Modify: `backend/credentials.py`
- Modify: `backend/db/models.py`
- Modify: `backend/db/database.py`
- Modify: `backend/main.py`

- [ ] Add Keychain operations for Sandbox Client ID, Secret, and per-Item access tokens, with delete support.
- [ ] Add a Plaid Item model for environment, institution/account display metadata, cursor, and latest sync summary; migrate existing SQLite additively.
- [ ] Implement fixed-host HTTPS Plaid Sandbox calls for Link token creation, public-token exchange, accounts/item metadata, paginated `/transactions/sync`, and Item removal.
- [ ] Retry pagination mutation from the original cursor and commit a new cursor only after all pages finish.
- [ ] Add config status/save, list Items, create Link token, exchange token, sync Item, and remove Item routes. Sanitize provider errors.
- [ ] Ensure Sandbox sync stores only status/counts/cursor and never inserts transaction rows.
- [ ] Verify by Python compilation and `git diff --check`.

### Task 2: Settings connection experience

**Files:**
- Create: `frontend/src/components/PlaidConnections.tsx`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/index.css`
- Modify: `frontend/index.html`

- [ ] Load Plaid Link directly from Plaid's CDN and use a one-time backend-created Link token.
- [ ] Add Sandbox credential entry without ever reading back the secret; provide connection, sync, and removal controls.
- [ ] Display institution/account masks, connection status, and added/modified/removed sync counts; state clearly that Sandbox records are synthetic and are not added to spending data.
- [ ] Show progress and sanitized errors; allow multiple independent Sandbox Items.
- [ ] Verify with the production frontend build and `git diff --check`.
