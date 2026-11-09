# PersonalFinance

A personal finance dashboard with local development and an invite-only hosted mode. Import bank CSVs, connect Plaid, enrich transactions with AI, track subscriptions, and get spending insights.

![Dashboard](https://img.shields.io/badge/stack-FastAPI%20%2B%20React-7c6af7)

## Features

- **Import** — Upload CSVs from Chase, Discover, and Amex
- **AI Enrichment** — Extracts merchant names, cities, and merchant types using Gemini
- **Search** — Keyword and semantic (embedding-based) search across all transactions
- **Categories** — Pie chart breakdown with configurable date ranges
- **Insights** — Spending anomalies, duplicate charge detection, price increases, merchant breakdown, day-of-week patterns, year-over-year comparison
- **Subscriptions** — Auto-detected recurring charges, manual entry, usage-based detection for API services
- **Savings Tips** — AI-generated suggestions based on your actual spending
- **Export** — Download any filtered view as CSV

## Requirements

- Python 3.11+
- Node.js 18+
- A Gemini API key (Google AI Studio — [get one free](https://aistudio.google.com/app/apikey))
- Optionally an Anthropic API key for Claude-based savings tips

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Aitous/PersonalFinance.git
cd PersonalFinance
```

### 2. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 3. Frontend

```bash
cd frontend
npm install
cd ..
```

### 4. Configure your LLM API key

Start the backend once to initialize the database, then open Settings in the app and save your Gemini (or Anthropic) API key. Keys are stored in macOS Keychain and never written to disk.

Alternatively, set them directly via the API:

```bash
curl -X POST http://localhost:8000/settings/llm \
  -H "Content-Type: application/json" \
  -d '{"provider": "gemini", "api_key": "YOUR_KEY"}'
```

## Running

Open two terminals:

**Terminal 1 — Backend:**
```bash
source .venv/bin/activate
uvicorn backend.main:app --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Then open [http://localhost:5173](http://localhost:5173).

## Importing Transactions

1. Download CSVs from your bank's website
2. Go to **Overview** → drag and drop or use the file picker
3. Supported formats: Chase, Discover, Amex (the app auto-detects the bank from the filename)
4. Click **Enrich new transactions** to run AI extraction of merchant names, cities, and types
5. Click **Re-detect** on the Subscriptions page to refresh recurring charge detection

## Project Structure

```
backend/
  routes/          # FastAPI endpoints
  analysis/        # Insights, categorization, subscription detection, merchant normalization
  search/          # Embedding-based semantic search
  parsers/         # CSV parsers per bank
  llm/             # LLM provider abstraction (Claude / Gemini)
  db/              # SQLAlchemy models and session

frontend/
  src/
    pages/         # Overview, Transactions, Categories, Insights, Subscriptions, SavingsTips
    api/           # API client
    components/    # Shared chart components
```

## Data Privacy

- The SQLite database (`finance.db`) is excluded from git via `.gitignore`
- Your CSV files (`transactions/`) are excluded from git
- API keys are stored in macOS Keychain, never in config files
- Transaction descriptions are sent to the Gemini API for enrichment — no other data leaves your machine

## LLM Models Used

| Task | Model |
|------|-------|
| Transaction enrichment | `gemini-3.5-flash-lite` |
| AI insights and savings tips | `gemini-3.8-flash` |
| Embeddings (semantic search) | local `sentence-transformers` |
# Hosted invite-only beta

The hosted app uses Supabase Auth for sign-in and PostgreSQL for tenant data. Keep the API as the only database client; never put the Supabase service key, database password, Plaid secrets, model keys, or `APP_ENCRYPTION_KEY` in frontend build variables.

## Supabase project setup

1. Create a Supabase project and enable an **asymmetric JWT signing key** for Auth. The API verifies access tokens against the project JWKS endpoint and validates issuer, audience, expiry, and subject. Supabase recommends a standard JWT verification library and documents the JWKS endpoint [here](https://supabase.com/docs/guides/auth/jwts).
2. Disable public email signups in Auth settings. Invite pilot users from the Supabase dashboard; the app only provides email-link sign-in and asks Supabase not to create unknown users.
3. Create a dedicated PostgreSQL login for the API with `NOBYPASSRLS`, then grant it ownership/DDL access to the app schema. For example, as the project database administrator:

   ```sql
   create role finance_app login password '<generated-secret>' nosuperuser nobypassrls;
   grant connect on database postgres to finance_app;
   grant usage, create on schema public to finance_app;
   ```

   Set `DATABASE_URL` to this role, not Supabase's `postgres` superuser or `service_role`. On startup the API enables and forces PostgreSQL row-level security on every user-owned table. Supabase documents that `service_role` bypasses RLS, so it must stay out of the database connection and browser [source](https://supabase.com/docs/guides/database/postgres/row-level-security).
4. Add a server-side `SUPABASE_SERVICE_ROLE_KEY` for account deletion only. Supabase service keys bypass RLS and must never be exposed to users.
5. Set the API and frontend environment variables below. Configure Supabase's allowed redirect URL to the HTTPS frontend origin. Configure SMTP before inviting beta users so email links are delivered reliably.
6. Invite the owner account, find its Auth user UUID, take a backup of the local SQLite database, then run the one-time owner migration command below. Plaid Items and local Keychain tokens are deliberately not copied; reconnect banks from hosted Settings.

### API environment

```text
APP_ENV=production
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<server-only Supabase service key>
DATABASE_URL=postgresql+psycopg://finance_app:<password>@<host>:5432/postgres?sslmode=require
APP_ENCRYPTION_KEY=<long random secret held in the host secret manager>
FRONTEND_ORIGIN=https://<your-frontend-host>
LLM_PROVIDER=openai|gemini|claude
OPENAI_API_KEY=<if using openai>
GEMINI_API_KEY=<if using gemini>
ANTHROPIC_API_KEY=<if using claude>
LLM_MONTHLY_REQUEST_LIMIT=100
LLM_GLOBAL_DAILY_REQUEST_LIMIT=2000
PLAID_PRODUCTION_CLIENT_ID=<server-only Plaid client id>
PLAID_PRODUCTION_SECRET=<server-only Plaid production secret>
```

The app meters each individual provider call. The default user allowance is 100 calls per calendar month and the global circuit breaker is 2,000 calls per day; these are request caps, not dollar caps, because current provider adapters do not return token-cost data. Change the limits in host secrets before deployment if needed. AI use requires each account to accept the in-app data-use notice first.

Back up `APP_ENCRYPTION_KEY` with the database backups. Replacing it without re-encrypting stored Plaid tokens will make existing bank connections unusable.

### Frontend environment

```text
VITE_APP_MODE=hosted
VITE_API_BASE_URL=https://<your-api-host>
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<Supabase publishable/anon key>
```

The frontend uses an in-memory Supabase session store; a full browser refresh requires a fresh email sign-in link. Hosted CORS accepts only `FRONTEND_ORIGIN`.

### Move the current owner’s data

After the API has initialized the empty PostgreSQL schema, check whether the owner already exists in Supabase Auth. Reuse that user's UUID; invite the owner only if the account is absent. Then run:

```bash
DATABASE_URL='<restricted PostgreSQL URL>' .venv/bin/python -m backend.scripts.migrate_local_owner --owner-id '<Supabase Auth user UUID>'
```

The migration creates a timestamped SQLite backup, copies tenant-owned ledger/import/rule data, namespaces transaction IDs for the new owner, and omits disposable report caches and Plaid tokens. Reconcile transaction counts and totals before inviting anyone else. Do not run this against a populated target owner; it intentionally stops if that account already has rows.

## Current hosted-beta boundaries

- User data reads and writes are tenant-scoped in SQLAlchemy and PostgreSQL RLS. Hosted background jobs are only started from authenticated requests; startup does not run a global embedding scan.
- Plaid Items are owner-scoped and access tokens are encrypted with `APP_ENCRYPTION_KEY`. Plaid developer credentials are service-managed. Configure production Plaid credentials and reconnect the owner’s Items after migration.
- Plaid transaction updates are currently refreshed by the user with the Sync button. Verified webhooks and a durable cross-restart job worker are still needed for automatic refresh before a wider beta.
- Users can export their account data. They must disconnect Plaid Items before requesting deletion; deletion then removes tenant records and the Supabase Auth identity.
- Invite issuance remains an operator action in the Supabase dashboard. There is no public registration route.
- This is not yet a public beta release: configure a hosted HTTPS API/frontend, production email delivery, production Plaid credentials, backup/restore monitoring, and an operational review before sending invites beyond the owner.

## Render deployment

The repository includes a `render.yaml` Blueprint for a Virginia-region FastAPI service and a static Vite frontend. Both are configured on Render's free tiers; the frontend is served from Render's global CDN. The free API has 512 MB RAM and spins down after 15 minutes without traffic, so this is a preview setup rather than a responsive production beta. It pins Python to 3.11.11 to avoid an unsupported dependency/runtime combination and disables local sentence-transformer ranking to reduce memory use; keyword search remains available. The existing Supabase project remains the database, so do not create a second hosted database. See [Render's free-tier limits](https://render.com/docs/free) and [pricing](https://render.com/pricing) before provisioning.

To deploy:

1. In Render, create a Blueprint Instance from the connected `Aitous/PersonalFinance` GitHub repository and review the service plan and recurring charge before confirming.
2. Supply the `sync: false` values requested by the Blueprint. API-only values belong only on `personalfinance-api`: `SUPABASE_SERVICE_ROLE_KEY`, restricted-role `DATABASE_URL`, `APP_ENCRYPTION_KEY`, `OPENAI_API_KEY`, and the production Plaid credentials. `SUPABASE_URL` and `FRONTEND_ORIGIN` are also required by the API. Never paste a server secret into a `VITE_*` variable.
3. For the initial Blueprint prompt, the expected public URLs from the configured service names are `https://personalfinance-api.onrender.com` and `https://personalfinance-frontend.onrender.com`. Enter the frontend URL as API `FRONTEND_ORIGIN` and the API URL as frontend `VITE_API_BASE_URL`. After creation, verify the actual service URLs in Render and correct/redeploy if Render had to add a suffix because of a name conflict.
4. Set the remaining frontend build values on `personalfinance-frontend`: `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` to the Supabase project URL and publishable/anon key. These values are included in the browser bundle; only the publishable key belongs here.
5. After the static site is deployed, confirm the API's `FRONTEND_ORIGIN` matches its exact HTTPS origin and redeploy the API if needed. In Supabase Auth URL Configuration, set Site URL to that origin and add the origin as an allowed redirect URL. The app sends email sign-in links back to `window.location.origin`.
6. For the owner-only setup, test Supabase's built-in email delivery to the project owner first. It can send only to addresses on the Supabase organization team and is limited to 2 emails/hour; configure custom SMTP if the owner address is not eligible or delivery fails. Before inviting any other beta users, configure custom SMTP and verify a sending domain. Keep public signups disabled.
7. Continue with **Move the current owner’s data** above only after `/health` succeeds and the API has initialized the empty owner schema. Then reconnect Plaid from the hosted app and reconcile the migrated ledger before inviting anyone else.

The Render API free service sleeps after 15 idle minutes and can take about a minute to wake. It also uses ephemeral storage, so all persistent data must remain in Supabase. Render may bill for outbound-bandwidth or build-pipeline overages if a payment method is on file; check workspace billing and set a zero pipeline spend limit before provisioning if you want to keep this preview at $0. Without a payment method, Render suspends free services when outbound bandwidth is exhausted. Render's `sync: false` variables are prompted during initial Blueprint creation; add any later secret variables manually in the service dashboard.
