# Multi-user Beta Foundation Design

## Intent

Turn the current local, single-user finance app into a hosted invite-only service where each person has a private account, can connect their own bank, and can use AI features without supplying an LLM key. Preserve the current owner's imported data while making the tenant boundary explicit throughout the backend.

## Current state

- FastAPI uses one global SQLite `finance.db`; `get_session()` has no user context.
- Financial and derived tables are globally queried, and API routes have no authentication.
- Plaid access tokens and LLM keys are stored in the operator Mac Keychain.
- Plaid syncing is user-triggered and there is no webhook endpoint.
- The frontend calls a fixed localhost API and has no login flow.
- AI calls read an operator-local Keychain key and are not metered per user.

## Goals

- Invite-only account creation and secure sign-in, logout, and session expiry.
- A user ID on every user-owned record, with ownership enforced in every route, background job, search/catalog query, and Plaid callback.
- A managed relational database suitable for a hosted API, with an explicit migration path that assigns existing local data to the owner's first account.
- Service-managed LLM credentials. End users never provide provider keys. Enforce per-user monthly usage limits and a platform-wide emergency spend cap before making model calls.
- Per-user Plaid Items, encrypted access tokens, and verified transaction-update webhooks with idempotent sync processing.
- User self-service data export and account deletion, including Plaid revocation and derived/cache/job cleanup.
- Keep public signup disabled during the invite-only pilot.

## Approved decisions

- Use Supabase Auth for invite-only email-link authentication and PostgreSQL for hosted storage. Keep the FastAPI backend as the only database writer, using a restricted `NOBYPASSRLS` database role; enforce `owner_id` predicates in application queries and Postgres row-level policies as defense in depth.
- Deploy the API and frontend to a managed HTTPS host; use the host's secret manager for provider credentials and an application encryption key. Do not put secrets in frontend build variables.
- Use email magic links for the first pilot; public signup is disabled and the operator invites accounts through Supabase.
- Start with a configurable monthly provider-request allowance per account plus a global daily request circuit breaker. The current provider adapters do not report token cost, so request limits are enforced until per-provider usage reporting is added.
- Preserve the owner's current ledger as the initial owner account. Reconnect Plaid in the hosted environment rather than copying access tokens out of the Mac Keychain.

## Data isolation rules

- Add an `owner_id` foreign key to transactions, accounts, subscriptions, import batches/rows, sync records, aliases/rules, enrichment jobs/items, report caches, Plaid Items/transaction identities, and usage records.
- Include owner identity in every tenant-scoped primary/unique/cache key, including transaction identity hashes, account external IDs, data revisions, and report-cache keys, so deterministic IDs from two people cannot collide.
- Derive owner ID only from a verified server-side authentication token; never trust an owner ID supplied in request JSON, query parameters, or headers.
- Every read, update, delete, aggregate, cache key, search result, background job, and webhook lookup must include owner scope.
- Use owner-scoped unique constraints for user-editable names/keys and enforce item ownership on transaction IDs and account IDs.
- Use transaction-scoped database sessions. Do not keep process-global per-user state.

## Authentication and browser behavior

- Frontend stores no bearer tokens in local storage. Use an auth SDK's secure session handling and same-site secure cookies or equivalent supported flow.
- API validates issuer, audience, expiry, signature, and subject on every non-public route.
- Invite issuance is an operator/admin operation; no open registration endpoint during the pilot.
- Rate-limit login, account recovery, AI endpoints, and Plaid link/exchange endpoints. Add CSRF protection if cookie-authenticated mutation routes are used.

## LLM budget and privacy behavior

- Keep provider keys only in deployment secret storage; backend provider selection is controlled by operator configuration.
- Record owner ID, feature, selected model, provider-reported input/output usage, estimated cost, result status, and timestamp. Do not retain prompts or transaction contents in usage logs.
- Enforce a default per-account monthly budget and configurable feature-level request ceilings; return a clear limit message and reset date when exhausted.
- Add a global daily circuit breaker and provider timeouts. Deterministic app features continue when the AI allowance is exhausted.
- Show users which AI features send transaction-derived data to a model provider and obtain the required consent before their first AI request.

## Plaid behavior

- Associate every Plaid Item and transaction identity with exactly one owner.
- Encrypt Plaid access tokens at application level using a key held only in deployment secret storage; never return tokens to clients or log webhook bodies containing sensitive data.
- Validate Plaid webhook JWT signatures and environment, acknowledge promptly, enqueue an idempotent sync job, and process `SYNC_UPDATES_AVAILABLE` using the saved Item cursor.
- Keep manual sync as a recovery action and show last successful transaction update time.
- On disconnect, revoke the Plaid Item and remove its token. On account deletion, revoke every Item before deleting all associated personal data.

## Data export and deletion

- Provide an authenticated export covering transactions, accounts, subscriptions, aliases/rules, and user settings in documented CSV/JSON formats.
- Provide deletion confirmation and a background deletion job. Revoke Plaid Items first, then remove transaction/import/job/cache/usage/user records and tokens; retries must be idempotent and report incomplete provider revocations.
- Define backup retention and deletion limitations in user-facing terms before inviting external users.

## Non-goals for this phase

- Public signup, payment processing, consumer credit products, financial advice, bill pay, or investment recommendations.
- Sharing, selling, or training general models on user transaction data.
- Migrating the user's Plaid access token from the local Keychain into hosted storage.

## Rollout

1. Land authentication, ownership schema, tenant-scoped backend access, and a one-time local-data-to-owner migration.
2. Add hosted secret management, usage metering/limits, export/delete, and frontend onboarding.
3. Add user-owned Production Plaid linking, verified webhooks, and background syncing.
4. Run an owner-only cloud migration and security review before inviting a small pilot cohort.

## Deployment status

Supabase Auth + PostgreSQL is the approved architecture. The code supports the hosted configuration, but a Supabase project, non-bypass database login, host URLs, and production secrets still need to be configured before deployment or inviting beta users.
