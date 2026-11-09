# Multi-user Beta Foundation Implementation Plan

> **For agentic workers:** Implement this plan task-by-task in the current workspace after the owner approves the design and hosting choice. Do not revert unrelated workspace work.

**Goal:** Prepare a private, invite-only hosted beta with tenant isolation, managed AI access, per-user budgets, account lifecycle controls, and user-owned Plaid syncing.

**Architecture:** Use managed authentication to establish a verified owner ID, relational PostgreSQL storage with owner-scoped records and defensive row policies, and a FastAPI service that remains the only writer. Store provider credentials as deployment secrets, meter AI use before calls, and process Plaid webhook notifications through an idempotent background queue.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, React, managed OIDC/email authentication, hosted secret manager, Plaid webhooks.

**Spec:** `docs/superpowers/specs/2026-11-02-multi-user-beta-design.md`

## Implementation progress

- Implemented: Supabase asymmetric-JWKS token verification, email-link sign-in UI, owner scoping in SQLAlchemy and PostgreSQL RLS, owner-aware transaction/cache IDs, local SQLite owner migration utility, managed service LLM keys, request quotas, first-use AI consent, encrypted per-owner Plaid tokens, account export/deletion, and hosted-mode restrictions for local filesystem imports.
- Not yet deployed: the owner must provide/configure Supabase and hosting credentials. Production Plaid webhooks and a durable cross-restart job worker remain release work.

## Global Constraints

- No public signup during the private pilot.
- Owner identity comes only from a verified auth token.
- No request may read or mutate data without owner scoping.
- End users never receive or supply Plaid or LLM provider secrets.
- Existing local data must remain recoverable and be assigned to the owner's first user account.
- Reconnect Plaid in hosted storage; do not export access tokens from macOS Keychain.
- Keep Plaid sandbox and production items separate.
- No user prompt/transaction content in usage logs.
- Preserve existing transaction/category/report behavior within each tenant.

## Review Focus

- Unauthenticated, expired, invalid-audience, and cross-owner access attempts.
- Cross-tenant leakage through analytics, global merchant aliases/rules, caches, search, export, and background jobs.
- Concurrent AI requests crossing account or global usage limits.
- Forged/replayed Plaid webhooks and duplicate webhook delivery.
- Partial account deletion when Plaid revocation or storage cleanup fails.
- Local-to-hosted migration restart, duplicate retry, and rollback behavior.

---

### Task 1: Hosted database and owner schema

**Files:**
- Modify: `backend/db/models.py`, `backend/db/database.py`
- Create: `backend/db/migrations/` migration setup and initial PostgreSQL migration
- Modify: `backend/requirements.txt`, deployment configuration, and `README.md`

- [x] Configure a managed PostgreSQL URL and bounded connection-pool settings.
- [x] Add owner identity fields and indexes to user-owned models; scope ORM reads/writes, enable PostgreSQL RLS, and namespace deterministic transaction/cache IDs.
- [ ] Replace startup schema creation with versioned migrations for production; retain an explicit local SQLite option.
- [x] Add a one-time migration command that backs up local SQLite data and assigns its rows to the invited owner. The copy is transactional and refuses to mix data into an already-populated owner.

### Task 2: Authentication, invite flow, and owner-scoped API

**Files:**
- Create: `backend/auth.py`, `backend/routes/auth_admin.py`, auth-related frontend components
- Modify: `backend/main.py` and every route/service using `get_session()`
- Modify: `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/components/Sidebar.tsx`

- [x] Verify Supabase JWT signature, issuer, audience, expiry, and subject; reject missing/invalid credentials in hosted mode.
- [ ] Add an in-app operator invite flow and `/me` endpoint. Invitations are currently issued from the Supabase dashboard; public signup is absent.
- [x] Add owner-scoped database/session helpers and scope API queries, mutations, export, cache, catalog, search, and request-launched background work.
- [x] Add email-link sign-in, auth callback, logout, and protected-route behavior; keep bearer tokens in memory.
- [ ] Add CORS, cookie/CSRF, and rate-limit settings for the chosen host and frontend origin.

### Task 3: Managed LLM provider and usage budgets

**Files:**
- Modify: `backend/llm/factory.py`, provider adapters, and all LLM entry points
- Modify: `backend/db/models.py` and migration for usage accounting
- Modify: `backend/routes/settings.py`, AI endpoints, and frontend settings/AI controls

- [x] Load provider keys only from deployment environment; remove end-user key entry from hosted settings.
- [x] Add serialized per-user monthly request reservation and a global daily request circuit breaker before provider calls. Dollar/token budgets await provider usage reporting.
- [x] Persist request status, feature, model, user, and timestamp without prompt or transaction text.
- [ ] Apply common budget checks to enrichment, re-categorization, transaction Q&A, savings tips, and cached explanations; avoid charging for cache hits.
- [ ] Surface allowance, reset time, and deterministic behavior when AI quota is exhausted.

### Task 4: Export, deletion, consent, and operational safeguards

**Files:**
- Create: account lifecycle routes/services and export worker
- Modify: route registration, models/migrations, frontend Settings/privacy screens
- Create: `docs/operations/` runbooks and privacy/data-flow material

- [x] Add owner-scoped export of transactions, accounts, subscriptions, imports, rules, aliases, Plaid metadata, and sync history.
- [x] Add account deletion after Plaid disconnect, removing tenant data and the Supabase identity.
- [x] Add first-use AI data disclosure/consent and consent revocation.
- [ ] Document backup, restore, incident, data-deletion, and secret-rotation procedures.

### Task 5: Per-user Production Plaid and verified update processing

**Files:**
- Modify: `backend/routes/plaid.py`, `backend/plaid_client.py`, `backend/db/models.py`
- Create: webhook verification, durable sync queue, and webhook routes
- Modify: `frontend/src/components/PlaidConnections.tsx`

- [x] Bind Items/tokens/accounts/transaction identities to the authenticated owner and encrypt tokens with a managed application key.
- [ ] Verify Plaid webhook signatures/environment, enqueue deduplicated update jobs, and process every change under the Item owner.
- [x] Keep manual sync and last-update visibility; ensure removal revokes only Items belonging to that owner.
- [ ] Add deployment docs for HTTPS webhook URL, Plaid dashboard allowlists/production settings, and webhook key rotation.

### Task 6: Hosted owner migration and release gate

**Files:**
- Create: deployment and migration/rollback runbooks
- Modify: frontend API base URL configuration and health endpoints

- [ ] Deploy with public signup disabled and only the owner's invitation enabled.
- [ ] Snapshot the current SQLite database, run migration once, reconcile totals/row counts, and reconnect Plaid through the hosted UI.
- [ ] Confirm per-user isolation and operational recovery before issuing any external invites.
