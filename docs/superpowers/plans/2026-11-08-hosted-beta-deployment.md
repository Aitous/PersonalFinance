# Hosted Beta Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the existing invite-only PersonalFinance app with a hosted React frontend, always-on FastAPI API, Supabase Auth/Postgres, and the current owner’s data safely migrated.

**Architecture:** Use Render Static Site for the Vite frontend and a paid Render Web Service for the API, with the existing Supabase project as Auth provider and PostgreSQL database. Keep all database, encryption, Plaid, and model secrets in server-side service environment variables; expose only the Supabase URL/publishable key and API URL to the frontend. Complete Auth redirect/email configuration before inviting the owner, migrate the local owner data once, then reconnect Plaid.

**Tech Stack:** React 19, Vite, FastAPI, Uvicorn, SQLAlchemy, Supabase Auth/Postgres, Render Blueprint.

**Spec:** `README.md` hosted invite-only beta section and `docs/superpowers/specs/2026-11-02-multi-user-beta-design.md`.

## Global Constraints

- Do not expose `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `APP_ENCRYPTION_KEY`, Plaid credentials, or LLM provider keys to frontend build variables.
- Use the existing restricted `finance_app` database role with `NOBYPASSRLS`.
- Keep public Supabase signups disabled; verify HTTPS redirects and owner email delivery before the owner invite. Require custom SMTP with a verified domain before inviting non-team beta users.
- Do not run the owner migration against an owner that already has application rows.
- Store no bank or transaction data on Render's ephemeral filesystem; keep it in Supabase Postgres and encrypt Plaid tokens with the configured application key.
- Preserve all existing user work in the current dirty workspace; limit this plan’s initial implementation to new hosting config/docs files.
- Do not create a paid hosting service, send invites, migrate user data, or trigger Plaid pulls without verifying the target and expected charge/action first.

## Review Focus

- Missing or malformed server secrets must fail startup with names only and must never leak values in logs.
- Frontend build variables must not accidentally include server-only secrets.
- The API health endpoint must remain usable while protected data routes require authenticated identity.
- Auth email links must resolve to the production frontend origin after confirmation and sign-in.
- Owner migration must stop on a populated target and leave a restorable local SQLite backup.

---

### Task 1: Add reproducible Render service configuration

**Files:**
- Create: `render.yaml`
- Modify: none

**Interfaces:**
- Produces a Blueprint with a React static site rooted at `frontend` and a Python web service rooted at the repository root.
- The API starts with `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`, checks `/health`, and declares server secrets as dashboard-supplied (`sync: false`).
- The frontend build receives only `VITE_APP_MODE`, `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY`.

- [x] Add the Blueprint with the API on Render's free compute plan ($0 fixed compute), Virginia region, Python 3.11.11, static frontend, keyword-only search for the 512 MB memory limit, build commands, health check, and explicit environment variable names.
- [x] Review the YAML for valid Render Blueprint fields and verify no secret literal is committed.

### Task 2: Document provider setup and secret mapping

**Files:**
- Modify: `README.md` hosted invite-only beta section

**Interfaces:**
- Documents mapping the Render-generated frontend URL into API `FRONTEND_ORIGIN` and Supabase Auth Site URL/redirect allowlist.
- Documents the production API and frontend env vars, plus the order: deploy → configure HTTPS/Auth/email → invite owner → migrate → reconnect Plaid → verify.

- [x] Add Render-specific dashboard steps, build/start commands, and required env variable mapping without including secret values.
- [x] Clarify that Render’s free API sleeps and is unsuitable for a responsive invite beta; frontend static hosting can remain free. Explain keyword-only search and potential overage charges.
- [x] Review for contradictions with the existing hosted-beta instructions.

### Task 3: Configure hosting and production Auth

**Files:**
- External Render and Supabase settings; no repository files

**Interfaces:**
- Requires Render access, the GitHub repository permission, current Supabase keys, production LLM/Plaid credentials, and SMTP configuration.
- Produces HTTPS frontend/API origins and an Auth redirect allowlist matching the frontend origin.

- [ ] Create/link the Render services on the approved free API plan in Virginia and check whether the workspace's payment/overage settings could create charges.
- [ ] Add server-only secrets to the API service and public-safe values to frontend build settings.
- [ ] Configure Site URL and redirect allowlist. Test the built-in email service for the owner-only invite (team-member addresses only, 2 emails/hour); use custom SMTP if the owner email is not eligible or delivery fails.
- [ ] Document that custom SMTP with a verified sending domain is required before inviting non-team beta users.

### Task 4: Invite owner and migrate local data

**Files:**
- Existing migration command: `backend.scripts.migrate_local_owner`
- No new repository files

**Interfaces:**
- Requires the production API to initialize the empty schema, a successful owner invite, the invited owner’s Supabase UUID, and a verified backup of the local SQLite file.
- Produces that owner’s data in hosted PostgreSQL while excluding local Plaid tokens and report caches.

- [ ] Back up and record the source SQLite row counts/totals.
- [ ] Check whether the intended owner already exists among Supabase Auth users; reuse that UUID, or invite only if absent after email and redirects are verified.
- [ ] Run the documented one-time migration against the empty hosted owner and reconcile counts/totals.

### Task 5: Reconnect Plaid and verify tenant safety

**Files:**
- No repository files unless deployment reveals a concrete defect

**Interfaces:**
- Requires owner login, production Plaid credentials configured on the API, and a migrated owner account.
- Produces a verified hosted account with imported data, functioning sync, isolated tenant reads/writes, and enforced LLM limits.

- [ ] Reconnect the owner’s institutions and sync once; reconcile transaction counts and balances against the local source.
- [ ] Verify unauthenticated API access is rejected, the owner can access only their own rows, and configured LLM caps reject excess calls.
- [ ] Record deployment URLs and operational limitations; do not invite other beta users until these checks pass.
