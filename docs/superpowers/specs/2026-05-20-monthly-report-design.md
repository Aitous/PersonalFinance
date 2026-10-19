# Monthly Report — Design Spec

## Goal

Add a dedicated Reports page that shows a full summary of any selected month: AI narrative, spending stats, category breakdown vs prior month, top merchants, and upcoming subscription renewals.

## Architecture

A new `GET /analysis/monthly-report` endpoint assembles all report data in one call. The AI narrative is generated on demand via the existing LLM abstraction and cached in a new `monthly_report_cache` table so it doesn't re-run on every page load. The frontend is a new `Reports.tsx` page added to the sidebar nav.

## Tech Stack

FastAPI, SQLAlchemy/SQLite, React 18 TypeScript, Recharts (existing), existing LLM abstraction (`backend/llm/`).

---

## Backend

### New endpoint

`GET /analysis/monthly-report?year=YYYY&month=M`

Response shape:
```json
{
  "year": 2026,
  "month": 4,
  "total": 3240.00,
  "prev_total": 3420.00,
  "tx_count": 84,
  "categories": [
    { "name": "dining", "current": 820.00, "prior": 732.00 }
  ],
  "merchants": [
    { "name": "Delta Airlines", "total": 410.00 }
  ],
  "subscriptions_due": [
    { "description": "Netflix", "amount": 15.99, "next_date": "2026-05-03" }
  ],
  "narrative": "You spent $3,240 in April..."
}
```

- `categories` sorted descending by `current`; up to all categories with spend > 0 in either month
- `merchants` top 8 by spend in the selected month
- `subscriptions_due` — active subscriptions whose estimated next charge falls within 30 days of the report month's last day (for last complete month) or today (for current month)
- `narrative` is `null` if not yet generated; frontend shows a "Generate summary" button

### Narrative generation

- Prompt fed to the existing LLM provider (Gemini): total, prev_total, top 3 categories with % change, count of subscriptions due. Instructs the model to write 2–4 sentences in plain English.
- Cached in `monthly_report_cache(year INT, month INT, narrative TEXT, created_at DATETIME)`, unique on `(year, month)`
- Separate `POST /analysis/monthly-report/narrative?year=YYYY&month=M` endpoint triggers generation and writes to cache; returns `{ "narrative": "..." }`

### Helper function

`backend/analysis/monthly_report.py` — `get_monthly_report(year, month) -> dict`

Queries transactions for the selected month and the prior month, computes all fields except narrative (pulled from cache if present).

---

## Frontend

### New page: `frontend/src/pages/Reports.tsx`

Added to sidebar nav between Insights and Subscriptions.

**Month picker** in the page header: left/right arrows step one month; defaults to the last complete month (current month − 1). Displays as `◀ April 2026 ▶`.

**Layout (top to bottom):**

1. **AI Narrative card** — displays cached narrative if present; otherwise shows a "Generate summary" button that calls `POST /analysis/monthly-report/narrative` and updates state on success. Shows a spinner while generating.

2. **Stats row** — 3 stat cards:
   - Total spent (formatted `$X,XXX`)
   - vs last month: `+X.X%` (red) or `−X.X%` (green) plus absolute delta
   - Transaction count

3. **Category breakdown** — Recharts `BarChart` with grouped bars (this month = purple `#7c6af7`, prior month = light purple `#c4b5fd`). One pair per category, sorted by current month descending. Clicking a bar pair navigates to `/transactions?category=NAME&dateFrom=YYYY-MM-01&dateTo=YYYY-MM-DD`.

4. **Top merchants** — Ranked list (1–8) with merchant name and amount. Clicking a row navigates to `/transactions?search=NAME&dateFrom=...&dateTo=...`.

5. **Subscriptions due** — List of subscriptions with estimated renewal date within 30 days. Each row shows name, amount, and date. Links to `/subscriptions`.

### API client additions (`frontend/src/api/`)

- `getMonthlyReport(year, month)` — `GET /analysis/monthly-report?year=Y&month=M`
- `generateNarrative(year, month)` — `POST /analysis/monthly-report/narrative?year=Y&month=M`

---

## Data Model

New SQLite table (created via SQLAlchemy, added to `backend/db/models.py`):

```python
class MonthlyReportCache(Base):
    __tablename__ = "monthly_report_cache"
    year: int (primary key, part of composite)
    month: int (primary key, part of composite)
    narrative: str
    created_at: datetime
```

No migration tooling in this project — table created via `Base.metadata.create_all` on startup.

---

## Subscription "due date" estimation

For a monthly subscription: `next_date = last_charged + 30 days`.
For an annual subscription: `next_date = last_charged + 365 days`.
A subscription is "due" if `next_date` falls within 30 days after the report month's end date.

---

## Out of scope

- Email/push notifications
- PDF export of the report
- Budget targets or goal tracking
- Income tracking
