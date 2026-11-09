# Plaid Production Import Implementation Plan

> **For agentic workers:** Implement this plan task-by-task in this session. Do not revert unrelated workspace changes.

**Goal:** Add a Production Plaid path that imports real posted transactions into the current local ledger while preserving Sandbox and safe CSV history reconciliation.

**Architecture:** Generalize the fixed-host Plaid client around an explicit `sandbox | production` environment and use separate Keychain namespaces. Keep a Plaid external-transaction mapping table so provider additions, modifications, and removals can be applied to the right ledger row, including when a safe overlap is mapped to a pre-existing CSV transaction. Production UI is a separately labeled section in Settings.

**Tech Stack:** FastAPI, requests, SQLAlchemy/SQLite, macOS Keychain, React, TypeScript, Plaid Link Web SDK.

**Spec:** `docs/superpowers/specs/2026-11-02-plaid-production-import-design.md`

## Global Constraints

- This phase supports the app owner's local, single-user app only; do not expose it as multi-user beta.
- Sandbox and Production credentials, access tokens, Items, and cursors must never cross environments.
- Secrets and access tokens must never be returned to the browser or logged.
- Plaid pending transactions must not enter spending totals.
- Removed Plaid records must not delete unrelated CSV/OFX transactions.
- Cursor advancement happens only after the complete page set and its transaction mutations succeed.
- Keep user-triggered sync; do not add a public webhook endpoint.
- Preserve existing import and OFX behavior and all unrelated workspace edits.

## Review Focus

- A failed or mutation-interrupted multi-page sync must leave the old cursor and ledger changes intact.
- Duplicate posted rows and pending-to-posted transitions must not produce duplicate spending.
- An ambiguous CSV overlap must not silently discard a real transaction.
- A Plaid removal must not delete a CSV-origin row mapped as an overlap.
- Production Items and secrets must not be exposed in Sandbox APIs or UI, or vice versa.

---

### Task 1: Environment-aware Plaid client and secret namespaces

**Files:**
- Modify: `backend/plaid_client.py`
- Modify: `backend/routes/plaid.py`
- Modify: `backend/credentials.py` only if needed for namespace helpers
- Test: `tests/routes/test_plaid.py`

- [x] Add explicit environment selection with fixed `https://sandbox.plaid.com` and `https://production.plaid.com` hosts.
- [x] Preserve current Sandbox routes and add Production config, Link-token, exchange, list, sync, and remove operations.
- [x] Store credentials under `plaid:sandbox` and `plaid:production`; store Item tokens under separate environment namespaces.
- [x] Test that each environment selects its own host and credentials, and rejects unknown environment values.

### Task 2: Transaction identity and local account persistence

**Files:**
- Modify: `backend/db/models.py`
- Modify: `backend/db/database.py`
- Create/modify: `backend/analysis/plaid_ingestion.py`
- Test: `tests/analysis/test_plaid_ingestion.py`

- [x] Add additive SQLite migration and model for Plaid external transaction identity, including environment, Item ID, Plaid transaction ID, local transaction ID, and whether the local row is Plaid-owned.
- [x] Create/reuse local Accounts for Plaid accounts using environment-scoped external IDs.
- [x] Convert only posted Plaid records into ledger rows with stable external identity and canonical positive-expense/negative-credit amounts.
- [x] Match existing CSV rows only when source, date, amount, and merchant/description evidence produce an unambiguous one-to-one match; retain both on ambiguity.
- [x] Apply modifications while preserving user-edited fields; safely unlink removals and delete only unedited Plaid-owned rows.
- [x] Test idempotent additions, pending exclusion, overlap mapping, ambiguous overlap retention, modifications preserving manual fields, removals, and environment separation.

### Task 3: Transaction sync integration

**Files:**
- Modify: `backend/routes/plaid.py`
- Modify: `backend/db/models.py` / `backend/db/database.py` only if Task 2 requires an additional field
- Test: `tests/routes/test_plaid.py`

- [x] Apply all `/transactions/sync` pages and transaction deltas atomically; restart from the original cursor after pagination mutation.
- [x] Enqueue normal enrichment for newly imported eligible purchases, invalidate derived analytics, and reconcile recurring charges after a successful import.
- [x] Report added/modified/removed/imported/duplicate counts without exposing transaction bodies or tokens.
- [x] Test cursor rollback on failed pages, complete pagination, and a repeated sync.

### Task 4: Production Settings UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/components/PlaidConnections.tsx`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/index.css`
- Test: `frontend/tests/plaidConnections.test.mjs` if a suitable UI test harness exists

- [x] Add a clearly separate Production panel and credential form; never read back the saved secret.
- [x] Start Production Link from a Production-generated link token; list, manually sync, and remove only Production Items.
- [x] Show last sync, transaction/change counts, periodic-refresh expectations, and safe errors.
- [x] Verify the frontend production build.

## Execution note

The LLM key experience is intentionally not changed in this plan. The approved direction is a future operator-managed server key with per-user quotas in the hosted beta; the current local app can retain its existing owner-configured key.
