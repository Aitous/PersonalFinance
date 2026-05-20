# LLM Transaction Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the LLM categorization call to also extract `merchant_name`, `city`, `is_online`, and `merchant_type` for each transaction using structured JSON output validated with Pydantic.

**Architecture:** Add `complete_json()` to both LLM providers (Gemini uses native JSON mode, Claude uses explicit JSON prompting). Update the Categorizer to return a `TransactionEnrichment` Pydantic model per transaction. Add four new columns to the `transactions` table. Update `SyncService` to persist all enrichment fields. Add a backfill endpoint to enrich existing transactions. Update the merchant breakdown to group by `merchant_name`.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, Pydantic v2, google-generativeai, anthropic SDK, React 18 + TypeScript

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `backend/db/models.py` | Add 4 new columns to Transaction |
| Modify | `backend/llm/base.py` | Add `complete_json` to protocol |
| Modify | `backend/llm/gemini_provider.py` | Implement `complete_json` with Gemini JSON mode |
| Modify | `backend/llm/claude_provider.py` | Implement `complete_json` with increased token limit |
| Modify | `backend/analysis/categorizer.py` | Pydantic model, new prompt, updated return type |
| Modify | `backend/sync_service.py` | Persist all enrichment fields |
| Modify | `backend/routes/import_csv.py` | Add `POST /import/enrich` backfill endpoint |
| Modify | `backend/analysis/insights.py` | Use `merchant_name` in breakdown |
| Modify | `frontend/src/api/client.ts` | Add `triggerEnrichment()` |
| Modify | `frontend/src/pages/Overview.tsx` | Add "Enrich" button next to Import |
| Create | `tests/test_categorizer.py` | Unit tests for enrichment |

---

## Task 1: DB schema — add enrichment columns

**Files:**
- Modify: `backend/db/models.py`

- [ ] **Step 1: Add the four columns to the Transaction model**

Open `backend/db/models.py`. Replace the Transaction class body with:

```python
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=True)
    merchant_name = Column(String, nullable=True)
    city = Column(String, nullable=True)
    is_online = Column(Boolean, nullable=True)
    merchant_type = Column(String, nullable=True)
    is_subscription = Column(Boolean, default=False)
    metadata_ = Column("metadata", Text, nullable=True)
    raw_csv_row = Column(Text, nullable=True)
    embedding = Column(Text, nullable=True)
```

- [ ] **Step 2: Run the DB migration**

SQLAlchemy doesn't auto-migrate. Run these ALTER TABLE statements against the existing `finance.db`:

```bash
cd /Users/youssefaitousarrah/Documents/PersonalFinance
source .venv/bin/activate
python3 - <<'EOF'
from backend.db.database import engine
with engine.connect() as conn:
    for col, typedef in [
        ("merchant_name", "TEXT"),
        ("city", "TEXT"),
        ("is_online", "BOOLEAN"),
        ("merchant_type", "TEXT"),
    ]:
        try:
            conn.execute(__import__("sqlalchemy").text(f"ALTER TABLE transactions ADD COLUMN {col} {typedef}"))
            conn.commit()
            print(f"Added {col}")
        except Exception as e:
            print(f"Skipped {col}: {e}")
EOF
```

Expected output:
```
Added merchant_name
Added city
Added is_online
Added merchant_type
```

- [ ] **Step 3: Verify columns exist**

```bash
python3 -c "
from backend.db.database import engine
import sqlalchemy as sa
insp = sa.inspect(engine)
cols = [c['name'] for c in insp.get_columns('transactions')]
print(cols)
assert 'merchant_name' in cols
assert 'city' in cols
assert 'is_online' in cols
assert 'merchant_type' in cols
print('OK')
"
```

Expected: prints column list and `OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/db/models.py
git commit -m "feat: add merchant_name, city, is_online, merchant_type columns to transactions"
```

---

## Task 2: Add `complete_json` to LLM providers

**Files:**
- Modify: `backend/llm/base.py`
- Modify: `backend/llm/gemini_provider.py`
- Modify: `backend/llm/claude_provider.py`

`complete_json(prompt)` returns a raw JSON string. The Categorizer (Task 3) owns parsing and validation — providers just guarantee they'll try their best to return valid JSON.

- [ ] **Step 1: Update the protocol**

Replace `backend/llm/base.py` entirely:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...
    def complete_json(self, prompt: str) -> str: ...
```

- [ ] **Step 2: Implement in GeminiProvider**

Gemini supports `response_mime_type="application/json"` natively — it forces the model to output valid JSON. Replace `backend/llm/gemini_provider.py` entirely:

```python
import google.generativeai as genai

class GeminiProvider:
    def __init__(self, model=None):
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._model.generate_content(prompt)
        return response.text

    def complete_json(self, prompt: str) -> str:
        response = self._model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
            ),
        )
        return response.text
```

- [ ] **Step 3: Implement in ClaudeProvider**

Claude doesn't have a JSON mode but reliably follows explicit JSON instructions. Increase `max_tokens` to 4096 for the larger structured responses. Replace `backend/llm/claude_provider.py` entirely:

```python
import anthropic

class ClaudeProvider:
    MODEL = "claude-sonnet-4-6"

    def __init__(self, client: anthropic.Anthropic):
        self._client = client

    def complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def complete_json(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
```

- [ ] **Step 4: Verify imports work**

```bash
cd /Users/youssefaitousarrah/Documents/PersonalFinance && source .venv/bin/activate
python3 -c "
from backend.llm.base import LLMProvider
from backend.llm.gemini_provider import GeminiProvider
from backend.llm.claude_provider import ClaudeProvider
print('GeminiProvider has complete_json:', hasattr(GeminiProvider, 'complete_json'))
print('ClaudeProvider has complete_json:', hasattr(ClaudeProvider, 'complete_json'))
print('OK')
"
```

Expected: both `True` and `OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/llm/base.py backend/llm/gemini_provider.py backend/llm/claude_provider.py
git commit -m "feat: add complete_json to LLM providers (Gemini JSON mode, Claude explicit JSON)"
```

---

## Task 3: Pydantic enrichment model + updated Categorizer

**Files:**
- Modify: `backend/analysis/categorizer.py`
- Create: `tests/test_categorizer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_categorizer.py`:

```python
import json
import pytest
from unittest.mock import MagicMock
from datetime import date
from backend.analysis.categorizer import Categorizer, TransactionEnrichment

def _make_tx(tx_id, description, amount=10.0):
    tx = MagicMock()
    tx.id = tx_id
    tx.description = description
    tx.amount = amount
    tx.date = date(2026, 1, 15)
    return tx

def _make_llm(json_response: str):
    llm = MagicMock()
    llm.complete_json.return_value = json_response
    return llm


def test_categorizer_returns_enrichment_model():
    txs = [_make_tx("abc", "TRADER JOE S #067 SAN MATEO", 45.0)]
    llm = _make_llm(json.dumps([{
        "id": "abc",
        "category": "groceries",
        "merchant_name": "Trader Joe's",
        "city": "San Mateo",
        "is_online": False,
        "merchant_type": "Grocery Store",
    }]))
    result = Categorizer(llm).categorize(txs)
    assert "abc" in result
    e = result["abc"]
    assert isinstance(e, TransactionEnrichment)
    assert e.category == "groceries"
    assert e.merchant_name == "Trader Joe's"
    assert e.city == "San Mateo"
    assert e.is_online is False
    assert e.merchant_type == "Grocery Store"


def test_categorizer_falls_back_on_invalid_json():
    txs = [_make_tx("abc", "SOME MERCHANT", 10.0)]
    llm = _make_llm("this is not json")
    result = Categorizer(llm).categorize(txs)
    assert result["abc"].category == "other"
    assert result["abc"].merchant_name == "SOME MERCHANT"


def test_categorizer_falls_back_on_invalid_category():
    txs = [_make_tx("abc", "NETFLIX", 15.99)]
    llm = _make_llm(json.dumps([{
        "id": "abc",
        "category": "made_up_category",
        "merchant_name": "Netflix",
        "city": None,
        "is_online": True,
        "merchant_type": "Streaming Service",
    }]))
    result = Categorizer(llm).categorize(txs)
    assert result["abc"].category == "other"
    assert result["abc"].merchant_name == "Netflix"


def test_categorizer_handles_missing_id_in_response():
    txs = [
        _make_tx("abc", "NETFLIX", 15.99),
        _make_tx("xyz", "TRADER JOE S", 45.0),
    ]
    # LLM only returns one of the two
    llm = _make_llm(json.dumps([{
        "id": "abc",
        "category": "subscriptions",
        "merchant_name": "Netflix",
        "city": None,
        "is_online": True,
        "merchant_type": "Streaming Service",
    }]))
    result = Categorizer(llm).categorize(txs)
    assert result["abc"].category == "subscriptions"
    assert result["xyz"].category == "other"
    assert result["xyz"].merchant_name == "TRADER JOE S"


def test_enrichment_model_validates_fields():
    e = TransactionEnrichment(
        id="x", category="dining", merchant_name="Chipotle",
        city="San Francisco", is_online=False, merchant_type="Fast Casual",
    )
    assert e.city == "San Francisco"
    # city is optional
    e2 = TransactionEnrichment(
        id="x", category="other", merchant_name="Unknown",
        city=None, is_online=False, merchant_type="Other",
    )
    assert e2.city is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/youssefaitousarrah/Documents/PersonalFinance && source .venv/bin/activate
python -m pytest tests/test_categorizer.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'TransactionEnrichment'`

- [ ] **Step 3: Rewrite `backend/analysis/categorizer.py`**

```python
import json
from typing import Dict, List, Optional
from pydantic import BaseModel
from backend.db.models import Transaction
from backend.llm.base import LLMProvider

VALID_CATEGORIES = {
    "dining", "groceries", "transport", "shopping",
    "entertainment", "subscriptions", "health", "travel",
    "utilities", "other",
}


class TransactionEnrichment(BaseModel):
    id: str
    category: str
    merchant_name: str
    city: Optional[str] = None
    is_online: bool
    merchant_type: str


ENRICH_PROMPT = """For each transaction below, return a JSON array where every element has exactly these fields:
- "id": the transaction id (string, copy exactly)
- "category": one of: dining, groceries, transport, shopping, entertainment, subscriptions, health, travel, utilities, other
  - dining: restaurants, cafes, bars, fast food, food delivery
  - groceries: supermarkets, grocery stores, food markets (Trader Joe's, Whole Foods, Costco food purchases)
  - transport: gas stations, Uber, Lyft, parking, public transit, tolls, auto services
  - shopping: retail, Amazon, clothing, electronics, home goods
  - entertainment: movies, concerts, games, sports events
  - subscriptions: recurring software/app charges (Google One, Strava, iCloud, Adobe), membership fees
  - health: pharmacies, doctors, gyms, dental, fitness, supplements
  - travel: flights, hotels, Airbnb, vacation rentals (only if clearly travel-related)
  - utilities: internet, phone, electricity, water, cable, insurance (GEICO, State Farm, etc.)
  - other: anything that doesn't fit above
- "merchant_name": clean canonical brand name (e.g. "Trader Joe's", "Costco", "Netflix", "Uber", "Chase Sapphire"). Strip store numbers, terminal codes, and location suffixes.
- "city": the city where the transaction occurred as a string, or null if not determinable from the description
- "is_online": true if this is an online/digital purchase, false if in-person
- "merchant_type": specific business type string, e.g. "Grocery Store", "Gas Station", "Streaming Service", "Ride Share", "Coffee Shop", "Warehouse Club", "Fast Casual Restaurant", "Airline", "Hotel", "Parking", "Pharmacy"

Return ONLY the raw JSON array. No markdown, no explanation, no code fences.

Transactions:
{transactions}"""


class Categorizer:
    BATCH_SIZE = 20

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def categorize(self, transactions: List[Transaction]) -> Dict[str, TransactionEnrichment]:
        if not transactions:
            return {}

        result: Dict[str, TransactionEnrichment] = {}

        for i in range(0, len(transactions), self.BATCH_SIZE):
            batch = transactions[i:i + self.BATCH_SIZE]
            tx_lines = "\n".join(
                f"{tx.id}: {tx.description} ${abs(tx.amount):.2f}"
                for tx in batch
            )
            prompt = ENRICH_PROMPT.format(transactions=tx_lines)

            try:
                raw = self._llm.complete_json(prompt)
                items = json.loads(raw)
                if not isinstance(items, list):
                    raise ValueError("Expected JSON array")
            except Exception:
                # If LLM call or JSON parse fails, fall back for entire batch
                for tx in batch:
                    result[tx.id] = _fallback(tx)
                continue

            parsed_ids = set()
            for item in items:
                try:
                    tx_id = item.get("id", "")
                    if item.get("category") not in VALID_CATEGORIES:
                        item["category"] = "other"
                    enrichment = TransactionEnrichment(**item)
                    result[enrichment.id] = enrichment
                    parsed_ids.add(enrichment.id)
                except Exception:
                    continue

            # Fall back for any transaction the LLM didn't return
            for tx in batch:
                if tx.id not in parsed_ids:
                    result[tx.id] = _fallback(tx)

        return result


def _fallback(tx: Transaction) -> TransactionEnrichment:
    return TransactionEnrichment(
        id=tx.id,
        category="other",
        merchant_name=tx.description,
        city=None,
        is_online=False,
        merchant_type="Other",
    )
```

- [ ] **Step 4: Run tests to verify they all pass**

```bash
cd /Users/youssefaitousarrah/Documents/PersonalFinance && source .venv/bin/activate
python -m pytest tests/test_categorizer.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/analysis/categorizer.py tests/test_categorizer.py
git commit -m "feat: Pydantic TransactionEnrichment model and structured JSON categorizer"
```

---

## Task 4: Update SyncService to persist enrichment fields

**Files:**
- Modify: `backend/sync_service.py`

`SyncService.categorize()` previously returned `Dict[str, str]` (id → category). It now returns `Dict[str, TransactionEnrichment]`. Update both `sync_bank` and `import_transactions` to write all five fields.

- [ ] **Step 1: Update both methods in `backend/sync_service.py`**

Replace both occurrences of the categorization block (in `sync_bank` and `import_transactions`). Find this pattern in each method:

```python
        if new_txs:
            categories = self._categorizer.categorize(new_txs)
            for tx in new_txs:
                tx.category = categories.get(tx.id, "other")
                self._session.add(tx)
```

Replace with (identical change in both methods):

```python
        if new_txs:
            enrichments = self._categorizer.categorize(new_txs)
            for tx in new_txs:
                enrich = enrichments.get(tx.id)
                if enrich:
                    tx.category = enrich.category
                    tx.merchant_name = enrich.merchant_name
                    tx.city = enrich.city
                    tx.is_online = enrich.is_online
                    tx.merchant_type = enrich.merchant_type
                else:
                    tx.category = "other"
                self._session.add(tx)
```

- [ ] **Step 2: Verify the module still imports cleanly**

```bash
cd /Users/youssefaitousarrah/Documents/PersonalFinance && source .venv/bin/activate
python3 -c "from backend.sync_service import SyncService; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/sync_service.py
git commit -m "feat: persist merchant_name, city, is_online, merchant_type during sync/import"
```

---

## Task 5: Backfill endpoint + frontend trigger

Existing transactions have `merchant_name = NULL`. This task adds `POST /import/enrich` to enrich them all, and a button in the frontend to trigger it.

**Files:**
- Modify: `backend/routes/import_csv.py`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/Overview.tsx`

- [ ] **Step 1: Add the backfill route to `backend/routes/import_csv.py`**

Add at the end of the file:

```python
@router.post("/import/enrich")
def enrich_existing(background_tasks: BackgroundTasks):
    """Enrich all transactions that are missing merchant_name."""
    from backend.analysis.categorizer import Categorizer
    from backend.llm.factory import get_llm_provider

    def _run():
        llm = get_llm_provider()
        categorizer = Categorizer(llm=llm)
        with get_session() as session:
            txs = session.execute(
                select(Transaction).where(Transaction.merchant_name.is_(None))
            ).scalars().all()
            session.expunge_all()

        if not txs:
            return

        enrichments = categorizer.categorize(list(txs))

        with get_session() as session:
            for tx_id, enrich in enrichments.items():
                tx = session.get(Transaction, tx_id)
                if tx:
                    tx.merchant_name = enrich.merchant_name
                    tx.city = enrich.city
                    tx.is_online = enrich.is_online
                    tx.merchant_type = enrich.merchant_type
                    # Only overwrite category if it was already 'other' or unset
                    if not tx.category or tx.category == "other":
                        tx.category = enrich.category
            session.commit()

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Enriching transactions in background"}
```

Also add `BackgroundTasks` to the import at the top of the file. The current imports line is:
```python
from fastapi import APIRouter, HTTPException
```
Replace with:
```python
from fastapi import APIRouter, BackgroundTasks, HTTPException
```

Also add the missing `select` and `Transaction` imports if not present. Check the top of the file and add:
```python
from sqlalchemy import select
from backend.db.models import Transaction
from backend.db.database import get_session
```

- [ ] **Step 2: Test the endpoint responds**

With the backend running (`uvicorn backend.main:app --reload`):

```bash
curl -s -X POST http://localhost:8000/import/enrich | python3 -m json.tool
```

Expected:
```json
{"status": "started", "message": "Enriching transactions in background"}
```

- [ ] **Step 3: Add `triggerEnrichment` to the API client**

In `frontend/src/api/client.ts`, add at the end:

```typescript
export const triggerEnrichment = () =>
  api.post("/import/enrich").then((r) => r.data);
```

- [ ] **Step 4: Add the "Enrich" button to Overview.tsx**

In `frontend/src/pages/Overview.tsx`, import `triggerEnrichment`:

```typescript
import { getOverview, triggerSync, getConfiguredBanks, importFromFolder, uploadCSV, triggerEnrichment } from "../api/client";
```

Add `enriching` and `enrichMsg` state after the existing state declarations:

```typescript
const [enriching, setEnriching] = useState(false);
const [enrichMsg, setEnrichMsg] = useState<string | null>(null);
```

Add the handler after `handleFileUpload`:

```typescript
const handleEnrich = async () => {
  setEnriching(true);
  setEnrichMsg(null);
  try {
    await triggerEnrichment();
    setEnrichMsg("Enrichment started in background — merchant names, cities, and types will appear shortly.");
  } catch (e: any) {
    setEnrichMsg(`Enrichment failed: ${e?.response?.data?.detail ?? e.message}`);
  } finally {
    setEnriching(false);
  }
};
```

Add the button in the import section, after the "Choose file" label and before the closing `</div>` of the import controls row:

```tsx
<button onClick={handleEnrich} disabled={enriching} style={{
  background: "#10b981", color: "#fff", border: "none",
  borderRadius: 8, padding: "7px 16px", cursor: "pointer", fontSize: 13,
}}>
  {enriching ? "Starting…" : "Enrich with AI"}
</button>
```

Display `enrichMsg` below the existing `importMsg`:

```tsx
{enrichMsg && (
  <div style={{ marginTop: 6, fontSize: 13, color: enrichMsg.startsWith("Enrichment started") ? "#0a0" : "#e05" }}>
    {enrichMsg}
  </div>
)}
```

- [ ] **Step 5: Commit**

```bash
git add backend/routes/import_csv.py frontend/src/api/client.ts frontend/src/pages/Overview.tsx
git commit -m "feat: add /import/enrich backfill endpoint and Enrich with AI button"
```

---

## Task 6: Use `merchant_name` in the merchant breakdown

**Files:**
- Modify: `backend/analysis/insights.py`

Replace the `_normalize_merchant` regex grouping with a DB-backed grouping: if `merchant_name` is set, use it; otherwise fall back to `_normalize_merchant(description)`.

- [ ] **Step 1: Update `get_merchant_breakdown` in `backend/analysis/insights.py`**

Find and replace the `get_merchant_breakdown` function:

```python
def get_merchant_breakdown(txs: List[Transaction]) -> List[dict]:
    groups: dict = defaultdict(list)
    for tx in txs:
        # Use LLM-extracted name if available, otherwise fall back to regex normalization
        key = tx.merchant_name if tx.merchant_name else _normalize_merchant(tx.description)
        groups[key].append(tx)

    merchants = []
    for name, merchant_txs in groups.items():
        total = sum(t.amount for t in merchant_txs)
        last_date = max(t.date for t in merchant_txs)
        cat_counts: dict = defaultdict(int)
        for t in merchant_txs:
            cat_counts[t.category or "other"] += 1
        top_cat = max(cat_counts, key=lambda k: cat_counts[k])
        # Use the most common merchant_type if enriched
        type_counts: dict = defaultdict(int)
        for t in merchant_txs:
            if t.merchant_type:
                type_counts[t.merchant_type] += 1
        top_type = max(type_counts, key=lambda k: type_counts[k]) if type_counts else None
        merchants.append({
            "name": name,
            "total": round(total, 2),
            "tx_count": len(merchant_txs),
            "category": top_cat,
            "merchant_type": top_type,
            "last_date": last_date.isoformat(),
        })

    return sorted(merchants, key=lambda x: -x["total"])
```

- [ ] **Step 2: Verify backend still responds**

```bash
curl -s "http://localhost:8000/analysis/insights?merchant_days=90" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for m in d['merchants'][:5]:
    print(m['name'], '-', m.get('merchant_type'), '-', m['tx_count'], 'txns', '\$' + str(m['total']))
"
```

Expected: top 5 merchants printed, no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/analysis/insights.py
git commit -m "feat: merchant breakdown uses LLM merchant_name with regex fallback"
```
