# App Reliability Implementation Plan

> Execute through Luna implementation subagents; the primary agent reviews integration and verifies results. The user approved implementing the October 18 audit and explicitly requested Luna.

**Goal:** Address the findings in `docs/reviews/2026-10-18-app-audit.md` before building a conversational agent.
**Architecture:** Retain FastAPI, SQLAlchemy/SQLite and React. Introduce durable import/account/job provenance with additive migrations; use shared transaction semantics and revision-aware derived data. Preserve existing IDs, manual decisions and financial rows.
**Spec:** `docs/reviews/2026-10-18-app-audit.md` is the accepted review/scope.

## Global constraints
- Preserve all existing working-tree changes. No rewriting financial history or assigning unknown legacy cards by guesswork.
- Back up SQLite before running migrations. Migrations additive and idempotent; retain existing public IDs and float amount response for compatibility, add integer minor units and currency for new writes.
- No live LLM or bank calls during tests. Synthetic and temporary databases only. Never print credentials or private transactions in reports.
- No new agent/chat implementation, remote hosting, vector database, or broad visual rewrite.
- No commits, pushes, destructive cleanup, or sub-subagents. Workers own explicit files; coordinate shared interfaces through the parent.
- Baseline: 92 tests pass, 4 fail; full TypeScript build fails in Insights/Reports. End state must fix those failures and run full verification.

## Task 1 — Account-aware, validated ingestion (backend owner: Luna ingestion)
Files: backend/db/models.py, database.py, new migration/ingestion helpers, parsers/csv_parser.py, ofx/client.py, sync_service.py, import_csv.py upload/folder endpoints, ingestion tests.
- [ ] Add Account, ImportBatch, ImportedRow provenance and optional account/identity fields on transactions; schema migrations preserve 1,779 existing rows/IDs.
- [ ] Validate headers/rows; report input/parsed/rejected/duplicate/new counts and reasons; reject wholly invalid files. Preview before import.
- [ ] Normalize OFX and CSV kinds/signs through one function; preserve original amount, account and bank FITID. Keep refund/payment semantics distinct.
- [ ] Account-scoped identities, repeated-row occurrence preservation and batch overlap reconciliation; reimports idempotent, same purchase across cards retained. Ambiguous legacy matches recorded, not discarded by guesswork.
- [ ] Import persistently without depending on LLM availability. Provide import list/status with coverage/checksum/filename. Existing upload API remains compatible with optional account_id. Expose GET /accounts and POST /accounts (bank,name,last4 optional) and POST /import/preview (multipart bank/account_id/file).
- [ ] Add transaction manual_category boolean, Subscription origin/dismissed fields, durable EnrichmentJob model and data revision helpers for task 3. Coordinate exact interfaces before task 3.
- [ ] Regression tests cover wrong bank/malformed lines, legitimate identical purchases, cross-account purchases, overlap, CSV+OFX normalization, legacy rows and idempotent migration.

## Task 2 — Frontend correctness and useful quality UI (owner: Luna frontend)
Files: frontend/** only. Own no backend or shared docs.
- [ ] Fix full npm build, including Recharts handlers/types, without disabling TS checks.
- [ ] One typed URL filter contract supporting existing q/merchant/month/ids plus category, source, date_from/date_to and legacy report aliases. Read/write filters, refresh/back-forward stable, report drilldowns preserve exact selected period/merchant.
- [ ] Add import preview/account selection and import summary using task 1 API; rejected lines visible; no guessed legacy account assignments.
- [ ] Show account/source freshness and unknown-city caveats using GET /analysis/data-quality: {sources:[{source,transaction_count,first_date,last_date}],total_transactions,missing_city,missing_merchant,unassigned_account,coverage_note}. No completeness claims from latest dates.
- [ ] Preserve existing style, fix Reports heading/content contrast, add responsive layout/keyboard sort controls and consistent error/retry/loading state in changed flows.
- [ ] Make gross/refund/net wording clear; typed summary return extensions stay backwards compatible.
- [ ] Verify full build and own lint/URL filter unit tests if an existing suitable runner exists; don't install heavy test frameworks.

## Task 3 — Recurring state and durable enrichment (owner: Luna reliability, starts after task 1 schema)
Files: backend/analysis/subscription_detector.py, merchant_normalizer.py, categorizer.py; routes/import_csv.py jobs section, routes/transactions.py subscriptions/category mutation; durable jobs helper; related tests.
- [ ] Reconcile auto subscriptions instead of deleting all; manual additions, active choices/dismissals preserved. Link supporting transactions and maintain recurring filters. Annual detection can use two observations; monthly stale activity reconciled.
- [ ] Manual category edits recorded and protected by enrichment/reclassification. Preserve valid fields when a retry falls back; explicit per-row success/failure, unknown is not a failure.
- [ ] Persist job state, per-row attempts/model/input hash, resume interrupted work, avoid duplicate pending overwrites; no full LLM work inside async upload.
- [ ] Reversible merchant aliases/proposals instead of blind in-place fuzzy merging; preserve raw extraction and allow explicit corrections.
- [ ] Invalidate derived data via shared revision helper after mutations; don't rewrite unrelated transactions or invoke live paid jobs.
- [ ] Tests cover manual subscription surviving redetect, dismissals, flags, annual two-charge case, failed retry preserving valid values/manual category, recovery from interrupted job.

## Task 4 — Analytics, indexing, baseline and integration (primary, with Luna follow-up as needed)
Files: backend/routes/analysis.py, analysis/insights.py, monthly_report.py, search/embedder.py, routes/search.py, main.py, setup/dependencies/CI/docs and integration tests.
- [ ] Shared gross purchases/refunds/net definitions and covered calendar-period average semantics; partial/unknown months explicit.
- [ ] Narrative cache keyed by data revision (including edits/imports/subscriptions); enriched embedding text includes merchant/city/type and input hash invalidation/rebuild.
- [ ] GET /analysis/data-quality returns the frontend contract above and coverage caveat; no guessing complete account periods.
- [ ] Correct backend direct dependencies/setup commands and stale sign tests, add lightweight CI. Preserve model choices requested earlier.
- [ ] Run full pytest, npm build, focused browser verification, migration/reimport against isolated database copy; review diffs for regressions. Start app after verified migration backup.

## Review focus
- Legacy unknown accounts cannot be confidently matched to a new card solely by amount/date.
- Legitimate identical purchases must not be collapsed, and overlap must remain idempotent.
- Manual choices survive all automatic jobs and repeated imports.
- Stale jobs/caches/indexes must never be presented as current results.
- Source freshness and missing city information remain visible in reports and future tool results.
