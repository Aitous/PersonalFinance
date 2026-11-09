# Plaid Production Connection and Transaction Import

## Intent

Extend the existing local, single-user Plaid Sandbox prototype so the app owner can link real Production accounts and import their transactions into the existing ledger. Sandbox remains available and visibly isolated. This phase does not make the app safe for a shared, multi-user beta.

## Goals

- Store Production client credentials and Item access tokens separately from Sandbox in macOS Keychain.
- Use fixed Plaid hosts selected from a server-side environment enum; never accept a host URL from a client.
- Start Production Link, exchange the public token server-side, list/remove Production Items, and preserve per-Item cursors.
- Import posted transaction additions, apply modifications without overwriting user-edited fields, and remove only rows owned by Plaid.
- Keep Plaid transaction IDs mapped to local ledger IDs so CSV overlap matches can still be updated or removed safely.
- Use existing categorization/enrichment job processing for newly imported purchases.
- Reconcile obvious CSV overlaps conservatively; when a match is not unambiguous, keep both rows instead of silently dropping a real purchase.
- Keep live bank sync user-triggered in this local phase. No public webhook, hosted service, or multi-user access is added.

## LLM access direction

Users of a future hosted beta should not need personal LLM API keys. The service should make model calls through an operator-managed server-side key and meter/limit use. This is a separate hosting and multi-user architecture task; this Production Plaid phase does not change provider settings or expose the current single-user instance to beta users.

## Data and update rules

- Record environment on every Plaid Item and scope credential/token lookup by environment and Item ID.
- Create/reuse local Account records keyed by environment plus Plaid account ID; store institution/account display metadata without secrets.
- Treat Plaid transaction IDs as external identities, not as permission to overwrite/delete arbitrary ledger rows.
- Ignore pending transactions in ledger totals. When posted transactions arrive, import the posted row; use Plaid's pending relationship only to prevent duplication.
- For modified rows, refresh provider-owned fields while preserving category/merchant/city fields marked as manual.
- For removed rows, delete a transaction only if it was created by Plaid and has no user edits. If it was reconciled to an existing CSV row, retain that CSV row and unlink the Plaid identity.
- Commit a cursor only after all pages are successfully applied in one sync operation. Retry pagination mutation from the original cursor.
- On successful import, invalidate derived data, reconcile recurring charges, and enqueue enrichment for new eligible rows.

## Security and rollout constraints

- Never return or log Plaid client secrets, public tokens, or access tokens.
- Keep Sandbox Items and Production Items separate in API responses and UI.
- Display that Plaid updates are periodic, not real-time; show last sync and an explicit sync control.
- Keep the app local-only until authentication, per-user ownership, database isolation, deletion/export, hosted secret management, and webhook verification are designed and implemented.

## Out of scope

- Public multi-user beta, hosted authentication, billing, webhooks, automatic scheduled sync, or bank-link sharing.
- Removing CSV/OFX import or requiring Plaid for app use.
- Per-user AI keys. Future hosted users should use a managed service key with quotas and budget controls.
