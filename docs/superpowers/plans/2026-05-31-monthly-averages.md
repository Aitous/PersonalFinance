# Monthly Averages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Average Monthly Spending" section to the Insights page showing total avg/month and a per-category breakdown table, with preset (3M/6M/12M) and custom date range controls.

**Architecture:** A new `get_monthly_averages()` pure function in `backend/analysis/insights.py` groups spending transactions by month+category, excludes the current partial month, and returns per-category averages and an overall total. A new `GET /analysis/monthly-averages` endpoint wraps it. The frontend adds controls and two display cards at the bottom of `Insights.tsx`, fetching on demand when the user changes the time range.

**Tech Stack:** FastAPI, Python 3.9, React 18 TypeScript, existing `_is_payment` / `Transaction` patterns from `backend/routes/analysis.py`.

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `backend/analysis/insights.py` | Modify | Add `get_monthly_averages()` |
| `backend/routes/analysis.py` | Modify | Add `GET /analysis/monthly-averages` endpoint |
| `frontend/src/pages/Insights.tsx` | Modify | Add controls + total card + category table |
| `tests/analysis/test_monthly_averages.py` | Create | Unit tests for `get_monthly_averages()` |

---

### Task 1: Implement `get_monthly_averages()` pure function

**Files:**
- Modify: `backend/analysis/insights.py`
- Create: `tests/analysis/test_monthly_averages.py`

- [ ] **Step 1: Write failing tests**

Create `tests/analysis/test_monthly_averages.py`:

```python
import pytest
from datetime import date
from unittest.mock import MagicMock


def _tx(amount, category, year, month, day=15):
    tx = MagicMock()
    tx.amount = amount
    tx.category = category
    tx.date = date(year, month, day)
    return tx


def test_averages_over_complete_months():
    from backend.analysis.insights import get_monthly_averages
    txs = [
        _tx(100.0, "dining", 2026, 1),
        _tx(200.0, "dining", 2026, 2),
        _tx(150.0, "groceries", 2026, 1),
        _tx(50.0, "groceries", 2026, 2),
    ]
    # date_from=2026-01-01, date_to=2026-02-28 → 2 complete months
    result = get_monthly_averages(txs, date_from=date(2026, 1, 1), date_to=date(2026, 2, 28))
    assert result["months_count"] == 2
    assert result["total_avg"] == 250.0  # (300 + 250) / 2
    cats = {c["category"]: c for c in result["categories"]}
    assert cats["dining"]["avg"] == 150.0   # (100 + 200) / 2
    assert cats["dining"]["pct"] == 60.0    # 150 / 250 * 100
    assert cats["groceries"]["avg"] == 100.0
    assert cats["groceries"]["pct"] == 40.0


def test_current_partial_month_excluded():
    from backend.analysis.insights import get_monthly_averages
    from datetime import date as _date
    today = _date.today()
    # Two complete months + some transactions this month
    txs = [
        _tx(100.0, "dining", today.year, today.month - 2 if today.month > 2 else 1, 15),
        _tx(100.0, "dining", today.year, today.month - 1 if today.month > 1 else 2, 15),
        _tx(999.0, "dining", today.year, today.month, 1),  # current month — should be excluded
    ]
    date_from = date(today.year, today.month - 2 if today.month > 2 else 1, 1)
    result = get_monthly_averages(txs, date_from=date_from, date_to=today)
    # current month txs excluded — avg should be 100, not skewed by 999
    assert result["total_avg"] == 100.0


def test_categories_sorted_descending_by_avg():
    from backend.analysis.insights import get_monthly_averages
    txs = [
        _tx(50.0, "dining", 2026, 1),
        _tx(200.0, "groceries", 2026, 1),
        _tx(10.0, "entertainment", 2026, 1),
    ]
    result = get_monthly_averages(txs, date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    avgs = [c["avg"] for c in result["categories"]]
    assert avgs == sorted(avgs, reverse=True)


def test_empty_transactions_returns_zeros():
    from backend.analysis.insights import get_monthly_averages
    result = get_monthly_averages([], date_from=date(2026, 1, 1), date_to=date(2026, 3, 31))
    assert result["total_avg"] == 0.0
    assert result["categories"] == []
    assert result["months_count"] == 0


def test_months_with_spend_counts_correctly():
    from backend.analysis.insights import get_monthly_averages
    # Category appears in only 1 of 3 months
    txs = [
        _tx(90.0, "dining", 2026, 1),
        _tx(90.0, "dining", 2026, 2),
        _tx(90.0, "dining", 2026, 3),
        _tx(300.0, "travel", 2026, 2),  # travel only in Feb
    ]
    result = get_monthly_averages(txs, date_from=date(2026, 1, 1), date_to=date(2026, 3, 31))
    cats = {c["category"]: c for c in result["categories"]}
    assert cats["travel"]["months_with_spend"] == 1
    assert cats["dining"]["months_with_spend"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/youssefaitousarrah/Documents/PersonalFinance && source .venv/bin/activate
pytest tests/analysis/test_monthly_averages.py -v
```
Expected: FAIL with `ImportError: cannot import name 'get_monthly_averages'`

- [ ] **Step 3: Add `get_monthly_averages()` to `backend/analysis/insights.py`**

Add this function at the bottom of `backend/analysis/insights.py`:

```python
def get_monthly_averages(txs: List[Transaction], date_from: date, date_to: date) -> dict:
    """
    Pure function. Accepts pre-filtered spending transactions (no payments, amount > 0).
    Excludes the current in-progress month from averages.
    Returns per-category averages and overall total average over complete months only.
    """
    today = date.today()
    current_month_key = today.strftime("%Y-%m")

    # Group by month+category, excluding current partial month
    by_month: dict = defaultdict(lambda: defaultdict(float))
    for tx in txs:
        if tx.date < date_from or tx.date > date_to:
            continue
        month_key = tx.date.strftime("%Y-%m")
        if month_key == current_month_key:
            continue
        by_month[month_key][tx.category or "other"] += tx.amount

    complete_months = sorted(by_month.keys())
    n = len(complete_months)
    if n == 0:
        return {"months_count": 0, "total_avg": 0.0, "categories": [], "date_from": date_from.isoformat(), "date_to": date_to.isoformat()}

    # Sum per category across all complete months
    cat_totals: dict = defaultdict(float)
    cat_month_counts: dict = defaultdict(int)
    for month_key in complete_months:
        for cat, amount in by_month[month_key].items():
            cat_totals[cat] += amount
            cat_month_counts[cat] += 1

    total_spend = sum(cat_totals.values())
    total_avg = round(total_spend / n, 2)

    categories = sorted(
        [
            {
                "category": cat,
                "avg": round(cat_totals[cat] / n, 2),
                "pct": round(cat_totals[cat] / total_spend * 100, 1) if total_spend > 0 else 0.0,
                "months_with_spend": cat_month_counts[cat],
            }
            for cat in cat_totals
        ],
        key=lambda x: -x["avg"],
    )

    return {
        "months_count": n,
        "total_avg": total_avg,
        "categories": categories,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }
```

Also add `date` to the imports at the top of `backend/analysis/insights.py` if not already present. The file already imports `from datetime import date` and `from collections import defaultdict` and `from typing import List` — no new imports needed.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/analysis/test_monthly_averages.py -v
```
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/analysis/insights.py tests/analysis/test_monthly_averages.py
git commit -m "feat: add get_monthly_averages() to insights"
```

---

### Task 2: Add `GET /analysis/monthly-averages` endpoint

**Files:**
- Modify: `backend/routes/analysis.py`

- [ ] **Step 1: Add the endpoint at the bottom of `backend/routes/analysis.py`**

```python
@router.get("/analysis/monthly-averages")
def get_monthly_averages_endpoint(
    months: int = 3,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    from backend.analysis.insights import get_monthly_averages

    today = date.today()

    # Resolve date range: custom dates take priority over months preset
    if date_from and date_to:
        try:
            from_date = date.fromisoformat(date_from)
            to_date = date.fromisoformat(date_to)
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        months = max(1, min(months, 60))
        from_date = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        # Go back `months` months from the start of current month
        year = today.year
        month = today.month - months
        while month <= 0:
            month += 12
            year -= 1
        from_date = date(year, month, 1)
        to_date = today

    with get_session() as session:
        all_txs = session.execute(select(Transaction)).scalars().all()
        spending_txs = [tx for tx in all_txs if not _is_payment(tx) and tx.amount > 0]

    return get_monthly_averages(spending_txs, date_from=from_date, date_to=to_date)
```

- [ ] **Step 2: Manually test the endpoint**

Start the backend if not running:
```bash
source .venv/bin/activate && uvicorn backend.main:app --reload
```

In another terminal:
```bash
# Preset: last 3 months
curl -s "http://localhost:8000/analysis/monthly-averages?months=3" | python3 -m json.tool

# Custom range
curl -s "http://localhost:8000/analysis/monthly-averages?date_from=2026-01-01&date_to=2026-04-30" | python3 -m json.tool
```

Expected: JSON with `months_count`, `total_avg`, `categories` array, `date_from`, `date_to`.

- [ ] **Step 3: Commit**

```bash
git add backend/routes/analysis.py
git commit -m "feat: add GET /analysis/monthly-averages endpoint"
```

---

### Task 3: Add Monthly Averages section to Insights page

**Files:**
- Modify: `frontend/src/pages/Insights.tsx`

- [ ] **Step 1: Read `frontend/src/pages/Insights.tsx`** to understand the existing structure. The file currently has sections for alerts, merchants, day-of-week, and year-over-year. The new section goes at the very bottom, just before the closing `</div>` of the outer container.

- [ ] **Step 2: Add state and fetch logic**

Find the top of the `Insights` component function (where `useState` / `useEffect` calls are). Add after the existing state variables:

```tsx
const [avgMonths, setAvgMonths] = useState<3 | 6 | 12>(3);
const [avgDateFrom, setAvgDateFrom] = useState("");
const [avgDateTo, setAvgDateTo] = useState("");
const [avgData, setAvgData] = useState<any>(null);
const [avgLoading, setAvgLoading] = useState(false);

useEffect(() => {
  setAvgLoading(true);
  const params = avgDateFrom && avgDateTo
    ? `date_from=${avgDateFrom}&date_to=${avgDateTo}`
    : `months=${avgMonths}`;
  fetch(`http://localhost:8000/analysis/monthly-averages?${params}`)
    .then((r) => r.json())
    .then(setAvgData)
    .finally(() => setAvgLoading(false));
}, [avgMonths, avgDateFrom, avgDateTo]);
```

- [ ] **Step 3: Add the section JSX**

Just before the final closing `</div>` of the return statement (after the year-over-year section), add:

```tsx
{/* Monthly Averages */}
<div style={{ marginTop: 32 }}>
  <div style={{ fontSize: 18, fontWeight: 700, color: "#fff", marginBottom: 16 }}>
    Average Monthly Spending
  </div>

  {/* Controls */}
  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 20, flexWrap: "wrap" }}>
    {([3, 6, 12] as const).map((m) => (
      <button
        key={m}
        onClick={() => { setAvgMonths(m); setAvgDateFrom(""); setAvgDateTo(""); }}
        style={{
          padding: "6px 16px", borderRadius: 8, border: "none", cursor: "pointer", fontSize: 13,
          background: avgMonths === m && !avgDateFrom ? "#7c6af7" : "#312e81",
          color: avgMonths === m && !avgDateFrom ? "#fff" : "#a5b4fc",
        }}
      >
        {m}M
      </button>
    ))}
    <span style={{ color: "#6b7280", fontSize: 13 }}>or</span>
    <input
      type="date"
      value={avgDateFrom}
      onChange={(e) => setAvgDateFrom(e.target.value)}
      style={{ background: "#312e81", border: "none", borderRadius: 8, padding: "6px 10px", color: "#e0e7ff", fontSize: 13 }}
    />
    <span style={{ color: "#6b7280", fontSize: 13 }}>–</span>
    <input
      type="date"
      value={avgDateTo}
      onChange={(e) => setAvgDateTo(e.target.value)}
      style={{ background: "#312e81", border: "none", borderRadius: 8, padding: "6px 10px", color: "#e0e7ff", fontSize: 13 }}
    />
  </div>

  {avgLoading && <div style={{ color: "#9ca3af", padding: 20 }}>Loading...</div>}

  {avgData && !avgLoading && (
    <>
      {/* Total average card */}
      <div style={{ background: "#1e1b4b", borderRadius: 12, padding: "20px 24px", marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 4 }}>Monthly average</div>
        <div style={{ fontSize: 32, fontWeight: 700, color: "#fff" }}>
          ${avgData.total_avg.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
        </div>
        <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 4 }}>
          avg over {avgData.months_count} complete month{avgData.months_count !== 1 ? "s" : ""}
          {avgData.months_count === 0 ? " — no complete months in range" : ` (${avgData.date_from} – ${avgData.date_to})`}
        </div>
      </div>

      {/* Per-category table */}
      {avgData.categories.length > 0 && (
        <div style={{ background: "#1e1b4b", borderRadius: 12, padding: "20px 24px" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ color: "#9ca3af", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                <th style={{ textAlign: "left", paddingBottom: 10, fontWeight: 600 }}>Category</th>
                <th style={{ textAlign: "right", paddingBottom: 10, fontWeight: 600 }}>Avg / month</th>
                <th style={{ textAlign: "right", paddingBottom: 10, fontWeight: 600 }}>% of total</th>
                <th style={{ textAlign: "right", paddingBottom: 10, fontWeight: 600 }}>Months with spend</th>
              </tr>
            </thead>
            <tbody>
              {avgData.categories.map((cat: any, i: number) => (
                <tr
                  key={cat.category}
                  onClick={() => {
                    const params = new URLSearchParams({ category: cat.category });
                    if (avgDateFrom) params.set("dateFrom", avgDateFrom);
                    if (avgDateTo) params.set("dateTo", avgDateTo);
                    window.location.href = `/transactions?${params.toString()}`;
                  }}
                  style={{
                    borderTop: "1px solid #312e81", cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#312e81")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                >
                  <td style={{ padding: "10px 0", color: "#e0e7ff", textTransform: "capitalize" }}>{cat.category}</td>
                  <td style={{ padding: "10px 0", textAlign: "right", color: "#c4b5fd", fontWeight: 600 }}>
                    ${cat.avg.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  </td>
                  <td style={{ padding: "10px 0", textAlign: "right", color: "#9ca3af" }}>{cat.pct}%</td>
                  <td style={{ padding: "10px 0", textAlign: "right", color: "#9ca3af" }}>
                    {cat.months_with_spend} / {avgData.months_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )}
</div>
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /Users/youssefaitousarrah/Documents/PersonalFinance/frontend && npx tsc --noEmit 2>&1
```
Expected: No errors.

- [ ] **Step 5: Verify it renders in the browser**

Start the app if not already running:
```bash
# Terminal 1
cd /Users/youssefaitousarrah/Documents/PersonalFinance && source .venv/bin/activate && uvicorn backend.main:app --reload

# Terminal 2
cd /Users/youssefaitousarrah/Documents/PersonalFinance/frontend && npm run dev
```

Open http://localhost:5173, navigate to Insights, scroll to the bottom. Verify:
- Three preset buttons (3M, 6M, 12M) and two date pickers visible
- Clicking a preset button loads data and shows the total average card and category table
- Setting custom from/to dates fetches with those dates
- Clicking a category row navigates to `/transactions?category=X`
- Active preset button is highlighted purple, others are dark

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Insights.tsx
git commit -m "feat: add average monthly spending section to Insights"
```

---

## Self-Review

**Spec coverage:**
- ✅ New section in Insights page → Task 3
- ✅ Preset buttons 3M/6M/12M → Task 3 step 3
- ✅ Custom date range pickers → Task 3 step 3
- ✅ Preset and custom mutually exclusive (setting custom clears preset highlight, picking preset clears custom dates) → Task 3 step 3
- ✅ Total avg/month card with "avg over N complete months" subtitle → Task 3 step 3
- ✅ Current partial month excluded → Task 1 (function skips `current_month_key`)
- ✅ Per-category table: category | avg/month | % of total | months with spend → Task 3 step 3
- ✅ Table sorted descending by avg → Task 1 (`key=lambda x: -x["avg"]`)
- ✅ Click category row navigates to transactions → Task 3 step 3
- ✅ `get_monthly_averages()` pure function → Task 1
- ✅ `GET /analysis/monthly-averages` endpoint → Task 2

**Placeholder scan:** None found.

**Type consistency:**
- `get_monthly_averages()` returns `{"months_count", "total_avg", "categories": [{"category", "avg", "pct", "months_with_spend"}], "date_from", "date_to"}`
- Frontend accesses `avgData.total_avg`, `avgData.months_count`, `avgData.categories`, `cat.category`, `cat.avg`, `cat.pct`, `cat.months_with_spend` — all match
- Endpoint parameter names (`months`, `date_from`, `date_to`) match frontend fetch URL construction — consistent
