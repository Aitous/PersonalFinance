# Recent Category Comparison Implementation Plan

> **For agentic workers:** Native implementation in the current session.

**Goal:** Make category change explanations focus on the selected month versus the three immediately preceding calendar months, while retaining an all-history average as reference.

**Architecture:** Add a deterministic recent-window aggregate to the monthly report, and provide month-by-month merchant and transaction evidence to one cached LLM explanation per comparison. Keep the existing category table as the sole place for amounts, explanations, and expandable evidence.

**Tech Stack:** Python, FastAPI, SQLAlchemy, SQLite, React, TypeScript, Recharts.

**Spec:** Sol 6.1 read-only review and user approval in this conversation.

## Global Constraints

- Use exactly the three calendar months before the selected month; do not silently substitute older months.
- Compute the recent mean only if each window month has observed transaction activity; this is not proof of complete statement coverage.
- Do not infer complete statement coverage from observed transactions.
- Preserve the all-history average as a reference, not the primary explanation baseline.
- Keep explanations grounded in deterministic totals and transaction evidence; cache by month, comparison, data revision, and prompt version.
- Do not add or run tests unless the user requests them; use build, syntax, and endpoint checks.

## Review Focus

- A missing month must not be treated as zero; the three-month baseline is unavailable unless each month has observed transactions.
- A single large prior transaction must remain visible with its month and merchant so the explanation can identify it as an outlier.
- Merchant contribution changes must reconcile with the category change against the three-month mean.
- Historical reference amounts may include transactions after a selected historical month and must be labeled as all-history context.
- Old cached explanations must not be served for the new baseline or prompt.

---

### Task 1: Calculate recent and all-history baselines

**Files:**
- Modify: `backend/analysis/monthly_report.py`

**Interfaces:**
- Extend category report rows with `recent_three_month_average`, and report metadata with the three preceding calendar month keys and their observed activity status.
- Preserve `all_data_monthly_average` as a reference metric.

- [ ] Calculate the three immediately preceding calendar months with year rollover.
- [ ] Aggregate gross purchase totals by category for each month; mark a month observed only when at least one spending transaction is present.
- [ ] Return a recent mean only when all three months have observed transaction activity; do not extend the window or infer statement completeness.
- [ ] Keep all-history average separate and document its reference-only meaning in returned metadata.

### Task 2: Build and cache month-specific explanation evidence

**Files:**
- Modify: `backend/analysis/monthly_category_explanations.py`
- Modify: `backend/routes/analysis.py`

**Interfaces:**
- Add comparison value `recent3`; retain `prior` as the one-month option.
- Evidence includes baseline amount per month, merchant totals and activity counts per month, plus largest current and baseline transactions with dates.
- Bump explanation prompt version so old `average` explanations cannot be reused.

- [ ] Compute merchant-level contributions against the exact three-month mean.
- [ ] Include month-by-month category values and baseline outlier transactions in the prompt/evidence payload.
- [ ] Require the LLM to identify a large one-month transaction only when supported, and describe missing activity as unobserved rather than stopped spending.
- [ ] Cache by selected month, comparison, data revision, and prompt version.

### Task 3: Update the report chart and existing category table

**Files:**
- Modify: `frontend/src/api/reports.ts`
- Modify: `frontend/src/pages/Reports.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Default chart comparison becomes `recent3`; preserve prior-month comparison.
- The existing table adds a recent-three-month average column and renames the lifetime value as an all-history reference.
- Keep explanations and expandable merchant/transaction evidence in the same table row.

- [ ] Update explanation fetch/cache keys to use `recent3` or `prior`.
- [ ] Display the three baseline months and make incomplete observed-month coverage explicit.
- [ ] Keep the all-history average visible as a quieter reference; explain that it may include later dates for older report months.
- [ ] Fix the largest-decrease callout to select the most negative delta.

### Task 4: Verify implementation

**Files:**
- No additional files.

- [ ] Run the frontend production build.
- [ ] Run Python syntax compilation for modified backend files and inspect `git diff --check`.
- [ ] Check report and explanation endpoints, including the cache-hit response, without adding or running a test suite.
