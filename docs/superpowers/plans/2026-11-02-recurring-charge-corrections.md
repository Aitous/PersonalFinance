# Recurring Charge Corrections Implementation Plan

> **For agentic workers:** Implement the tasks below in order. Preserve unrelated workspace changes; do not commit.

**Goal:** Make recurring-charge identity, lifecycle state, and cost reporting consistent across detection, the API, the recurring page, and Savings Tips.

**Architecture:** Use account/source plus normalized transaction descriptor as the detector identity, while migrating existing detected rows by overlapping transaction evidence. Reconcile whenever detector inputs change, compute effective activity from the latest observed charge, and expose one monthly-cost profile for all downstream consumers while preserving manually entered amounts.

**Tech Stack:** FastAPI, SQLAlchemy, Python, React, TypeScript.

## Global Constraints

- Keep user-created subscription amounts authoritative.
- Keep dismissed detections hidden and dismissed across re-detection.
- Preserve existing transaction IDs and transaction rows.
- Do not run or add tests unless the user asks.
- Do not commit or revert unrelated workspace changes.

## Review Focus

- Old detected IDs must migrate without losing active overrides or producing duplicate rows.
- Unassigned rows from different sources must not be combined into one series.
- Deletion and enrichment must refresh links and `is_subscription` flags.
- Fixed, variable, and annual totals must use consistent billing-period sums.
- Manual subscriptions must not claim an unobserved payment date or duplicate detected rows.

---

### Task 1: Stable identity and subscription reconciliation

**Files:** `backend/analysis/subscription_detector.py`, `backend/analysis/recurring.py`, `backend/routes/transactions.py`

- [x] Derive detected IDs from the account/source and normalized bank descriptor, not the enriched display label.
- [x] Match old detected rows by supporting-transaction overlap when migrating to stable IDs.
- [x] Match one manual/legacy row to exact normalized service names across account-assigned evidence, aggregate links, and avoid duplicate detected rows.
- [x] Hide dismissed rows in the list API and reject attempts to reactivate dismissed rows.
- [x] Prune deleted evidence and recompute transaction recurring flags during reconciliation.
- [x] Scope transactions with no account ID by source, and avoid rejecting a whole series because of one in-person category/type outlier.
- [x] Require regular timing for one-charge-per-month patterns before classifying monthly.

### Task 2: Consistent amounts and manual charge semantics

**Files:** `backend/analysis/recurring.py`, `backend/routes/transactions.py`, `backend/routes/analysis.py`, `backend/analysis/savings_advisor.py`, `frontend/src/api/client.ts`, `frontend/src/pages/Subscriptions.tsx`

- [x] Add latest billing-period total to the shared amount profile.
- [x] Use period totals and monthly equivalents for detected entries; preserve manual/legacy amounts in the API and UI.
- [x] Pass the same profile's monthly equivalent to Savings Tips.
- [x] Store no last-charged date for manually added entries until a transaction is observed.

### Task 3: Keep derived recurring state current

**Files:** `backend/routes/transactions.py`, `backend/jobs/enrichment.py`, `backend/analysis/recurring.py`

- [x] Reconcile after transaction category/merchant edits, deletion, and enrichment completion.
- [x] Compute auto-detected active status from the latest charge on reads so it ages correctly without a manual re-detection.

### Task 4: Verification

- [x] Compile the changed Python modules.
- [x] Build the frontend and run `git diff --check`.
- [ ] Do not run test suites.
