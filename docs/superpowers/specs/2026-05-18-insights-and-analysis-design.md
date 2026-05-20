# Insights & Analysis Implementation Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dedicated Insights page to the sidebar with four sections: smart alerts, full merchant breakdown, day-of-week spending patterns, and year-over-year comparison.

**Architecture:** New `GET /analysis/insights` endpoint returns all four data payloads in a single call. New `Insights.tsx` page renders them. Alerts recalculate fresh on every page load — no persistence or dismissal needed.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, React 18 + TypeScript, Recharts

---

## Data Model

No schema changes required. All analysis runs over the existing `transactions` table. Payment transactions are excluded via the existing `_is_payment()` helper in `backend/routes/analysis.py`.

---

## Backend: `/analysis/insights`

Single endpoint returns a JSON object with four keys: `alerts`, `merchants`, `day_of_week`, `year_over_year`.

### Alerts

Three alert types, each returns a list (empty if no issues detected).

**1. Spending anomalies** (`alerts.anomalies`)
- For each category, compute the rolling 3-month average spend (excluding the current month).
- If current month spend > 2× the average, emit an anomaly alert.
- Only emit if current month has at least 3 transactions in that category (avoids noise on sparse categories).
- Fields: `category`, `current_amount`, `avg_amount`, `ratio`, `tx_count`

**2. Duplicate charges** (`alerts.duplicates`)
- Group transactions by normalized merchant name (strip trailing numbers/IDs, uppercase).
- Within each merchant group, flag any two transactions with the same amount within 7 days of each other.
- Exclude recurring/subscription charges (amount stable across 3+ months).
- Fields: `merchant`, `amount`, `dates` (list of ISO date strings), `sources`

**3. Price increases on recurring charges** (`alerts.price_increases`)
- Reuse the subscription detector's normalized merchant grouping.
- For each recurring merchant with 6+ charges, compare the last 2 charges to the prior median.
- If the last charge is >5% higher than the median of all prior charges, emit a price increase alert.
- Fields: `merchant`, `old_amount`, `new_amount`, `delta`, `first_new_date`

### Merchant Breakdown

`GET /analysis/insights` also accepts query params `merchant_days: int = 90` (7–730) for the merchant section time window.

- Aggregate all non-payment transactions in the window by normalized merchant name.
- Normalized merchant: strip trailing transaction IDs, location codes, and sequences (same logic as subscription detector's `_normalize()`).
- Return all merchants sorted by total descending.
- Fields per merchant: `name`, `total`, `tx_count`, `category`, `last_date`
- No top-N limit — return all (frontend handles search/scroll).

### Day of Week

- For each day (Mon=0 … Sun=6), sum all non-payment transaction amounts across all time.
- Return 7 entries: `day` (0–6), `day_name` ("Monday"…), `total`, `tx_count`, `avg_per_tx`
- Also return `weekend_pct`: percentage of total spend on Sat+Sun.

### Year-over-Year

- Extract all calendar years present in the transactions table.
- For each year: total spend, spend per category.
- Compute "on pace" for the current year: `(ytd_spend / days_elapsed) * 365`.
- If fewer than 2 calendar years have data, return `insufficient_data: true` and the frontend hides the section gracefully.
- Fields: `years` (list of `{year, total, categories: {category: amount}}`), `on_pace`, `on_pace_pct_change`, `insufficient_data`

---

## Frontend: `Insights.tsx`

New page at `/insights`. Added to sidebar between "Categories" and "Recurring".

### Layout (top to bottom)

1. **Alerts section** — renders only if at least one alert exists across all three types. Each alert type renders as a colored card (yellow=anomaly, red=duplicate, purple=price increase). If no alerts: show a green "All clear" banner.

2. **Merchant Breakdown section** — search input + time window selector (Last 90 days / 6 months / All time). Full scrollable table with columns: Merchant, Category, Txns, Total, bar (relative width). Merchant name click navigates to `/transactions` with a search query pre-filled.

3. **Day of Week section** — bar chart (Recharts `BarChart`) showing total spend per day. Weekend bars highlighted in amber. Summary sentence below: "Weekends (Sat–Sun) account for X% of your spending."

4. **Year-over-Year section** — hidden if `insufficient_data: true`. Three summary cards (prior year total, current YTD, on-pace projection with % change). Below: grouped bar chart comparing spend per category across years (last 2 years only to keep it readable).

### Data fetching

- Single `getInsights(merchantDays)` API call on mount and when `merchantDays` changes.
- `merchantDays` state driven by the time window selector (default 90).
- Loading and error states handled with inline messages (no spinner component needed).

---

## API Client

Add to `frontend/src/api/client.ts`:

```ts
export const getInsights = (merchantDays = 90) =>
  api.get("/analysis/insights", { params: { merchant_days: merchantDays } }).then(r => r.data);
```

---

## Sidebar

Add "Insights" link in `frontend/src/components/Sidebar.tsx` between "Categories" and "Recurring".

---

## Files to Create/Modify

- **Create:** `backend/analysis/insights.py` — all four analysis functions
- **Modify:** `backend/routes/analysis.py` — add `GET /analysis/insights` route
- **Create:** `frontend/src/pages/Insights.tsx` — the full page
- **Modify:** `frontend/src/api/client.ts` — add `getInsights`
- **Modify:** `frontend/src/components/Sidebar.tsx` — add nav link
- **Modify:** `frontend/src/App.tsx` — add route `/insights`
