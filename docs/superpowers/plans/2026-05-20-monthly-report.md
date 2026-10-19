# Monthly Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Reports page that shows a full monthly summary: AI narrative, spending stats, category breakdown vs prior month, top merchants, and upcoming subscription renewals.

**Architecture:** A new `get_monthly_report(year, month)` function in `backend/analysis/monthly_report.py` assembles all data from the SQLite DB. A `MonthlyReportCache` table stores generated AI narratives keyed on `(year, month)`. Two new FastAPI endpoints (`GET /analysis/monthly-report` and `POST /analysis/monthly-report/narrative`) are registered in the existing `analysis.py` router. A new `Reports.tsx` page is added to the React frontend with a month picker, narrative card, stats row, grouped bar chart, top merchants list, and subscriptions-due section.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, Python 3.11, React 18 TypeScript, Recharts (already installed), existing `backend/llm/` abstraction.

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `backend/db/models.py` | Modify | Add `MonthlyReportCache` model |
| `backend/analysis/monthly_report.py` | Create | `get_monthly_report()` pure function |
| `backend/routes/analysis.py` | Modify | Add two new endpoints |
| `frontend/src/api/reports.ts` | Create | API client functions |
| `frontend/src/pages/Reports.tsx` | Create | Full reports page |
| `frontend/src/App.tsx` | Modify | Add route + nav link |
| `tests/analysis/test_monthly_report.py` | Create | Unit tests for `get_monthly_report()` |

---

### Task 1: Add `MonthlyReportCache` model

**Files:**
- Modify: `backend/db/models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/db/test_models.py  (add to existing file)
def test_monthly_report_cache_table_exists():
    from backend.db.database import engine
    from sqlalchemy import inspect
    inspector = inspect(engine)
    assert "monthly_report_cache" in inspector.get_table_names()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /path/to/PersonalFinance && source .venv/bin/activate
pytest tests/db/test_models.py::test_monthly_report_cache_table_exists -v
```
Expected: FAIL with `AssertionError` (table does not exist yet)

- [ ] **Step 3: Add the model to `backend/db/models.py`**

Add this class at the bottom of the file (after the `Sync` class):

```python
class MonthlyReportCache(Base):
    __tablename__ = "monthly_report_cache"

    year = Column(Integer, primary_key=True)
    month = Column(Integer, primary_key=True)
    narrative = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
```

The `datetime` and `timezone` imports are already at the top of the file. `Text`, `Integer`, `DateTime` are already imported from `sqlalchemy`.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/db/test_models.py::test_monthly_report_cache_table_exists -v
```
Expected: PASS (SQLAlchemy creates the table via `Base.metadata.create_all` which is called on startup — for tests, call it manually or restart the server once)

Note: The table is created automatically by `init_db()` on server startup via `Base.metadata.create_all(engine)` in `backend/db/database.py`. For the test to pass without starting the server, call `init_db()` in the test:

```python
def test_monthly_report_cache_table_exists():
    from backend.db.database import engine, init_db
    from sqlalchemy import inspect
    init_db()
    inspector = inspect(engine)
    assert "monthly_report_cache" in inspector.get_table_names()
```

- [ ] **Step 5: Commit**

```bash
git add backend/db/models.py tests/db/test_models.py
git commit -m "feat: add MonthlyReportCache model"
```

---

### Task 2: Implement `get_monthly_report()` — core data function

**Files:**
- Create: `backend/analysis/monthly_report.py`
- Create: `tests/analysis/test_monthly_report.py`

- [ ] **Step 1: Write failing tests**

Create `tests/analysis/test_monthly_report.py`:

```python
import pytest
from datetime import date
from unittest.mock import MagicMock


def _tx(amount, category, year, month, day=1, description="SHOP", merchant_name=None):
    tx = MagicMock()
    tx.amount = amount
    tx.category = category
    tx.date = date(year, month, day)
    tx.description = description
    tx.merchant_name = merchant_name
    return tx


def test_total_and_tx_count():
    from backend.analysis.monthly_report import get_monthly_report_data
    txs = [
        _tx(100.0, "dining", 2026, 4),
        _tx(200.0, "groceries", 2026, 4),
        _tx(50.0, "dining", 2026, 3),  # prior month
    ]
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert result["total"] == 300.0
    assert result["tx_count"] == 2
    assert result["prev_total"] == 50.0


def test_categories_sorted_by_current_descending():
    from backend.analysis.monthly_report import get_monthly_report_data
    txs = [
        _tx(50.0, "dining", 2026, 4),
        _tx(200.0, "groceries", 2026, 4),
        _tx(40.0, "groceries", 2026, 3),
    ]
    result = get_monthly_report_data(txs, year=2026, month=4)
    cats = result["categories"]
    assert cats[0]["name"] == "groceries"
    assert cats[0]["current"] == 200.0
    assert cats[0]["prior"] == 40.0
    assert cats[1]["name"] == "dining"
    assert cats[1]["current"] == 50.0
    assert cats[1]["prior"] == 0.0


def test_top_merchants_limited_to_8():
    from backend.analysis.monthly_report import get_monthly_report_data
    txs = [_tx(float(i), f"cat{i}", 2026, 4, description=f"MERCHANT{i}") for i in range(1, 12)]
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert len(result["merchants"]) == 8
    # First merchant should be the one with the highest amount
    assert result["merchants"][0]["total"] == 11.0


def test_empty_month_returns_zeros():
    from backend.analysis.monthly_report import get_monthly_report_data
    txs = [_tx(100.0, "dining", 2026, 3)]  # only prior month has data
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert result["total"] == 0.0
    assert result["tx_count"] == 0
    assert result["categories"] == []
    assert result["merchants"] == []


def test_merchants_uses_merchant_name_when_available():
    from backend.analysis.monthly_report import get_monthly_report_data
    txs = [
        _tx(50.0, "dining", 2026, 4, description="SQ *CHIPOTLE 1234", merchant_name="Chipotle"),
        _tx(30.0, "dining", 2026, 4, description="SQ *CHIPOTLE 5678", merchant_name="Chipotle"),
    ]
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert result["merchants"][0]["name"] == "Chipotle"
    assert result["merchants"][0]["total"] == 80.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/analysis/test_monthly_report.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.analysis.monthly_report'`

- [ ] **Step 3: Create `backend/analysis/monthly_report.py`**

```python
from collections import defaultdict
from datetime import date
from typing import List
from backend.db.models import Transaction


def get_monthly_report_data(txs: List[Transaction], year: int, month: int) -> dict:
    """
    Pure function — computes all report fields except the AI narrative.
    Accepts a pre-filtered list of spending transactions (no payments, amount > 0).
    """
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    current_txs = [t for t in txs if t.date.year == year and t.date.month == month]
    prior_txs = [t for t in txs if t.date.year == prev_year and t.date.month == prev_month]

    total = round(sum(t.amount for t in current_txs), 2)
    prev_total = round(sum(t.amount for t in prior_txs), 2)
    tx_count = len(current_txs)

    # Categories: include any category present in either month
    current_by_cat: dict = defaultdict(float)
    for t in current_txs:
        current_by_cat[t.category or "other"] += t.amount

    prior_by_cat: dict = defaultdict(float)
    for t in prior_txs:
        prior_by_cat[t.category or "other"] += t.amount

    all_cats = set(current_by_cat) | set(prior_by_cat)
    categories = sorted(
        [
            {
                "name": cat,
                "current": round(current_by_cat[cat], 2),
                "prior": round(prior_by_cat[cat], 2),
            }
            for cat in all_cats
        ],
        key=lambda x: -x["current"],
    )

    # Top 8 merchants by spend in current month
    merchant_totals: dict = defaultdict(float)
    for t in current_txs:
        name = t.merchant_name if t.merchant_name else (t.description or "Unknown").upper().strip()
        merchant_totals[name] += t.amount

    merchants = sorted(
        [{"name": k, "total": round(v, 2)} for k, v in merchant_totals.items()],
        key=lambda x: -x["total"],
    )[:8]

    return {
        "year": year,
        "month": month,
        "total": total,
        "prev_total": prev_total,
        "tx_count": tx_count,
        "categories": categories,
        "merchants": merchants,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/analysis/test_monthly_report.py -v
```
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/analysis/monthly_report.py tests/analysis/test_monthly_report.py
git commit -m "feat: add get_monthly_report_data() core function"
```

---

### Task 3: Add `subscriptions_due` to the report data

**Files:**
- Modify: `backend/analysis/monthly_report.py`
- Modify: `tests/analysis/test_monthly_report.py`

- [ ] **Step 1: Write failing test**

Add to `tests/analysis/test_monthly_report.py`:

```python
def test_subscriptions_due_within_30_days():
    from backend.analysis.monthly_report import get_subscriptions_due
    from datetime import date, timedelta

    today = date(2026, 4, 30)  # last day of report month

    monthly_sub = MagicMock()
    monthly_sub.description = "Netflix"
    monthly_sub.amount = 15.99
    monthly_sub.frequency = "monthly"
    monthly_sub.last_charged = date(2026, 4, 3)   # next = May 3 — within 30 days
    monthly_sub.active = True

    annual_sub = MagicMock()
    annual_sub.description = "Adobe CC"
    annual_sub.amount = 599.0
    annual_sub.frequency = "annual"
    annual_sub.last_charged = date(2025, 5, 10)   # next = 2026-05-10 — within 30 days
    annual_sub.active = True

    far_sub = MagicMock()
    far_sub.description = "AWS"
    far_sub.amount = 9.99
    far_sub.frequency = "monthly"
    far_sub.last_charged = date(2026, 3, 1)        # next = Mar 31 — already past
    far_sub.active = True

    result = get_subscriptions_due([monthly_sub, annual_sub, far_sub], report_month_end=today)
    names = [r["description"] for r in result]
    assert "Netflix" in names
    assert "Adobe CC" in names
    assert "AWS" not in names


def test_inactive_subscriptions_excluded():
    from backend.analysis.monthly_report import get_subscriptions_due
    from datetime import date

    sub = MagicMock()
    sub.description = "Old Service"
    sub.amount = 9.99
    sub.frequency = "monthly"
    sub.last_charged = date(2026, 4, 1)
    sub.active = False

    result = get_subscriptions_due([sub], report_month_end=date(2026, 4, 30))
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/analysis/test_monthly_report.py::test_subscriptions_due_within_30_days tests/analysis/test_monthly_report.py::test_inactive_subscriptions_excluded -v
```
Expected: FAIL with `ImportError: cannot import name 'get_subscriptions_due'`

- [ ] **Step 3: Add `get_subscriptions_due()` to `backend/analysis/monthly_report.py`**

Add this function at the bottom of the file:

```python
from datetime import timedelta
from typing import List as _List
from backend.db.models import Subscription


def get_subscriptions_due(subs: _List[Subscription], report_month_end: date) -> list:
    """
    Returns subscriptions whose estimated next charge falls within 30 days after report_month_end.
    """
    window_start = report_month_end
    window_end = report_month_end + timedelta(days=30)

    due = []
    for sub in subs:
        if not sub.active or sub.last_charged is None:
            continue
        days = 30 if sub.frequency == "monthly" else 365
        next_date = sub.last_charged + timedelta(days=days)
        if window_start < next_date <= window_end:
            due.append({
                "description": sub.description,
                "amount": sub.amount,
                "next_date": next_date.isoformat(),
            })

    return sorted(due, key=lambda x: x["next_date"])
```

Also add `timedelta` to the import at the top of the file — replace:
```python
from datetime import date
```
with:
```python
from datetime import date, timedelta
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/analysis/test_monthly_report.py -v
```
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/analysis/monthly_report.py tests/analysis/test_monthly_report.py
git commit -m "feat: add get_subscriptions_due() to monthly report"
```

---

### Task 4: Add FastAPI endpoints

**Files:**
- Modify: `backend/routes/analysis.py`

- [ ] **Step 1: Add imports at the top of `backend/routes/analysis.py`**

Add after the existing imports:

```python
from datetime import date as _date
```

- [ ] **Step 2: Add the two endpoints at the bottom of `backend/routes/analysis.py`**

```python
@router.get("/analysis/monthly-report")
def get_monthly_report(year: int, month: int):
    if not (1 <= month <= 12):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="month must be 1–12")

    import calendar
    month_end = _date(year, month, calendar.monthrange(year, month)[1])

    with get_session() as session:
        from backend.db.models import MonthlyReportCache, Subscription
        from backend.analysis.monthly_report import get_monthly_report_data, get_subscriptions_due

        all_txs = session.execute(select(Transaction)).scalars().all()
        spending_txs = [tx for tx in all_txs if not _is_payment(tx) and tx.amount > 0]

        subs = session.execute(
            select(Subscription).where(Subscription.active == True)
        ).scalars().all()

        cached = session.execute(
            select(MonthlyReportCache).where(
                MonthlyReportCache.year == year,
                MonthlyReportCache.month == month,
            )
        ).scalar_one_or_none()

        report = get_monthly_report_data(spending_txs, year=year, month=month)
        report["subscriptions_due"] = get_subscriptions_due(subs, report_month_end=month_end)
        report["narrative"] = cached.narrative if cached else None

    return report


@router.post("/analysis/monthly-report/narrative")
def generate_monthly_narrative(year: int, month: int):
    import calendar
    month_end = _date(year, month, calendar.monthrange(year, month)[1])

    with get_session() as session:
        from backend.db.models import MonthlyReportCache, Subscription
        from backend.analysis.monthly_report import get_monthly_report_data, get_subscriptions_due
        from datetime import datetime, timezone

        # Check cache first
        cached = session.execute(
            select(MonthlyReportCache).where(
                MonthlyReportCache.year == year,
                MonthlyReportCache.month == month,
            )
        ).scalar_one_or_none()
        if cached:
            return {"narrative": cached.narrative}

        all_txs = session.execute(select(Transaction)).scalars().all()
        spending_txs = [tx for tx in all_txs if not _is_payment(tx) and tx.amount > 0]
        subs = session.execute(
            select(Subscription).where(Subscription.active == True)
        ).scalars().all()

        report = get_monthly_report_data(spending_txs, year=year, month=month)
        due = get_subscriptions_due(subs, report_month_end=month_end)

        import calendar as _cal
        month_name = _cal.month_name[month]
        top3 = report["categories"][:3]
        cat_lines = "\n".join(
            f"- {c['name']}: ${c['current']:.0f} (prior month: ${c['prior']:.0f})"
            for c in top3
        )
        pct_change = ""
        if report["prev_total"] > 0:
            delta = (report["total"] - report["prev_total"]) / report["prev_total"] * 100
            pct_change = f", {abs(delta):.1f}% {'more' if delta > 0 else 'less'} than last month"
        due_text = f"{len(due)} subscription(s) renew in the next 30 days." if due else "No subscriptions renewing soon."

        prompt = (
            f"Write a 2-4 sentence plain English summary of someone's spending in {month_name} {year}. "
            f"They spent ${report['total']:.0f} total{pct_change}. "
            f"Top categories:\n{cat_lines}\n"
            f"{due_text} "
            f"Be specific about amounts. No preamble, no sign-off."
        )

        llm = get_llm_provider(use_pro=True)
        narrative = llm.complete(prompt).strip()

        entry = MonthlyReportCache(
            year=year,
            month=month,
            narrative=narrative,
            created_at=datetime.now(timezone.utc),
        )
        session.add(entry)

    return {"narrative": narrative}
```

- [ ] **Step 3: Manually test the endpoints**

Start the backend:
```bash
source .venv/bin/activate && uvicorn backend.main:app --reload
```

In another terminal:
```bash
# Should return report data with narrative: null
curl "http://localhost:8000/analysis/monthly-report?year=2026&month=4" | python3 -m json.tool

# Should generate and cache narrative (requires LLM key configured)
curl -X POST "http://localhost:8000/analysis/monthly-report/narrative?year=2026&month=4" | python3 -m json.tool

# Should now return cached narrative
curl "http://localhost:8000/analysis/monthly-report?year=2026&month=4" | python3 -m json.tool
```

Expected: First call returns JSON with `narrative: null`. POST returns `{"narrative": "..."}`. Second GET returns same narrative.

- [ ] **Step 4: Commit**

```bash
git add backend/routes/analysis.py
git commit -m "feat: add GET /analysis/monthly-report and POST /analysis/monthly-report/narrative endpoints"
```

---

### Task 5: Frontend API client

**Files:**
- Create: `frontend/src/api/reports.ts`

- [ ] **Step 1: Create `frontend/src/api/reports.ts`**

```typescript
const BASE = "http://localhost:8000";

export interface CategoryItem {
  name: string;
  current: number;
  prior: number;
}

export interface MerchantItem {
  name: string;
  total: number;
}

export interface SubscriptionDue {
  description: string;
  amount: number;
  next_date: string;
}

export interface MonthlyReport {
  year: number;
  month: number;
  total: number;
  prev_total: number;
  tx_count: number;
  categories: CategoryItem[];
  merchants: MerchantItem[];
  subscriptions_due: SubscriptionDue[];
  narrative: string | null;
}

export async function getMonthlyReport(year: number, month: number): Promise<MonthlyReport> {
  const res = await fetch(`${BASE}/analysis/monthly-report?year=${year}&month=${month}`);
  if (!res.ok) throw new Error("Failed to fetch monthly report");
  return res.json();
}

export async function generateNarrative(year: number, month: number): Promise<string> {
  const res = await fetch(
    `${BASE}/analysis/monthly-report/narrative?year=${year}&month=${month}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error("Failed to generate narrative");
  const data = await res.json();
  return data.narrative;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/reports.ts
git commit -m "feat: add Reports API client"
```

---

### Task 6: Build the Reports page

**Files:**
- Create: `frontend/src/pages/Reports.tsx`

- [ ] **Step 1: Create `frontend/src/pages/Reports.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import {
  getMonthlyReport, generateNarrative,
  MonthlyReport,
} from "../api/reports";

function lastCompleteMonth(): { year: number; month: number } {
  const today = new Date();
  const month = today.getMonth(); // 0-indexed, so this is "previous month" in 1-indexed
  const year = month === 0 ? today.getFullYear() - 1 : today.getFullYear();
  return { year, month: month === 0 ? 12 : month };
}

const MONTH_NAMES = [
  "", "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function pctChange(current: number, prior: number): string | null {
  if (prior === 0) return null;
  const pct = ((current - prior) / prior) * 100;
  return (pct > 0 ? "+" : "") + pct.toFixed(1) + "%";
}

function fmt(n: number): string {
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

export default function Reports() {
  const navigate = useNavigate();
  const initial = lastCompleteMonth();
  const [year, setYear] = useState(initial.year);
  const [month, setMonth] = useState(initial.month);
  const [report, setReport] = useState<MonthlyReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [narrativeLoading, setNarrativeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getMonthlyReport(year, month)
      .then(setReport)
      .catch(() => setError("Failed to load report."))
      .finally(() => setLoading(false));
  }, [year, month]);

  function stepMonth(delta: number) {
    let m = month + delta;
    let y = year;
    if (m < 1) { m = 12; y -= 1; }
    if (m > 12) { m = 1; y += 1; }
    setYear(y);
    setMonth(m);
  }

  async function handleGenerateNarrative() {
    if (!report) return;
    setNarrativeLoading(true);
    try {
      const narrative = await generateNarrative(year, month);
      setReport({ ...report, narrative });
    } finally {
      setNarrativeLoading(false);
    }
  }

  const card: React.CSSProperties = {
    background: "#1e1b4b", borderRadius: 12, padding: "20px 24px", marginBottom: 20,
  };
  const label: React.CSSProperties = { fontSize: 12, color: "#9ca3af", marginBottom: 4 };
  const sectionTitle: React.CSSProperties = {
    fontSize: 13, fontWeight: 700, color: "#a5b4fc", letterSpacing: "0.05em",
    textTransform: "uppercase", marginBottom: 14,
  };

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "32px 24px", color: "#e0e7ff" }}>
      {/* Header + month picker */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 28 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: "#fff", margin: 0 }}>Monthly Report</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={() => stepMonth(-1)}
            style={{ background: "#312e81", border: "none", color: "#c4b5fd", borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: 16 }}
          >◀</button>
          <span style={{ fontWeight: 600, fontSize: 16, minWidth: 140, textAlign: "center" }}>
            {MONTH_NAMES[month]} {year}
          </span>
          <button
            onClick={() => stepMonth(1)}
            style={{ background: "#312e81", border: "none", color: "#c4b5fd", borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontSize: 16 }}
          >▶</button>
        </div>
      </div>

      {loading && <div style={{ color: "#9ca3af", textAlign: "center", padding: 60 }}>Loading...</div>}
      {error && <div style={{ color: "#f87171", textAlign: "center", padding: 60 }}>{error}</div>}

      {report && !loading && (
        <>
          {/* 1. AI Narrative */}
          <div style={card}>
            <div style={sectionTitle}>Summary</div>
            {report.narrative ? (
              <p style={{ margin: 0, lineHeight: 1.7, color: "#e0e7ff" }}>{report.narrative}</p>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <p style={{ margin: 0, color: "#6b7280" }}>No summary generated yet.</p>
                <button
                  onClick={handleGenerateNarrative}
                  disabled={narrativeLoading}
                  style={{
                    background: "#7c6af7", border: "none", color: "#fff", borderRadius: 8,
                    padding: "8px 18px", cursor: narrativeLoading ? "default" : "pointer",
                    fontSize: 13, opacity: narrativeLoading ? 0.6 : 1,
                  }}
                >
                  {narrativeLoading ? "Generating…" : "Generate summary"}
                </button>
              </div>
            )}
          </div>

          {/* 2. Stats row */}
          <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
            {[
              { label: "Total spent", value: fmt(report.total) },
              {
                label: "vs last month",
                value: pctChange(report.total, report.prev_total) ?? "—",
                valueColor: report.total <= report.prev_total ? "#6ee7b7" : "#f87171",
                sub: report.prev_total > 0
                  ? `${report.total <= report.prev_total ? "−" : "+"}${fmt(Math.abs(report.total - report.prev_total))}`
                  : undefined,
              },
              { label: "Transactions", value: String(report.tx_count) },
            ].map((s) => (
              <div key={s.label} style={{ ...card, flex: 1, marginBottom: 0, textAlign: "center" }}>
                <div style={label}>{s.label}</div>
                <div style={{ fontSize: 26, fontWeight: 700, color: (s as any).valueColor ?? "#fff" }}>{s.value}</div>
                {(s as any).sub && <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 2 }}>{(s as any).sub}</div>}
              </div>
            ))}
          </div>

          {/* 3. Category breakdown */}
          {report.categories.length > 0 && (
            <div style={card}>
              <div style={sectionTitle}>Spending by Category</div>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart
                  data={report.categories}
                  layout="vertical"
                  margin={{ left: 80, right: 30, top: 4, bottom: 4 }}
                  onClick={(data) => {
                    if (!data?.activePayload) return;
                    const cat = (data.activePayload[0]?.payload as any)?.name;
                    if (!cat) return;
                    const pad = (n: number) => String(n).padStart(2, "0");
                    const from = `${year}-${pad(month)}-01`;
                    const lastDay = new Date(year, month, 0).getDate();
                    const to = `${year}-${pad(month)}-${pad(lastDay)}`;
                    navigate(`/transactions?category=${encodeURIComponent(cat)}&dateFrom=${from}&dateTo=${to}`);
                  }}
                  style={{ cursor: "pointer" }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#312e81" horizontal={false} />
                  <XAxis type="number" tick={{ fill: "#9ca3af", fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fill: "#e0e7ff", fontSize: 12 }} width={76} />
                  <Tooltip
                    contentStyle={{ background: "#1e1b4b", border: "1px solid #312e81", borderRadius: 8 }}
                    labelStyle={{ color: "#c4b5fd" }}
                    itemStyle={{ color: "#e0e7ff" }}
                    formatter={(v: number) => fmt(v)}
                  />
                  <Legend wrapperStyle={{ color: "#9ca3af", fontSize: 12 }} />
                  <Bar dataKey="current" name={`${MONTH_NAMES[month]}`} fill="#7c6af7" radius={[0, 3, 3, 0]} />
                  <Bar dataKey="prior" name="Prior month" fill="#c4b5fd" radius={[0, 3, 3, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* 4. Top merchants */}
          {report.merchants.length > 0 && (
            <div style={card}>
              <div style={sectionTitle}>Top Merchants</div>
              {report.merchants.map((m, i) => {
                const pad = (n: number) => String(n).padStart(2, "0");
                const from = `${year}-${pad(month)}-01`;
                const lastDay = new Date(year, month, 0).getDate();
                const to = `${year}-${pad(month)}-${pad(lastDay)}`;
                return (
                  <div
                    key={m.name}
                    onClick={() => navigate(`/transactions?search=${encodeURIComponent(m.name)}&dateFrom=${from}&dateTo=${to}`)}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "10px 0", borderBottom: i < report.merchants.length - 1 ? "1px solid #312e81" : "none",
                      cursor: "pointer",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.75")}
                    onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span style={{ fontSize: 12, color: "#6b7280", minWidth: 18 }}>{i + 1}</span>
                      <span style={{ color: "#e0e7ff" }}>{m.name}</span>
                    </div>
                    <span style={{ color: "#c4b5fd", fontWeight: 600 }}>{fmt(m.total)}</span>
                  </div>
                );
              })}
            </div>
          )}

          {/* 5. Subscriptions due */}
          {report.subscriptions_due.length > 0 && (
            <div style={card}>
              <div style={sectionTitle}>Subscriptions Renewing Soon</div>
              {report.subscriptions_due.map((s) => (
                <div
                  key={s.description + s.next_date}
                  onClick={() => navigate("/subscriptions")}
                  style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: "10px 0",
                    borderBottom: "1px solid #312e81",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.75")}
                  onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
                >
                  <div>
                    <span style={{ color: "#fde68a", marginRight: 8 }}>⚠</span>
                    <span style={{ color: "#e0e7ff" }}>{s.description}</span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ color: "#c4b5fd", fontWeight: 600 }}>{fmt(s.amount)}</div>
                    <div style={{ fontSize: 11, color: "#6b7280" }}>{s.next_date}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Reports.tsx
git commit -m "feat: add Reports page"
```

---

### Task 7: Wire up routing and navigation

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Read `frontend/src/App.tsx` to find the nav links and routes**

Open `frontend/src/App.tsx` and locate:
1. The `<nav>` section containing links like `Insights`, `Subscriptions`
2. The `<Routes>` section containing `<Route path="/insights" ...>`

- [ ] **Step 2: Add the Reports import**

At the top of `frontend/src/App.tsx`, add alongside the other page imports:

```tsx
import Reports from "./pages/Reports";
```

- [ ] **Step 3: Add the nav link**

In the nav section, add a link between Insights and Subscriptions:

```tsx
<NavLink to="/reports">Reports</NavLink>
```

(Match the exact style/component pattern used by the other nav links in the file.)

- [ ] **Step 4: Add the route**

In the `<Routes>` section, add:

```tsx
<Route path="/reports" element={<Reports />} />
```

- [ ] **Step 5: Start the dev server and verify**

```bash
cd frontend && npm run dev
```

Open http://localhost:5173. Confirm:
- "Reports" appears in the nav
- Clicking it loads the Reports page
- The month picker shows last complete month by default
- Clicking ◀/▶ changes the month and reloads data
- Category bars link to `/transactions` with correct date filters
- Merchant rows link to `/transactions` with correct search/date filters
- Subscriptions due section links to `/subscriptions`
- "Generate summary" button calls the API and displays the narrative

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: wire Reports page into nav and routing"
```

---

## Self-Review

**Spec coverage:**
- ✅ New nav page between Insights and Subscriptions → Task 7
- ✅ Month picker defaulting to last complete month → Task 6 (`lastCompleteMonth()`)
- ✅ AI narrative card with Generate button, cached per month → Tasks 4 + 6
- ✅ Stats row (total, vs last month, tx count) → Task 6
- ✅ Category horizontal grouped bar chart, click navigates to transactions → Task 6
- ✅ Top 8 merchants, click navigates to transactions → Tasks 2 + 6
- ✅ Subscriptions due within 30 days, links to /subscriptions → Tasks 3 + 6
- ✅ `MonthlyReportCache` model → Task 1
- ✅ `get_monthly_report_data()` pure function → Task 2
- ✅ `get_subscriptions_due()` → Task 3
- ✅ `GET /analysis/monthly-report` endpoint → Task 4
- ✅ `POST /analysis/monthly-report/narrative` endpoint → Task 4
- ✅ Frontend API client with TypeScript types → Task 5

**Placeholder scan:** None found.

**Type consistency:**
- `get_monthly_report_data()` defined in Task 2, called in Task 4 endpoints — signature matches
- `get_subscriptions_due()` defined in Task 3, called in Task 4 — signature matches
- `MonthlyReport` interface in `reports.ts` matches the shape returned by the endpoint (Task 4 + Task 5)
- `CategoryItem.name`, `.current`, `.prior` used consistently across Tasks 2, 5, 6
- `MerchantItem.name`, `.total` used consistently across Tasks 2, 5, 6
