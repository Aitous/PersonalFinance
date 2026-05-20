# Insights & Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated Insights page with smart spending alerts, a full searchable merchant breakdown, day-of-week spending patterns, and year-over-year comparison.

**Architecture:** A new `backend/analysis/insights.py` module holds all six analysis functions. A single `GET /analysis/insights?merchant_days=90` endpoint in `backend/routes/analysis.py` calls them and returns one JSON payload. A new `Insights.tsx` React page renders the four sections. No DB schema changes needed.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, Python 3.9, React 18 + TypeScript, Recharts

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/analysis/insights.py` | Six pure analysis functions operating on `List[Transaction]` |
| Modify | `backend/routes/analysis.py` | Add `GET /analysis/insights` route (lines 1–83) |
| Create | `tests/test_insights.py` | Unit tests for all six analysis functions |
| Modify | `frontend/src/api/client.ts` | Add `getInsights(merchantDays)` |
| Modify | `frontend/src/App.tsx` | Add `/insights` route |
| Modify | `frontend/src/components/Sidebar.tsx` | Add Insights nav link |
| Create | `frontend/src/pages/Insights.tsx` | Full Insights page |

---

## Task 1: Backend analysis functions

**Files:**
- Create: `backend/analysis/insights.py`
- Create: `tests/test_insights.py`

### Context

The project root is `/Users/youssefaitousarrah/Documents/PersonalFinance`. The venv is at `.venv`. Run backend tests with:
```bash
cd /Users/youssefaitousarrah/Documents/PersonalFinance
source .venv/bin/activate
python -m pytest tests/test_insights.py -v
```

`_normalize()` lives in `backend/analysis/subscription_detector.py:14–18`. It strips trailing transaction IDs, uppercase the string, and removes location codes. Import it directly — do not copy it.

`Transaction` model fields relevant here: `id`, `date` (Python `date`), `description` (str), `amount` (float, always positive for spending), `category` (str|None), `source` (str).

- [ ] **Step 1: Write the failing tests**

Create `tests/__init__.py` (empty) if it doesn't exist, then create `tests/test_insights.py`:

```python
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

def _tx(description, amount, category="dining", days_ago=0, source="chase"):
    tx = MagicMock()
    tx.description = description
    tx.amount = amount
    tx.category = category
    tx.date = date.today() - timedelta(days=days_ago)
    tx.source = source
    return tx

# ── anomalies ──────────────────────────────────────────────────────────────

def test_anomaly_detected_when_current_is_2x_average():
    from backend.analysis.insights import get_spending_anomalies
    today = date.today()
    # 3 prior months of ~$100 dining, current month $250+
    txs = []
    for months_back in [1, 2, 3]:
        for _ in range(3):
            d = today.replace(day=5) - timedelta(days=months_back * 30)
            tx = MagicMock()
            tx.description = "RESTAURANT"
            tx.amount = 35.0
            tx.category = "dining"
            tx.date = d
            tx.source = "chase"
            txs.append(tx)
    # Current month: 4 transactions totalling $260
    for i in range(4):
        tx = MagicMock()
        tx.description = "RESTAURANT"
        tx.amount = 65.0
        tx.category = "dining"
        tx.date = today.replace(day=i + 1)
        tx.source = "chase"
        txs.append(tx)
    result = get_spending_anomalies(txs)
    assert len(result) == 1
    assert result[0]["category"] == "dining"
    assert result[0]["ratio"] >= 2.0

def test_no_anomaly_when_below_2x():
    from backend.analysis.insights import get_spending_anomalies
    today = date.today()
    txs = []
    for months_back in [1, 2, 3]:
        for _ in range(3):
            d = today.replace(day=5) - timedelta(days=months_back * 30)
            tx = MagicMock()
            tx.description = "RESTAURANT"
            tx.amount = 50.0
            tx.category = "dining"
            tx.date = d
            tx.source = "chase"
            txs.append(tx)
    for _ in range(3):
        tx = MagicMock()
        tx.description = "RESTAURANT"
        tx.amount = 55.0
        tx.category = "dining"
        tx.date = today.replace(day=1)
        tx.source = "chase"
        txs.append(tx)
    result = get_spending_anomalies(txs)
    assert result == []

def test_no_anomaly_when_fewer_than_3_txs_current_month():
    from backend.analysis.insights import get_spending_anomalies
    today = date.today()
    txs = []
    for months_back in [1, 2, 3]:
        for _ in range(3):
            d = today.replace(day=5) - timedelta(days=months_back * 30)
            tx = MagicMock()
            tx.description = "RESTAURANT"
            tx.amount = 30.0
            tx.category = "dining"
            tx.date = d
            tx.source = "chase"
            txs.append(tx)
    # Only 2 txs this month but very large
    for _ in range(2):
        tx = MagicMock()
        tx.description = "RESTAURANT"
        tx.amount = 500.0
        tx.category = "dining"
        tx.date = today.replace(day=1)
        tx.source = "chase"
        txs.append(tx)
    result = get_spending_anomalies(txs)
    assert result == []

# ── duplicates ─────────────────────────────────────────────────────────────

def test_duplicate_same_amount_within_7_days():
    from backend.analysis.insights import get_duplicate_charges
    today = date.today()
    txs = [
        _tx("NETFLIX.COM", 15.49, "subscriptions", days_ago=3),
        _tx("NETFLIX.COM", 15.49, "subscriptions", days_ago=0),
    ]
    result = get_duplicate_charges(txs)
    assert len(result) == 1
    assert result[0]["merchant"] == "NETFLIX.COM"
    assert result[0]["amount"] == 15.49

def test_no_duplicate_beyond_7_days():
    from backend.analysis.insights import get_duplicate_charges
    txs = [
        _tx("NETFLIX.COM", 15.49, "subscriptions", days_ago=35),
        _tx("NETFLIX.COM", 15.49, "subscriptions", days_ago=0),
    ]
    result = get_duplicate_charges(txs)
    assert result == []

def test_no_duplicate_for_recurring_merchant():
    from backend.analysis.insights import get_duplicate_charges
    today = date.today()
    # 8 monthly charges of same amount — should be treated as recurring, not duplicate
    txs = [_tx("SPOTIFY", 9.99, "subscriptions", days_ago=i*30) for i in range(8)]
    result = get_duplicate_charges(txs)
    assert result == []

# ── price increases ────────────────────────────────────────────────────────

def test_price_increase_detected():
    from backend.analysis.insights import get_price_increases
    today = date.today()
    # 8 charges at $9.99, then 2 at $13.99
    txs = [_tx("SPOTIFY", 9.99, "subscriptions", days_ago=(9-i)*30) for i in range(8)]
    txs.append(_tx("SPOTIFY", 13.99, "subscriptions", days_ago=30))
    txs.append(_tx("SPOTIFY", 13.99, "subscriptions", days_ago=0))
    result = get_price_increases(txs)
    assert len(result) == 1
    assert result[0]["merchant"] == "SPOTIFY"
    assert result[0]["old_amount"] == 9.99
    assert result[0]["new_amount"] == 13.99

def test_no_price_increase_within_5_pct():
    from backend.analysis.insights import get_price_increases
    txs = [_tx("SPOTIFY", 9.99, "subscriptions", days_ago=i*30) for i in range(10)]
    txs.append(_tx("SPOTIFY", 10.29, "subscriptions", days_ago=0))  # ~3% increase
    result = get_price_increases(txs)
    assert result == []

# ── merchant breakdown ─────────────────────────────────────────────────────

def test_merchant_breakdown_aggregates_and_sorts():
    from backend.analysis.insights import get_merchant_breakdown
    txs = [
        _tx("AMAZON.COM", 50.0, "shopping", days_ago=5),
        _tx("AMAZON.COM", 30.0, "shopping", days_ago=2),
        _tx("COSTCO WHSE", 200.0, "groceries", days_ago=3),
    ]
    result = get_merchant_breakdown(txs)
    assert result[0]["name"] == "COSTCO WHSE"
    assert result[0]["total"] == 200.0
    assert result[1]["name"] == "AMAZON.COM"
    assert result[1]["total"] == 80.0
    assert result[1]["tx_count"] == 2

# ── day of week ────────────────────────────────────────────────────────────

def test_day_of_week_returns_7_entries():
    from backend.analysis.insights import get_day_of_week
    txs = [_tx("SHOP", 10.0, days_ago=i) for i in range(14)]
    result = get_day_of_week(txs)
    assert len(result["days"]) == 7
    assert "weekend_pct" in result
    assert 0 <= result["weekend_pct"] <= 100

# ── year over year ─────────────────────────────────────────────────────────

def test_yoy_insufficient_data_when_only_one_year():
    from backend.analysis.insights import get_year_over_year
    txs = [_tx("SHOP", 100.0, days_ago=i*10) for i in range(5)]
    result = get_year_over_year(txs)
    assert result["insufficient_data"] is True

def test_yoy_returns_two_years():
    from backend.analysis.insights import get_year_over_year
    today = date.today()
    txs = []
    for i in range(5):
        tx = MagicMock()
        tx.description = "SHOP"
        tx.amount = 100.0
        tx.category = "shopping"
        tx.date = today.replace(year=today.year - 1, month=i + 1, day=1)
        tx.source = "chase"
        txs.append(tx)
    for i in range(3):
        tx = MagicMock()
        tx.description = "SHOP"
        tx.amount = 120.0
        tx.category = "shopping"
        tx.date = today.replace(month=i + 1, day=1)
        tx.source = "chase"
        txs.append(tx)
    result = get_year_over_year(txs)
    assert result["insufficient_data"] is False
    assert len(result["years"]) == 2
    assert result["on_pace"] is not None
```

- [ ] **Step 2: Run tests to verify they all fail**

```bash
cd /Users/youssefaitousarrah/Documents/PersonalFinance && source .venv/bin/activate && python -m pytest tests/test_insights.py -v 2>&1 | head -40
```

Expected: All tests fail with `ModuleNotFoundError: No module named 'backend.analysis.insights'`

- [ ] **Step 3: Create `backend/analysis/insights.py`**

```python
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import List

from backend.analysis.subscription_detector import (
    _normalize, MONTHLY_DAYS_MIN, MONTHLY_DAYS_MAX, ANNUAL_DAYS_MIN, ANNUAL_DAYS_MAX,
)
from backend.db.models import Transaction


def get_spending_anomalies(txs: List[Transaction]) -> List[dict]:
    today = date.today()
    current_month = today.strftime("%Y-%m")

    by_cat_month: dict = defaultdict(lambda: defaultdict(list))
    for tx in txs:
        month_key = tx.date.strftime("%Y-%m")
        cat = tx.category or "other"
        by_cat_month[cat][month_key].append(tx.amount)

    anomalies = []
    for cat, months_data in by_cat_month.items():
        if current_month not in months_data:
            continue
        current_txs = months_data[current_month]
        if len(current_txs) < 3:
            continue
        current_amount = sum(current_txs)

        prior_months = sorted(m for m in months_data if m != current_month)
        if len(prior_months) < 3:
            continue
        # Use the 3 most recent prior months
        recent_prior = prior_months[-3:]
        prior_totals = [sum(months_data[m]) for m in recent_prior]
        avg = sum(prior_totals) / len(prior_totals)

        if avg > 0 and current_amount / avg >= 2.0:
            anomalies.append({
                "category": cat,
                "current_amount": round(current_amount, 2),
                "avg_amount": round(avg, 2),
                "ratio": round(current_amount / avg, 2),
                "tx_count": len(current_txs),
            })

    return sorted(anomalies, key=lambda x: -x["ratio"])


def get_duplicate_charges(txs: List[Transaction]) -> List[dict]:
    groups: dict = defaultdict(list)
    for tx in txs:
        key = _normalize(tx.description)
        groups[key].append(tx)

    # Identify recurring merchants to exclude (stable amount, 6+ charges)
    recurring: set = set()
    for key, merchant_txs in groups.items():
        if len(merchant_txs) >= 6:
            amounts = [t.amount for t in merchant_txs]
            avg = sum(amounts) / len(amounts)
            if avg > 0 and (max(amounts) - min(amounts)) / avg <= 0.15:
                recurring.add(key)

    duplicates = []
    for key, merchant_txs in groups.items():
        if key in recurring:
            continue
        sorted_txs = sorted(merchant_txs, key=lambda t: t.date)
        seen_pairs: set = set()
        for i, tx1 in enumerate(sorted_txs):
            for tx2 in sorted_txs[i + 1:]:
                days_apart = (tx2.date - tx1.date).days
                if days_apart > 7:
                    break
                if abs(tx1.amount - tx2.amount) < 0.01:
                    pair_key = (round(tx1.amount, 2), tx1.date.isoformat())
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        duplicates.append({
                            "merchant": key,
                            "amount": round(tx1.amount, 2),
                            "dates": [tx1.date.isoformat(), tx2.date.isoformat()],
                            "sources": list({tx1.source, tx2.source}),
                        })
    return duplicates


def get_price_increases(txs: List[Transaction]) -> List[dict]:
    groups: dict = defaultdict(list)
    for tx in txs:
        key = _normalize(tx.description)
        groups[key].append(tx)

    increases = []
    for key, merchant_txs in groups.items():
        if len(merchant_txs) < 6:
            continue
        sorted_txs = sorted(merchant_txs, key=lambda t: t.date)

        gaps = [
            (sorted_txs[i + 1].date - sorted_txs[i].date).days
            for i in range(len(sorted_txs) - 1)
        ]
        avg_gap = sum(gaps) / len(gaps)
        if not (MONTHLY_DAYS_MIN <= avg_gap <= ANNUAL_DAYS_MAX):
            continue

        prior = sorted_txs[:-2]
        recent = sorted_txs[-2:]
        if not prior:
            continue

        prior_median = statistics.median(t.amount for t in prior)
        last_amount = recent[-1].amount

        if prior_median > 0 and (last_amount - prior_median) / prior_median > 0.05:
            increases.append({
                "merchant": key,
                "old_amount": round(prior_median, 2),
                "new_amount": round(last_amount, 2),
                "delta": round(last_amount - prior_median, 2),
                "first_new_date": recent[-1].date.isoformat(),
            })

    return increases


def get_merchant_breakdown(txs: List[Transaction]) -> List[dict]:
    groups: dict = defaultdict(list)
    for tx in txs:
        key = _normalize(tx.description)
        groups[key].append(tx)

    merchants = []
    for name, merchant_txs in groups.items():
        total = sum(t.amount for t in merchant_txs)
        last_date = max(t.date for t in merchant_txs)
        cat_counts: dict = defaultdict(int)
        for t in merchant_txs:
            cat_counts[t.category or "other"] += 1
        top_cat = max(cat_counts, key=lambda k: cat_counts[k])
        merchants.append({
            "name": name,
            "total": round(total, 2),
            "tx_count": len(merchant_txs),
            "category": top_cat,
            "last_date": last_date.isoformat(),
        })

    return sorted(merchants, key=lambda x: -x["total"])


def get_day_of_week(txs: List[Transaction]) -> dict:
    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    totals: dict = defaultdict(float)
    counts: dict = defaultdict(int)

    for tx in txs:
        dow = tx.date.weekday()
        totals[dow] += tx.amount
        counts[dow] += 1

    total_all = sum(totals.values())
    weekend_total = totals[5] + totals[6]
    weekend_pct = round(weekend_total / total_all * 100, 1) if total_all > 0 else 0.0

    return {
        "days": [
            {
                "day": i,
                "day_name": DAY_NAMES[i],
                "total": round(totals[i], 2),
                "tx_count": counts[i],
                "avg_per_tx": round(totals[i] / counts[i], 2) if counts[i] > 0 else 0.0,
            }
            for i in range(7)
        ],
        "weekend_pct": weekend_pct,
    }


def get_year_over_year(txs: List[Transaction]) -> dict:
    today = date.today()
    by_year_cat: dict = defaultdict(lambda: defaultdict(float))

    for tx in txs:
        by_year_cat[tx.date.year][tx.category or "other"] += tx.amount

    years_present = sorted(by_year_cat.keys())
    if len(years_present) < 2:
        return {"insufficient_data": True, "years": [], "on_pace": None, "on_pace_pct_change": None}

    years_to_show = years_present[-2:]
    years_data = []
    for y in years_to_show:
        cats = dict(by_year_cat[y])
        total = sum(cats.values())
        years_data.append({
            "year": y,
            "total": round(total, 2),
            "categories": {k: round(v, 2) for k, v in cats.items()},
        })

    on_pace = None
    on_pace_pct_change = None
    if years_to_show[-1] == today.year:
        day_of_year = today.timetuple().tm_yday
        ytd = sum(by_year_cat[today.year].values())
        on_pace = round(ytd / day_of_year * 365, 2)
        prior_total = sum(by_year_cat[years_to_show[0]].values())
        if prior_total > 0:
            on_pace_pct_change = round((on_pace - prior_total) / prior_total * 100, 1)

    return {
        "insufficient_data": False,
        "years": years_data,
        "on_pace": on_pace,
        "on_pace_pct_change": on_pace_pct_change,
    }
```

- [ ] **Step 4: Run tests to verify they all pass**

```bash
cd /Users/youssefaitousarrah/Documents/PersonalFinance && source .venv/bin/activate && python -m pytest tests/test_insights.py -v
```

Expected: All 13 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/analysis/insights.py tests/test_insights.py tests/__init__.py
git commit -m "feat: add insights analysis functions (anomalies, duplicates, price increases, merchants, dow, yoy)"
```

---

## Task 2: Wire up `/analysis/insights` route

**Files:**
- Modify: `backend/routes/analysis.py`

- [ ] **Step 1: Add the route**

Open `backend/routes/analysis.py`. After the existing imports, add `timedelta` is already imported. Add the following route at the end of the file (after line 83):

```python
@router.get("/analysis/insights")
def get_insights(merchant_days: int = 90):
    from backend.analysis.insights import (
        get_spending_anomalies, get_duplicate_charges, get_price_increases,
        get_merchant_breakdown, get_day_of_week, get_year_over_year,
    )
    merchant_days = max(7, min(merchant_days, 730))
    since = date.today() - timedelta(days=merchant_days)

    with get_session() as session:
        all_txs = session.execute(select(Transaction)).scalars().all()
        spending_txs = [tx for tx in all_txs if not _is_payment(tx) and tx.amount > 0]
        merchant_txs = [tx for tx in spending_txs if tx.date >= since]

    return {
        "alerts": {
            "anomalies": get_spending_anomalies(spending_txs),
            "duplicates": get_duplicate_charges(spending_txs),
            "price_increases": get_price_increases(spending_txs),
        },
        "merchants": get_merchant_breakdown(merchant_txs),
        "day_of_week": get_day_of_week(spending_txs),
        "year_over_year": get_year_over_year(spending_txs),
    }
```

- [ ] **Step 2: Verify the endpoint responds**

Make sure the backend is running (`uvicorn backend.main:app --reload` in a separate terminal), then:

```bash
curl -s "http://localhost:8000/analysis/insights" | python3 -m json.tool | head -40
```

Expected: JSON with keys `alerts`, `merchants`, `day_of_week`, `year_over_year`. `alerts` has sub-keys `anomalies`, `duplicates`, `price_increases`.

- [ ] **Step 3: Commit**

```bash
git add backend/routes/analysis.py
git commit -m "feat: add GET /analysis/insights endpoint"
```

---

## Task 3: Frontend wiring — API client, routing, sidebar

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Add `getInsights` to the API client**

Open `frontend/src/api/client.ts`. Add at the end of the file:

```typescript
export const getInsights = (merchantDays = 90) =>
  api.get("/analysis/insights", { params: { merchant_days: merchantDays } }).then((r) => r.data);
```

- [ ] **Step 2: Add the route in App.tsx**

Open `frontend/src/App.tsx`. Add the import at the top with the other page imports:

```typescript
import { Insights } from "./pages/Insights";
```

Add the route inside `<Routes>`, after the `/categories` route:

```tsx
<Route path="/insights" element={<Insights />} />
```

- [ ] **Step 3: Add the sidebar link**

Open `frontend/src/components/Sidebar.tsx`. Add the Insights entry to the `links` array, between Categories and Recurring:

```typescript
const links = [
  { to: "/", label: "Overview", icon: "📊" },
  { to: "/transactions", label: "Transactions", icon: "📋" },
  { to: "/categories", label: "Categories", icon: "🏷️" },
  { to: "/insights", label: "Insights", icon: "⚡" },
  { to: "/subscriptions", label: "Recurring", icon: "🔄" },
  { to: "/savings", label: "Savings Tips", icon: "💡" },
  { to: "/settings", label: "Settings", icon: "⚙️" },
];
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/App.tsx frontend/src/components/Sidebar.tsx
git commit -m "feat: wire up Insights page routing and sidebar link"
```

---

## Task 4: Build `Insights.tsx`

**Files:**
- Create: `frontend/src/pages/Insights.tsx`

This is a self-contained page. It has four sections rendered sequentially. Uses inline styles consistent with the rest of the codebase (no CSS files, no Tailwind). Uses Recharts `BarChart` for the day-of-week chart (already installed).

- [ ] **Step 1: Create `frontend/src/pages/Insights.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getInsights } from "../api/client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

const SECTION = {
  background: "#fff", borderRadius: 10, padding: 24,
  boxShadow: "0 1px 4px rgba(0,0,0,0.07)", marginBottom: 24,
};

const CATEGORY_COLORS: Record<string, string> = {
  dining: "#7c6af7", groceries: "#a78bfa", transport: "#c4b5fd",
  shopping: "#60a5fa", entertainment: "#34d399", subscriptions: "#f59e0b",
  health: "#f87171", travel: "#38bdf8", utilities: "#94a3b8", other: "#d1d5db",
};

export function Insights() {
  const navigate = useNavigate();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [merchantDays, setMerchantDays] = useState(90);
  const [merchantSearch, setMerchantSearch] = useState("");

  useEffect(() => {
    setLoading(true);
    getInsights(merchantDays)
      .then(setData)
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  }, [merchantDays]);

  if (loading) return <p>Loading insights…</p>;
  if (error) return <p style={{ color: "red" }}>Failed to load insights: {error}</p>;
  if (!data) return null;

  const { alerts, merchants, day_of_week, year_over_year } = data;
  const totalAlerts = alerts.anomalies.length + alerts.duplicates.length + alerts.price_increases.length;

  const filteredMerchants = merchants.filter((m: any) =>
    m.name.toLowerCase().includes(merchantSearch.toLowerCase())
  );

  const maxDow = Math.max(...day_of_week.days.map((d: any) => d.total), 1);

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24 }}>Insights</h1>

      {/* ── Alerts ── */}
      <div style={SECTION}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>⚡ Alerts</h2>
        {totalAlerts === 0 ? (
          <div style={{ background: "#d1fae5", borderLeft: "3px solid #10b981", padding: "10px 14px", borderRadius: 6 }}>
            <span style={{ color: "#065f46", fontWeight: 600 }}>✓ All clear — no anomalies detected this month.</span>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {alerts.anomalies.map((a: any) => (
              <div key={a.category} style={{ background: "#fef3c7", borderLeft: "3px solid #f59e0b", padding: "10px 14px", borderRadius: 6 }}>
                <div style={{ fontWeight: 600, color: "#92400e" }}>
                  ⚠ {a.category.charAt(0).toUpperCase() + a.category.slice(1)} spend is {a.ratio}× your 3-month average
                </div>
                <div style={{ color: "#78350f", marginTop: 2, fontSize: 13 }}>
                  ${a.current_amount.toFixed(2)} this month vs. ${a.avg_amount.toFixed(2)} avg — {a.tx_count} transactions
                </div>
              </div>
            ))}
            {alerts.duplicates.map((d: any, i: number) => (
              <div key={i} style={{ background: "#fee2e2", borderLeft: "3px solid #ef4444", padding: "10px 14px", borderRadius: 6 }}>
                <div style={{ fontWeight: 600, color: "#991b1b" }}>
                  🔁 Possible duplicate: {d.merchant}
                </div>
                <div style={{ color: "#7f1d1d", marginTop: 2, fontSize: 13 }}>
                  ${d.amount.toFixed(2)} charged {d.dates.length} times ({d.dates.join(" & ")})
                </div>
              </div>
            ))}
            {alerts.price_increases.map((p: any, i: number) => (
              <div key={i} style={{ background: "#ede9fe", borderLeft: "3px solid #7c3aed", padding: "10px 14px", borderRadius: 6 }}>
                <div style={{ fontWeight: 600, color: "#4c1d95" }}>
                  📈 Price increase: {p.merchant}
                </div>
                <div style={{ color: "#3b0764", marginTop: 2, fontSize: 13 }}>
                  ${p.old_amount.toFixed(2)} → ${p.new_amount.toFixed(2)} starting {p.first_new_date} (+${p.delta.toFixed(2)}/mo)
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Merchant Breakdown ── */}
      <div style={SECTION}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>🏪 Merchant Breakdown</h2>
        <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
          <input
            value={merchantSearch}
            onChange={(e) => setMerchantSearch(e.target.value)}
            placeholder="Search merchants…"
            style={{ flex: 1, padding: "7px 12px", borderRadius: 6, border: "1.5px solid #e5e7eb", fontSize: 13 }}
          />
          <select
            value={merchantDays}
            onChange={(e) => setMerchantDays(Number(e.target.value))}
            style={{ padding: "7px 10px", borderRadius: 6, border: "1px solid #ddd", fontSize: 13 }}
          >
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 6 months</option>
            <option value={730}>All time</option>
          </select>
        </div>
        <div style={{ background: "#fff", borderRadius: 8, overflow: "hidden", border: "1px solid #f0f0f0" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f9fafb", textAlign: "left" }}>
                <th style={{ padding: "10px 16px", fontWeight: 600, color: "#6b7280" }}>Merchant</th>
                <th style={{ padding: "10px 16px", fontWeight: 600, color: "#6b7280" }}>Category</th>
                <th style={{ padding: "10px 16px", fontWeight: 600, color: "#6b7280", textAlign: "right" }}>Txns</th>
                <th style={{ padding: "10px 16px", fontWeight: 600, color: "#6b7280", textAlign: "right" }}>Total</th>
                <th style={{ padding: "10px 16px", fontWeight: 600, color: "#6b7280", width: 120 }}></th>
              </tr>
            </thead>
            <tbody>
              {filteredMerchants.map((m: any) => {
                const maxTotal = merchants[0]?.total ?? 1;
                const barWidth = Math.round((m.total / maxTotal) * 100);
                return (
                  <tr
                    key={m.name}
                    style={{ borderTop: "1px solid #f0f0f0", cursor: "pointer" }}
                    onClick={() => navigate(`/transactions?q=${encodeURIComponent(m.name)}`)}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#f9fafb")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "")}
                  >
                    <td style={{ padding: "9px 16px", fontWeight: 500 }}>{m.name}</td>
                    <td style={{ padding: "9px 16px" }}>
                      <span style={{
                        background: CATEGORY_COLORS[m.category] ?? "#d1d5db",
                        color: "#fff", padding: "2px 8px", borderRadius: 12, fontSize: 11,
                      }}>{m.category}</span>
                    </td>
                    <td style={{ padding: "9px 16px", textAlign: "right", color: "#9ca3af" }}>{m.tx_count}</td>
                    <td style={{ padding: "9px 16px", textAlign: "right", fontWeight: 600 }}>${m.total.toFixed(2)}</td>
                    <td style={{ padding: "9px 16px" }}>
                      <div style={{ background: "#e5e7eb", borderRadius: 3, height: 6 }}>
                        <div style={{ width: `${barWidth}%`, background: "#7c6af7", borderRadius: 3, height: 6 }} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filteredMerchants.length === 0 && (
            <p style={{ textAlign: "center", color: "#9ca3af", padding: 24 }}>No merchants match your search.</p>
          )}
        </div>
        <div style={{ color: "#9ca3af", fontSize: 12, marginTop: 8 }}>
          Showing {filteredMerchants.length} of {merchants.length} merchants — click a row to see transactions
        </div>
      </div>

      {/* ── Day of Week ── */}
      <div style={SECTION}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>📅 Spending by Day of Week</h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={day_of_week.days} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
            <XAxis dataKey="day_name" tick={{ fontSize: 12 }} tickFormatter={(v) => v.slice(0, 3)} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip
              formatter={(value: number) => [`$${value.toFixed(2)}`, "Total"]}
              contentStyle={{ background: "#1a1a2e", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 }}
            />
            <Bar dataKey="total" radius={[4, 4, 0, 0]}>
              {day_of_week.days.map((d: any) => (
                <Cell key={d.day} fill={d.day >= 5 ? "#f59e0b" : "#7c6af7"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p style={{ color: "#6b7280", fontSize: 13, margin: "8px 0 0" }}>
          Weekends (Sat–Sun) account for <strong>{day_of_week.weekend_pct}%</strong> of your spending.
        </p>
      </div>

      {/* ── Year over Year ── */}
      {!year_over_year.insufficient_data && (
        <div style={SECTION}>
          <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>📊 Year-over-Year</h2>
          <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
            {year_over_year.years.map((y: any) => (
              <div key={y.year} style={{ flex: 1, background: "#f9fafb", borderRadius: 8, padding: "12px 16px", textAlign: "center" }}>
                <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>{y.year}</div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>${y.total.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</div>
              </div>
            ))}
            {year_over_year.on_pace !== null && (
              <div style={{
                flex: 1, background: year_over_year.on_pace_pct_change > 0 ? "#fef3c7" : "#d1fae5",
                borderRadius: 8, padding: "12px 16px", textAlign: "center",
              }}>
                <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>On pace for</div>
                <div style={{ fontSize: 22, fontWeight: 700 }}>${year_over_year.on_pace.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</div>
                {year_over_year.on_pace_pct_change !== null && (
                  <div style={{ fontSize: 12, color: year_over_year.on_pace_pct_change > 0 ? "#92400e" : "#065f46", marginTop: 2 }}>
                    {year_over_year.on_pace_pct_change > 0 ? "+" : ""}{year_over_year.on_pace_pct_change}% vs last year
                  </div>
                )}
              </div>
            )}
          </div>
          {/* Category breakdown grouped bar chart */}
          {(() => {
            const allCats = new Set<string>();
            year_over_year.years.forEach((y: any) => Object.keys(y.categories).forEach((c: string) => allCats.add(c)));
            const cats = Array.from(allCats).filter((c) => c !== "other");
            const chartData = cats.map((cat) => {
              const entry: Record<string, any> = { category: cat.slice(0, 10) };
              year_over_year.years.forEach((y: any) => { entry[String(y.year)] = y.categories[cat] ?? 0; });
              return entry;
            }).sort((a, b) => {
              const lastYear = String(year_over_year.years[year_over_year.years.length - 1].year);
              return (b[lastYear] ?? 0) - (a[lastYear] ?? 0);
            }).slice(0, 8);

            const yearKeys = year_over_year.years.map((y: any) => String(y.year));
            const YEAR_COLORS = ["#c4b5fd", "#7c6af7"];

            return (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
                  <XAxis dataKey="category" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                  <Tooltip
                    formatter={(value: number, name: string) => [`$${value.toFixed(0)}`, name]}
                    contentStyle={{ background: "#1a1a2e", border: "none", borderRadius: 8, color: "#fff", fontSize: 12 }}
                  />
                  {yearKeys.map((yr, i) => (
                    <Bar key={yr} dataKey={yr} fill={YEAR_COLORS[i % YEAR_COLORS.length]} radius={[3, 3, 0, 0]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            );
          })()}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify the page loads in the browser**

Open `http://localhost:5173/insights`. You should see:
- An "Alerts" section (either a green "All clear" banner or colored alert cards)
- A "Merchant Breakdown" table with a search box and time window selector
- A "Spending by Day of Week" bar chart with weekday bars in purple and weekend bars in amber
- A "Year-over-Year" section if you have 2+ years of data (hidden otherwise)

Click a merchant row — it should navigate to `/transactions?q=MERCHANT_NAME`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Insights.tsx
git commit -m "feat: add Insights page with alerts, merchant breakdown, day-of-week, and YoY sections"
```
