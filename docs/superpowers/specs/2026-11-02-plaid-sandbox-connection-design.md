# Plaid Sandbox Connection Design

## Intent

Prepare the local finance app to automate bank data connections through Plaid. Start with a Sandbox-only path that validates Plaid Link, token exchange, and transaction cursor sync without introducing synthetic transactions into the user's real finance data.

## Why now

The current app imports user-downloaded CSVs and can also sync through direct OFX credentials. CSV imports are reliable but manual. Plaid could provide institution-authorized connections and incremental transaction updates, while Sandbox lets us validate the connection lifecycle before using real accounts.

## Goals

- Let the user save Plaid Sandbox client credentials through Settings.
- Store Plaid client secrets and Item access tokens only in macOS Keychain; never return them to the frontend, database, or logs.
- Start Plaid Link from the local React app using a short-lived Link token created by the FastAPI backend.
- Exchange the Link public token on the backend, retain the access token in Keychain, and store non-secret Item metadata and sync cursor in SQLite.
- List and remove Sandbox Items. Removing an Item should revoke it at Plaid and delete its local token and metadata.
- Call `/transactions/sync`, handle pagination, and persist the cursor only after a complete response. Surface sync status and counts in Settings.
- Keep Sandbox transaction rows out of the main `transactions` table and all spending analytics.
- Keep the CSV inbox and current OFX sync usable.

## Non-goals

- Import real bank data or enable Plaid Production in this phase.
- Add a public webhook endpoint, hosted backend, or tunnel. This app runs on localhost; Sandbox sync is user-triggered.
- Remove or change CSV and OFX import behavior.
- Add Plaid balances, payments, recurring transactions, or other paid products.

## User experience

1. In Settings, the user selects Sandbox and enters Plaid Sandbox Client ID and Secret. The UI confirms only whether credentials are configured.
2. The user chooses “Connect test account” to launch Plaid Link.
3. On successful Link, the frontend sends the one-time public token to the local backend. The backend exchanges it and stores the access token in Keychain.
4. Settings displays institution, connected account masks, environment, and sync status. “Sync test transactions” retrieves cursor-based updates and shows added/modified/removed counts, but does not change the user's transaction data.
5. The user can remove a test Item, which revokes it remotely and clears its local token and metadata.

## Technical decisions

- Use the current Plaid Link Web SDK loaded directly from Plaid's CDN, not bundled or vendored.
- Use backend requests to Plaid over HTTPS. Plaid credentials, access tokens, and cursors never go into browser storage or logs. The cursor is non-secret but remains in the database beside its Item metadata.
- Record environment per Item so a future production connection cannot accidentally reuse a Sandbox token or cursor.
- Support multiple Sandbox Items, connected one institution at a time. Each Item has its own token and cursor.
- Use a stable local identifier for each Item; one Plaid Item can contain multiple accounts.
- Follow the complete `/transactions/sync` pagination contract. Accumulate pages from the original cursor and commit the new cursor only after `has_more` is false. Retry a mutation-during-pagination from the original cursor.
- Treat Sandbox data as synthetic. Discard transaction row bodies after each complete sync; persist only the cursor, latest sync time/status, and update counts. This validates cursor sync without creating a second transaction store or putting synthetic data in the real one.
- No live Plaid credentials or bank login are needed to implement this phase; the user will supply Sandbox API credentials in Settings to exercise it.

## Open implementation details left to the builder

- Exact SQLite model names and route names, following existing project conventions.
- How to display Plaid API errors without leaking request bodies, credentials, or tokens.
- Whether the Plaid Link script is loaded globally or on demand, using the simplest secure fit for the current Vite app.

## Later phase

After Sandbox linking and cursor sync work, design Production imports separately. That phase must handle up to 24 months of history, account mapping, duplicate overlap with CSV/OFX history, pending-to-posted transitions, modified/removed transactions, transaction provenance, and explicit disconnection to control subscription billing.
