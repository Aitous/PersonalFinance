# Personal Finance App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local personal finance app that downloads transactions from Chase, Discover, and Amex via Playwright, stores them in SQLite, and serves a React dashboard with expense categories, trend charts, subscription detection, and AI-powered saving tips.

**Architecture:** Python FastAPI backend handles all scraping, analysis, and LLM calls; React frontend communicates via REST API; credentials live exclusively in macOS Keychain; transactions persist in a local SQLite database.

**Tech Stack:** Python 3.11+, FastAPI, Playwright (Python), SQLAlchemy, SQLite, `keyring`, Anthropic SDK, `google-generativeai`, React 18, TypeScript, Recharts, Vite.

---

## Task Group Overview

| Group | Tasks | What it produces |
|-------|-------|-----------------|
| A — Foundation | 1–3 | Project scaffold, DB models, credentials store |
| B — Analysis Engine | 4–7 | LLM providers, categorizer, subscription detector, savings advisor |
| C — Scrapers | 8–11 | BaseScraper, CSV parsers, Chase/Discover/Amex scrapers |
| D — API | 12 | All FastAPI routes wired together |
| E — Frontend | 13–19 | React app: sidebar, all 6 pages, charts |

---

## Task 1: Project Scaffold

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/main.py`
- Create: `frontend/` (Vite React TypeScript app)
- Create: `config.json`
- Create: `.gitignore`

- [ ] **Step 1: Create the root `.gitignore`**

```
# Python
__pycache__/
*.pyc
.venv/
*.egg-info/

# Database
finance.db

# Superpowers
.superpowers/

# Frontend
frontend/node_modules/
frontend/dist/

# Environment
.env
```

- [ ] **Step 2: Create `config.json`**

```json
{
  "llm_provider": "claude",
  "default_sync_days": 90
}
```

- [ ] **Step 3: Create Python virtual environment and `backend/requirements.txt`**

Run:
```bash
cd ~/Documents/PersonalFinance
python3 -m venv .venv
source .venv/bin/activate
```

Create `backend/requirements.txt`:
```
fastapi==0.111.0
uvicorn[standard]==0.30.1
sqlalchemy==2.0.30
playwright==1.44.0
keyring==25.2.1
anthropic==0.28.0
google-generativeai==0.7.2
pandas==2.2.2
pytest==8.2.2
pytest-asyncio==0.23.7
httpx==0.27.0
```

Run:
```bash
pip install -r backend/requirements.txt
playwright install chromium
```

- [ ] **Step 4: Scaffold the React frontend with Vite**

Run:
```bash
cd ~/Documents/PersonalFinance
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install recharts axios react-router-dom @types/react-router-dom
```

- [ ] **Step 5: Create minimal `backend/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PersonalFinance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Verify backend starts**

Run:
```bash
cd ~/Documents/PersonalFinance
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

Expected: `Application startup complete.`  
Visit `http://localhost:8000/health` — should return `{"status":"ok"}`

- [ ] **Step 7: Verify frontend starts**

Run (new terminal):
```bash
cd ~/Documents/PersonalFinance/frontend
npm run dev
```

Expected: `Local: http://localhost:5173`

- [ ] **Step 8: Commit**

```bash
git init
git add .gitignore config.json backend/requirements.txt backend/main.py frontend/
git commit -m "feat: project scaffold — FastAPI backend + React frontend"
```

---

## Task 2: Database Models

**Files:**
- Create: `backend/db/database.py`
- Create: `backend/db/models.py`
- Create: `tests/db/test_models.py`

- [ ] **Step 1: Write failing tests**

Create `tests/db/test_models.py`:
```python
import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.db.models import Base, Transaction, Subscription, Sync

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_create_transaction(db):
    tx = Transaction(
        id="abc123",
        source="chase",
        date=date(2025, 5, 1),
        description="WHOLE FOODS",
        amount=-84.20,
        category="groceries",
        is_subscription=False,
    )
    db.add(tx)
    db.commit()
    result = db.get(Transaction, "abc123")
    assert result.description == "WHOLE FOODS"
    assert result.amount == -84.20

def test_create_subscription(db):
    sub = Subscription(
        id="sub1",
        description="NETFLIX.COM",
        amount=15.99,
        frequency="monthly",
        last_charged=date(2025, 5, 1),
        active=True,
    )
    db.add(sub)
    db.commit()
    result = db.get(Subscription, "sub1")
    assert result.frequency == "monthly"

def test_create_sync(db):
    sync = Sync(
        source="chase",
        synced_at="2025-05-01T10:00:00",
        from_date=date(2025, 1, 1),
        to_date=date(2025, 5, 1),
        tx_count=42,
    )
    db.add(sync)
    db.commit()
    assert sync.id is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/Documents/PersonalFinance
source .venv/bin/activate
pytest tests/db/test_models.py -v
```

Expected: `ImportError` or `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/db/__init__.py`**

```python
```
(empty file)

- [ ] **Step 4: Create `backend/db/models.py`**

```python
from datetime import date, datetime
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True)  # hash of source+date+amount+description
    source = Column(String, nullable=False)  # 'chase' | 'discover' | 'amex'
    date = Column(Date, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)  # negative=expense, positive=credit
    category = Column(String, nullable=True)
    is_subscription = Column(Boolean, default=False)
    metadata_ = Column("metadata", Text, nullable=True)  # JSON blob
    raw_csv_row = Column(Text, nullable=True)

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    frequency = Column(String, nullable=False)  # 'monthly' | 'annual'
    last_charged = Column(Date, nullable=True)
    active = Column(Boolean, default=True)

class Sync(Base):
    __tablename__ = "syncs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    tx_count = Column(Integer, nullable=False)
```

- [ ] **Step 5: Create `backend/db/database.py`**

```python
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.db.models import Base

DB_PATH = Path(__file__).parent.parent.parent / "finance.db"

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)

SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

def get_session() -> Session:
    return SessionLocal()
```

- [ ] **Step 6: Create `backend/__init__.py`**

```python
```
(empty file)

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/db/test_models.py -v
```

Expected: 3 tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/db/ tests/db/
git commit -m "feat: SQLAlchemy models for transactions, subscriptions, syncs"
```

---

## Task 3: Credentials Store

**Files:**
- Create: `backend/credentials.py`
- Create: `tests/test_credentials.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_credentials.py`:
```python
import pytest
from unittest.mock import patch, call
from backend.credentials import CredentialsStore

def test_save_and_get_bank_credential():
    store = CredentialsStore()
    with patch("keyring.set_password") as mock_set, \
         patch("keyring.get_password", return_value="mypassword"):
        store.save_bank_credential("chase", "username", "myuser")
        store.save_bank_credential("chase", "password", "mypassword")
        pwd = store.get_bank_credential("chase", "password")
        assert pwd == "mypassword"

def test_save_and_get_llm_api_key():
    store = CredentialsStore()
    with patch("keyring.set_password") as mock_set, \
         patch("keyring.get_password", return_value="sk-ant-abc123"):
        store.save_llm_key("claude", "sk-ant-abc123")
        key = store.get_llm_key("claude")
        assert key == "sk-ant-abc123"

def test_missing_credential_returns_none():
    store = CredentialsStore()
    with patch("keyring.get_password", return_value=None):
        result = store.get_bank_credential("chase", "password")
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_credentials.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create `backend/credentials.py`**

```python
import keyring
from typing import Optional

SERVICE_PREFIX = "PersonalFinanceApp"

class CredentialsStore:
    def save_bank_credential(self, bank: str, field: str, value: str) -> None:
        keyring.set_password(SERVICE_PREFIX, f"{bank}:{field}", value)

    def get_bank_credential(self, bank: str, field: str) -> Optional[str]:
        return keyring.get_password(SERVICE_PREFIX, f"{bank}:{field}")

    def save_llm_key(self, provider: str, api_key: str) -> None:
        keyring.set_password(SERVICE_PREFIX, f"llm:{provider}", api_key)

    def get_llm_key(self, provider: str) -> Optional[str]:
        return keyring.get_password(SERVICE_PREFIX, f"llm:{provider}")

credentials_store = CredentialsStore()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_credentials.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/credentials.py tests/test_credentials.py
git commit -m "feat: credentials store backed by macOS Keychain"
```

---

## Task 4: LLM Provider Abstraction + Claude Provider

**Files:**
- Create: `backend/llm/__init__.py`
- Create: `backend/llm/base.py`
- Create: `backend/llm/claude_provider.py`
- Create: `backend/llm/gemini_provider.py`
- Create: `backend/llm/factory.py`
- Create: `tests/llm/test_providers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/llm/test_providers.py`:
```python
import pytest
from unittest.mock import MagicMock, patch
from backend.llm.claude_provider import ClaudeProvider
from backend.llm.gemini_provider import GeminiProvider
from backend.llm.factory import get_llm_provider

def test_claude_provider_calls_api():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="groceries")]
    )
    provider = ClaudeProvider(client=mock_client)
    result = provider.complete("Categorize: WHOLE FOODS $84")
    assert result == "groceries"
    mock_client.messages.create.assert_called_once()

def test_gemini_provider_calls_api():
    mock_model = MagicMock()
    mock_model.generate_content.return_value = MagicMock(text="dining")
    provider = GeminiProvider(model=mock_model)
    result = provider.complete("Categorize: UBER EATS $32")
    assert result == "dining"

def test_factory_returns_claude(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"llm_provider": "claude"}')
    with patch("backend.llm.factory.CONFIG_PATH", config), \
         patch("backend.llm.factory.credentials_store") as mock_creds, \
         patch("backend.llm.factory.anthropic.Anthropic") as mock_anthropic:
        mock_creds.get_llm_key.return_value = "sk-ant-test"
        provider = get_llm_provider()
        assert isinstance(provider, ClaudeProvider)

def test_factory_returns_gemini(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"llm_provider": "gemini"}')
    with patch("backend.llm.factory.CONFIG_PATH", config), \
         patch("backend.llm.factory.credentials_store") as mock_creds, \
         patch("backend.llm.factory.genai.GenerativeModel") as mock_genai, \
         patch("backend.llm.factory.genai.configure"):
        mock_creds.get_llm_key.return_value = "AIza-test"
        provider = get_llm_provider()
        assert isinstance(provider, GeminiProvider)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/llm/test_providers.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create `backend/llm/__init__.py`**

```python
```
(empty)

- [ ] **Step 4: Create `backend/llm/base.py`**

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...
```

- [ ] **Step 5: Create `backend/llm/claude_provider.py`**

```python
import anthropic
from backend.llm.base import LLMProvider

class ClaudeProvider:
    MODEL = "claude-sonnet-4-6"

    def __init__(self, client: anthropic.Anthropic = None):
        self._client = client

    def complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
```

- [ ] **Step 6: Create `backend/llm/gemini_provider.py`**

```python
import google.generativeai as genai

class GeminiProvider:
    def __init__(self, model=None):
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._model.generate_content(prompt)
        return response.text
```

- [ ] **Step 7: Create `backend/llm/factory.py`**

```python
import json
from pathlib import Path
import anthropic
import google.generativeai as genai
from backend.credentials import credentials_store
from backend.llm.claude_provider import ClaudeProvider
from backend.llm.gemini_provider import GeminiProvider

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"

def get_llm_provider():
    config = json.loads(CONFIG_PATH.read_text())
    provider_name = config.get("llm_provider", "claude")

    if provider_name == "claude":
        api_key = credentials_store.get_llm_key("claude")
        client = anthropic.Anthropic(api_key=api_key)
        return ClaudeProvider(client=client)

    if provider_name == "gemini":
        api_key = credentials_store.get_llm_key("gemini")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        return GeminiProvider(model=model)

    raise ValueError(f"Unknown LLM provider: {provider_name}")
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
pytest tests/llm/test_providers.py -v
```

Expected: 4 tests PASS

- [ ] **Step 9: Commit**

```bash
git add backend/llm/ tests/llm/
git commit -m "feat: LLM provider abstraction with Claude and Gemini backends"
```

---

## Task 5: Categorizer

**Files:**
- Create: `backend/analysis/__init__.py`
- Create: `backend/analysis/categorizer.py`
- Create: `tests/analysis/test_categorizer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/analysis/test_categorizer.py`:
```python
import pytest
from unittest.mock import MagicMock
from datetime import date
from backend.analysis.categorizer import Categorizer, VALID_CATEGORIES
from backend.db.models import Transaction

def make_tx(id, description, amount):
    return Transaction(
        id=id, source="chase", date=date(2025, 5, 1),
        description=description, amount=amount
    )

def test_categorizes_batch_of_transactions():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = (
        "tx1: groceries\ntx2: dining\ntx3: subscriptions"
    )
    categorizer = Categorizer(llm=mock_llm)
    txs = [
        make_tx("tx1", "WHOLE FOODS", -84.20),
        make_tx("tx2", "UBER EATS", -32.50),
        make_tx("tx3", "NETFLIX.COM", -15.99),
    ]
    result = categorizer.categorize(txs)
    assert result["tx1"] == "groceries"
    assert result["tx2"] == "dining"
    assert result["tx3"] == "subscriptions"

def test_falls_back_to_other_for_unknown_category():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "tx1: banana_stuff"
    categorizer = Categorizer(llm=mock_llm)
    txs = [make_tx("tx1", "RANDOM MERCHANT", -10.00)]
    result = categorizer.categorize(txs)
    assert result["tx1"] == "other"

def test_empty_list_returns_empty_dict():
    mock_llm = MagicMock()
    categorizer = Categorizer(llm=mock_llm)
    result = categorizer.categorize([])
    assert result == {}
    mock_llm.complete.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/analysis/test_categorizer.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create `backend/analysis/__init__.py`**

```python
```
(empty)

- [ ] **Step 4: Create `backend/analysis/categorizer.py`**

```python
from typing import Dict, List
from backend.db.models import Transaction
from backend.llm.base import LLMProvider

VALID_CATEGORIES = {
    "dining", "groceries", "transport", "shopping",
    "entertainment", "subscriptions", "health", "travel",
    "utilities", "other",
}

CATEGORIZE_PROMPT = """Categorize each transaction below into exactly one of these categories:
dining, groceries, transport, shopping, entertainment, subscriptions, health, travel, utilities, other

Return one line per transaction in the format: <id>: <category>
Only return the lines, nothing else.

Transactions:
{transactions}"""

class Categorizer:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def categorize(self, transactions: List[Transaction]) -> Dict[str, str]:
        if not transactions:
            return {}

        tx_lines = "\n".join(
            f"{tx.id}: {tx.description} ${abs(tx.amount):.2f}"
            for tx in transactions
        )
        prompt = CATEGORIZE_PROMPT.format(transactions=tx_lines)
        response = self._llm.complete(prompt)

        result: Dict[str, str] = {}
        for line in response.strip().splitlines():
            if ":" not in line:
                continue
            tx_id, _, category = line.partition(":")
            category = category.strip().lower()
            result[tx_id.strip()] = category if category in VALID_CATEGORIES else "other"

        return result
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/analysis/test_categorizer.py -v
```

Expected: 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/analysis/ tests/analysis/
git commit -m "feat: LLM-powered transaction categorizer with batch prompting"
```

---

## Task 6: Subscription Detector

**Files:**
- Modify: `backend/analysis/` (add `subscription_detector.py`)
- Create: `tests/analysis/test_subscription_detector.py`

- [ ] **Step 1: Write failing tests**

Create `tests/analysis/test_subscription_detector.py`:
```python
import pytest
from datetime import date
from backend.analysis.subscription_detector import SubscriptionDetector
from backend.db.models import Transaction

def make_tx(id, description, amount, tx_date):
    return Transaction(
        id=id, source="chase", date=tx_date,
        description=description, amount=amount
    )

def test_detects_monthly_subscription():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "NETFLIX.COM", -15.99, date(2025, 3, 15)),
        make_tx("t2", "NETFLIX.COM", -15.99, date(2025, 4, 15)),
        make_tx("t3", "NETFLIX.COM", -15.99, date(2025, 5, 15)),
    ]
    subs = detector.detect(txs)
    assert len(subs) == 1
    assert subs[0].description == "NETFLIX.COM"
    assert subs[0].frequency == "monthly"
    assert subs[0].amount == 15.99

def test_detects_annual_subscription():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "AMAZON PRIME", -139.00, date(2024, 5, 1)),
        make_tx("t2", "AMAZON PRIME", -139.00, date(2025, 5, 1)),
    ]
    subs = detector.detect(txs)
    assert len(subs) == 1
    assert subs[0].frequency == "annual"

def test_ignores_non_recurring():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "RANDOM STORE", -50.00, date(2025, 3, 1)),
        make_tx("t2", "ANOTHER STORE", -75.00, date(2025, 4, 15)),
    ]
    subs = detector.detect(txs)
    assert subs == []

def test_amount_tolerance():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "SPOTIFY", -10.99, date(2025, 3, 5)),
        make_tx("t2", "SPOTIFY", -10.99, date(2025, 4, 5)),
        make_tx("t3", "SPOTIFY", -11.49, date(2025, 5, 5)),  # tax variation
    ]
    subs = detector.detect(txs)
    assert len(subs) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/analysis/test_subscription_detector.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create `backend/analysis/subscription_detector.py`**

```python
import hashlib
from collections import defaultdict
from datetime import date
from typing import List
from backend.db.models import Subscription, Transaction

AMOUNT_TOLERANCE = 1.00  # dollars
MONTHLY_DAYS_MIN, MONTHLY_DAYS_MAX = 25, 35
ANNUAL_DAYS_MIN, ANNUAL_DAYS_MAX = 350, 380

class SubscriptionDetector:
    def detect(self, transactions: List[Transaction]) -> List[Subscription]:
        expenses = [tx for tx in transactions if tx.amount < 0]
        groups: dict[str, list[Transaction]] = defaultdict(list)
        for tx in expenses:
            groups[tx.description.upper()].append(tx)

        subscriptions: List[Subscription] = []
        for description, txs in groups.items():
            if len(txs) < 2:
                continue
            txs_sorted = sorted(txs, key=lambda t: t.date)
            frequency = self._detect_frequency(txs_sorted)
            if frequency is None:
                continue
            base_amount = abs(txs_sorted[-1].amount)
            sub_id = hashlib.md5(description.encode()).hexdigest()
            subscriptions.append(Subscription(
                id=sub_id,
                description=description,
                amount=base_amount,
                frequency=frequency,
                last_charged=txs_sorted[-1].date,
                active=True,
            ))
        return subscriptions

    def _detect_frequency(self, txs: List[Transaction]):
        if len(txs) < 2:
            return None
        amounts = [abs(tx.amount) for tx in txs]
        if max(amounts) - min(amounts) > AMOUNT_TOLERANCE:
            return None

        gaps = [
            (txs[i + 1].date - txs[i].date).days
            for i in range(len(txs) - 1)
        ]
        avg_gap = sum(gaps) / len(gaps)

        if MONTHLY_DAYS_MIN <= avg_gap <= MONTHLY_DAYS_MAX:
            return "monthly"
        if ANNUAL_DAYS_MIN <= avg_gap <= ANNUAL_DAYS_MAX:
            return "annual"
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/analysis/test_subscription_detector.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/analysis/subscription_detector.py tests/analysis/test_subscription_detector.py
git commit -m "feat: subscription detector — identifies recurring charges by interval"
```

---

## Task 7: Savings Advisor

**Files:**
- Modify: `backend/analysis/` (add `savings_advisor.py`)
- Create: `tests/analysis/test_savings_advisor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/analysis/test_savings_advisor.py`:
```python
import pytest
from unittest.mock import MagicMock
from backend.analysis.savings_advisor import SavingsAdvisor

def test_generates_tips_from_category_summary():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = (
        "1. Cut dining by cooking at home twice a week.\n"
        "2. Rotate streaming services instead of running all at once."
    )
    advisor = SavingsAdvisor(llm=mock_llm)
    summary = {
        "dining": {"total": 847, "avg_monthly": 282},
        "subscriptions": {"total": 312, "count": 8},
    }
    tips = advisor.get_tips(summary, period="Feb–Apr 2025")
    assert len(tips) == 2
    assert "dining" in tips[0].lower()
    mock_llm.complete.assert_called_once()

def test_prompt_contains_category_data():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "1. Save more."
    advisor = SavingsAdvisor(llm=mock_llm)
    summary = {"groceries": {"total": 500, "avg_monthly": 166}}
    advisor.get_tips(summary, period="Q1 2025")
    prompt_used = mock_llm.complete.call_args[0][0]
    assert "groceries" in prompt_used
    assert "500" in prompt_used
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/analysis/test_savings_advisor.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create `backend/analysis/savings_advisor.py`**

```python
import json
from typing import Dict, List
from backend.llm.base import LLMProvider

SAVINGS_PROMPT = """You are a personal finance advisor. Based on the spending summary below, 
provide 3-5 specific, actionable saving tips. Be concrete — reference actual numbers.

Period: {period}

Spending by category (USD):
{categories}

Return a numbered list only. No preamble or closing remarks."""

class SavingsAdvisor:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def get_tips(self, category_summary: Dict, period: str) -> List[str]:
        categories_text = "\n".join(
            f"- {cat}: ${data['total']:.0f} total"
            + (f", ${data['avg_monthly']:.0f}/mo avg" if "avg_monthly" in data else "")
            + (f", {data['count']} services" if "count" in data else "")
            for cat, data in category_summary.items()
        )
        prompt = SAVINGS_PROMPT.format(period=period, categories=categories_text)
        response = self._llm.complete(prompt)

        tips = []
        for line in response.strip().splitlines():
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                cleaned = line.lstrip("0123456789.-) ").strip()
                if cleaned:
                    tips.append(cleaned)
        return tips
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/analysis/test_savings_advisor.py -v
```

Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/analysis/savings_advisor.py tests/analysis/test_savings_advisor.py
git commit -m "feat: savings advisor generates AI-powered tips from category spend summary"
```

---

## Task 8: CSV Parser

**Files:**
- Create: `backend/parsers/__init__.py`
- Create: `backend/parsers/csv_parser.py`
- Create: `tests/parsers/test_csv_parser.py`
- Create: `tests/parsers/fixtures/chase_sample.csv`
- Create: `tests/parsers/fixtures/discover_sample.csv`
- Create: `tests/parsers/fixtures/amex_sample.csv`

- [ ] **Step 1: Create fixture CSV files**

Create `tests/parsers/fixtures/chase_sample.csv`:
```
Transaction Date,Post Date,Description,Category,Type,Amount,Memo
05/14/2025,05/15/2025,WHOLE FOODS #123,Groceries,Sale,-84.20,
05/13/2025,05/14/2025,NETFLIX.COM,Entertainment,Sale,-15.99,
05/12/2025,05/13/2025,PAYROLL DEPOSIT,Paycheck,Payment,3200.00,
```

Create `tests/parsers/fixtures/discover_sample.csv`:
```
Trans. Date,Post Date,Description,Amount,Category
05/14/2025,05/15/2025,UBER EATS,-32.50,Restaurants
05/13/2025,05/14/2025,SPOTIFY,-9.99,Music
05/12/2025,05/13/2025,CASHBACK BONUS,20.00,Rewards
```

Create `tests/parsers/fixtures/amex_sample.csv`:
```
Date,Description,Amount,Extended Details,Appears On Your Statement As,Address,City/State,Zip Code,Country,Reference,Category
05/14/2025,DELTA AIR LINES,-420.00,,DELTA AIR LINES,,,,USA,,Travel
05/13/2025,STARBUCKS,-6.75,,STARBUCKS,,,,USA,,Dining
```

- [ ] **Step 2: Write failing tests**

Create `tests/parsers/test_csv_parser.py`:
```python
import pytest
from pathlib import Path
from backend.parsers.csv_parser import parse_csv

FIXTURES = Path(__file__).parent / "fixtures"

def test_parse_chase_csv():
    txs = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    expenses = [t for t in txs if t.amount < 0]
    assert len(expenses) == 2
    assert expenses[0].description == "WHOLE FOODS #123"
    assert expenses[0].amount == -84.20
    assert expenses[0].source == "chase"

def test_parse_discover_csv():
    txs = parse_csv(FIXTURES / "discover_sample.csv", source="discover")
    expenses = [t for t in txs if t.amount < 0]
    assert len(expenses) == 2
    assert expenses[0].description == "UBER EATS"
    assert expenses[0].amount == -32.50

def test_parse_amex_csv():
    txs = parse_csv(FIXTURES / "amex_sample.csv", source="amex")
    assert len(txs) == 2
    assert txs[0].description == "DELTA AIR LINES"
    assert txs[0].amount == -420.00

def test_transaction_id_is_deterministic():
    txs1 = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    txs2 = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    assert txs1[0].id == txs2[0].id

def test_transaction_id_is_unique_per_transaction():
    txs = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    ids = [t.id for t in txs]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/parsers/test_csv_parser.py -v
```

Expected: `ImportError`

- [ ] **Step 4: Create `backend/parsers/__init__.py`**

```python
```
(empty)

- [ ] **Step 5: Create `backend/parsers/csv_parser.py`**

```python
import csv
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import List
from backend.db.models import Transaction

# Column mappings per bank: (date_col, description_col, amount_col, date_fmt)
BANK_SCHEMAS = {
    "chase": {
        "date_col": "Transaction Date",
        "description_col": "Description",
        "amount_col": "Amount",
        "date_fmt": "%m/%d/%Y",
        "extra_cols": ["Category", "Type", "Memo"],
    },
    "discover": {
        "date_col": "Trans. Date",
        "description_col": "Description",
        "amount_col": "Amount",
        "date_fmt": "%m/%d/%Y",
        "extra_cols": ["Category"],
    },
    "amex": {
        "date_col": "Date",
        "description_col": "Description",
        "amount_col": "Amount",
        "date_fmt": "%m/%d/%Y",
        "extra_cols": ["Category", "City/State", "Country"],
    },
}

def _make_id(source: str, tx_date: date, description: str, amount: float) -> str:
    raw = f"{source}:{tx_date.isoformat()}:{description}:{amount:.2f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def parse_csv(file_path: Path, source: str) -> List[Transaction]:
    schema = BANK_SCHEMAS[source]
    transactions: List[Transaction] = []

    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_date = row[schema["date_col"]].strip()
            description = row[schema["description_col"]].strip()
            amount_str = row[schema["amount_col"]].strip().replace(",", "")

            try:
                tx_date = datetime.strptime(raw_date, schema["date_fmt"]).date()
                amount = float(amount_str)
            except (ValueError, KeyError):
                continue

            metadata = {
                col: row.get(col, "").strip()
                for col in schema["extra_cols"]
                if row.get(col, "").strip()
            }

            transactions.append(Transaction(
                id=_make_id(source, tx_date, description, amount),
                source=source,
                date=tx_date,
                description=description,
                amount=amount,
                metadata_=json.dumps(metadata) if metadata else None,
                raw_csv_row=json.dumps(dict(row)),
            ))

    return transactions
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/parsers/test_csv_parser.py -v
```

Expected: 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/parsers/ tests/parsers/
git commit -m "feat: CSV parser with Chase, Discover, Amex normalization"
```

---

## Task 9: BaseScraper with Security Constraints

**Files:**
- Create: `backend/scrapers/__init__.py`
- Create: `backend/scrapers/base.py`
- Create: `tests/scrapers/test_base_scraper.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scrapers/test_base_scraper.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.scrapers.base import BaseScraper

class DummyScraper(BaseScraper):
    ALLOWED_DOMAINS = ["example.com"]
    SOURCE = "dummy"

    async def login(self): pass
    async def download_transactions(self, since): return None
    async def logout(self): pass

def test_is_allowed_domain():
    scraper = DummyScraper(username="u", password="p")
    assert scraper._is_allowed("https://example.com/transactions") is True
    assert scraper._is_allowed("https://evil.com/steal") is False
    assert scraper._is_allowed("https://sub.example.com/page") is True

def test_not_allowed_domain_raises():
    scraper = DummyScraper(username="u", password="p")
    with pytest.raises(ValueError, match="blocked"):
        scraper._assert_allowed("https://evil.com/steal")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/scrapers/test_base_scraper.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create `backend/scrapers/__init__.py`**

```python
```
(empty)

- [ ] **Step 4: Create `backend/scrapers/base.py`**

```python
import tempfile
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import ClassVar, List
from urllib.parse import urlparse
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

class BaseScraper(ABC):
    ALLOWED_DOMAINS: ClassVar[List[str]] = []
    SOURCE: ClassVar[str] = ""

    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password
        self._browser: Browser = None
        self._context: BrowserContext = None
        self._page: Page = None
        self._logged_in = False

    def _is_allowed(self, url: str) -> bool:
        hostname = urlparse(url).hostname or ""
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in self.ALLOWED_DOMAINS
        )

    def _assert_allowed(self, url: str) -> None:
        if not self._is_allowed(url):
            raise ValueError(f"Navigation to {url} blocked — not in allowed domains {self.ALLOWED_DOMAINS}")

    async def _block_mutations_after_login(self, route, request):
        if request.method != "GET":
            await route.abort()
        else:
            await route.continue_()

    async def _setup_context(self) -> None:
        playwright = await async_playwright().start()
        self._browser = await playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(accept_downloads=True)

        # Block navigation to non-allowlisted domains
        async def enforce_allowlist(route, request):
            if not self._is_allowed(request.url):
                await route.abort()
            else:
                await route.continue_()

        await self._context.route("**/*", enforce_allowlist)
        self._page = await self._context.new_page()

    async def _enable_mutation_blocking(self) -> None:
        await self._context.route("**/*", self._block_mutations_after_login)

    async def _teardown(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()

    @abstractmethod
    async def login(self) -> None: ...

    @abstractmethod
    async def download_transactions(self, since: date) -> Path: ...

    @abstractmethod
    async def logout(self) -> None: ...

    async def sync(self, since: date) -> Path:
        await self._setup_context()
        try:
            await self.login()
            self._logged_in = True
            await self._enable_mutation_blocking()
            download_path = await self.download_transactions(since)
            await self.logout()
            return download_path
        finally:
            await self._teardown()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/scrapers/test_base_scraper.py -v
```

Expected: 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/scrapers/ tests/scrapers/
git commit -m "feat: BaseScraper with domain allowlist and mutation blocking"
```

---

## Task 10: Bank Scrapers (Chase, Discover, Amex)

**Files:**
- Create: `backend/scrapers/chase.py`
- Create: `backend/scrapers/discover.py`
- Create: `backend/scrapers/amex.py`

> **Note:** These scrapers require real bank credentials and live websites to integration-test. Unit tests are limited to structure checks. Full testing must be done manually with your own credentials via the Settings page after the API is wired up.

- [ ] **Step 1: Write structure tests**

Create `tests/scrapers/test_scraper_structure.py`:
```python
from backend.scrapers.chase import ChaseScraper
from backend.scrapers.discover import DiscoverScraper
from backend.scrapers.amex import AmexScraper
from backend.scrapers.base import BaseScraper

def test_scrapers_inherit_base():
    assert issubclass(ChaseScraper, BaseScraper)
    assert issubclass(DiscoverScraper, BaseScraper)
    assert issubclass(AmexScraper, BaseScraper)

def test_scrapers_declare_allowed_domains():
    assert "chase.com" in ChaseScraper.ALLOWED_DOMAINS
    assert "discover.com" in DiscoverScraper.ALLOWED_DOMAINS
    assert "americanexpress.com" in AmexScraper.ALLOWED_DOMAINS

def test_scrapers_declare_source():
    assert ChaseScraper.SOURCE == "chase"
    assert DiscoverScraper.SOURCE == "discover"
    assert AmexScraper.SOURCE == "amex"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/scrapers/test_scraper_structure.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create `backend/scrapers/chase.py`**

```python
import tempfile
from datetime import date
from pathlib import Path
from backend.scrapers.base import BaseScraper

class ChaseScraper(BaseScraper):
    ALLOWED_DOMAINS = ["chase.com", "www.chase.com"]
    SOURCE = "chase"

    LOGIN_URL = "https://www.chase.com"

    async def login(self) -> None:
        await self._page.goto(self.LOGIN_URL)
        await self._page.wait_for_selector("#userId-input", timeout=15000)
        await self._page.fill("#userId-input", self._username)
        await self._page.click("#password-input")
        await self._page.fill("#password-input", self._password)
        await self._page.click("#signin-button")
        # Wait for dashboard to confirm successful login
        await self._page.wait_for_url("**/dashboard/**", timeout=30000)

    async def download_transactions(self, since: date) -> Path:
        # Navigate to account activity download
        await self._page.goto("https://www.chase.com/digital/advanced-transactions/activity")
        await self._page.wait_for_selector("[data-testid='download-activity-button']", timeout=10000)

        # Set date range
        await self._page.click("[data-testid='date-range-custom']")
        await self._page.fill("[data-testid='start-date-input']", since.strftime("%m/%d/%Y"))
        await self._page.fill("[data-testid='end-date-input']", date.today().strftime("%m/%d/%Y"))

        # Select CSV format and download
        await self._page.select_option("[data-testid='file-type-select']", "csv")

        tmp_dir = Path(tempfile.mkdtemp())
        async with self._page.expect_download() as download_info:
            await self._page.click("[data-testid='download-button']")
        download = await download_info.value
        dest = tmp_dir / f"chase_{since.isoformat()}.csv"
        await download.save_as(str(dest))
        return dest

    async def logout(self) -> None:
        await self._page.click("[data-testid='global-header-account-icon']")
        await self._page.click("[data-testid='logout-link']")
```

- [ ] **Step 4: Create `backend/scrapers/discover.py`**

```python
import tempfile
from datetime import date
from pathlib import Path
from backend.scrapers.base import BaseScraper

class DiscoverScraper(BaseScraper):
    ALLOWED_DOMAINS = ["discover.com", "www.discover.com", "portal.discover.com"]
    SOURCE = "discover"

    LOGIN_URL = "https://portal.discover.com/customersvcs/universalLogin/ac_main"

    async def login(self) -> None:
        await self._page.goto(self.LOGIN_URL)
        await self._page.wait_for_selector("#userid", timeout=15000)
        await self._page.fill("#userid", self._username)
        await self._page.fill("#password", self._password)
        await self._page.click("#loginButton")
        await self._page.wait_for_url("**/cardmembersvcs/**", timeout=30000)

    async def download_transactions(self, since: date) -> Path:
        await self._page.goto("https://www.discover.com/credit-cards/cardmembersvcs/acctsvcs.svc/summary")
        await self._page.wait_for_selector("[data-testid='download-link']", timeout=10000)

        await self._page.click("[data-testid='download-link']")
        await self._page.wait_for_selector("[data-testid='date-range-custom']", timeout=5000)
        await self._page.click("[data-testid='date-range-custom']")
        await self._page.fill("[data-testid='from-date']", since.strftime("%m/%d/%Y"))
        await self._page.fill("[data-testid='to-date']", date.today().strftime("%m/%d/%Y"))
        await self._page.select_option("[data-testid='file-format']", "csv")

        tmp_dir = Path(tempfile.mkdtemp())
        async with self._page.expect_download() as download_info:
            await self._page.click("[data-testid='download-submit']")
        download = await download_info.value
        dest = tmp_dir / f"discover_{since.isoformat()}.csv"
        await download.save_as(str(dest))
        return dest

    async def logout(self) -> None:
        await self._page.click("[aria-label='Sign Out']")
```

- [ ] **Step 5: Create `backend/scrapers/amex.py`**

```python
import tempfile
from datetime import date
from pathlib import Path
from backend.scrapers.base import BaseScraper

class AmexScraper(BaseScraper):
    ALLOWED_DOMAINS = ["americanexpress.com", "www.americanexpress.com", "global.americanexpress.com"]
    SOURCE = "amex"

    LOGIN_URL = "https://www.americanexpress.com/en-us/account/login"

    async def login(self) -> None:
        await self._page.goto(self.LOGIN_URL)
        await self._page.wait_for_selector("#eliloUserID", timeout=15000)
        await self._page.fill("#eliloUserID", self._username)
        await self._page.fill("#eliloPassword", self._password)
        await self._page.click("#loginSubmit")
        await self._page.wait_for_url("**/dashboard**", timeout=30000)

    async def download_transactions(self, since: date) -> Path:
        await self._page.goto("https://www.americanexpress.com/en-us/account/activity")
        await self._page.wait_for_selector("[data-testid='download-transactions']", timeout=10000)
        await self._page.click("[data-testid='download-transactions']")

        await self._page.wait_for_selector("[data-testid='custom-date-range']", timeout=5000)
        await self._page.click("[data-testid='custom-date-range']")
        await self._page.fill("[data-testid='start-date']", since.strftime("%m/%d/%Y"))
        await self._page.fill("[data-testid='end-date']", date.today().strftime("%m/%d/%Y"))
        await self._page.select_option("[data-testid='file-format']", "csv")

        tmp_dir = Path(tempfile.mkdtemp())
        async with self._page.expect_download() as download_info:
            await self._page.click("[data-testid='download-btn']")
        download = await download_info.value
        dest = tmp_dir / f"amex_{since.isoformat()}.csv"
        await download.save_as(str(dest))
        return dest

    async def logout(self) -> None:
        await self._page.click("[data-testid='account-menu-trigger']")
        await self._page.click("[data-testid='logout']")
```

- [ ] **Step 6: Run structure tests**

```bash
pytest tests/scrapers/test_scraper_structure.py -v
```

Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/scrapers/chase.py backend/scrapers/discover.py backend/scrapers/amex.py tests/scrapers/test_scraper_structure.py
git commit -m "feat: Chase, Discover, Amex scrapers — download CSV via Playwright"
```

---

## Task 11: Sync Service

**Files:**
- Create: `backend/sync_service.py`
- Create: `tests/test_sync_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_sync_service.py`:
```python
import pytest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from backend.sync_service import SyncService

@pytest.fixture
def mock_session():
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    return session

@pytest.mark.asyncio
async def test_sync_saves_transactions(mock_session, tmp_path):
    csv_file = tmp_path / "chase.csv"
    csv_file.write_text(
        "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
        "05/14/2025,05/15/2025,WHOLE FOODS,Groceries,Sale,-84.20,\n"
    )
    mock_scraper = AsyncMock()
    mock_scraper.sync.return_value = csv_file
    mock_scraper.SOURCE = "chase"

    mock_llm = MagicMock()
    mock_llm.complete.return_value = ""

    service = SyncService(session=mock_session, llm=mock_llm)
    with patch("backend.sync_service.ChaseScraper", return_value=mock_scraper):
        result = await service.sync_bank("chase", since=date(2025, 1, 1), username="u", password="p")

    assert result["tx_count"] == 1
    mock_session.add.assert_called()
    mock_session.commit.assert_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_sync_service.py -v
```

Expected: `ImportError`

- [ ] **Step 3: Create `backend/sync_service.py`**

```python
import json
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.db.models import Subscription, Sync, Transaction
from backend.parsers.csv_parser import parse_csv
from backend.analysis.categorizer import Categorizer
from backend.analysis.subscription_detector import SubscriptionDetector
from backend.scrapers.chase import ChaseScraper
from backend.scrapers.discover import DiscoverScraper
from backend.scrapers.amex import AmexScraper
from backend.llm.base import LLMProvider

SCRAPER_MAP = {
    "chase": ChaseScraper,
    "discover": DiscoverScraper,
    "amex": AmexScraper,
}

class SyncService:
    def __init__(self, session: Session, llm: LLMProvider):
        self._session = session
        self._llm = llm
        self._categorizer = Categorizer(llm=llm)
        self._sub_detector = SubscriptionDetector()

    async def sync_bank(
        self,
        bank: Literal["chase", "discover", "amex"],
        since: date,
        username: str,
        password: str,
    ) -> dict:
        scraper_cls = SCRAPER_MAP[bank]
        scraper = scraper_cls(username=username, password=password)

        csv_path = await scraper.sync(since=since)
        try:
            transactions = parse_csv(csv_path, source=bank)
        finally:
            if csv_path and csv_path.exists():
                csv_path.unlink()

        new_txs = []
        for tx in transactions:
            exists = self._session.execute(
                select(Transaction).where(Transaction.id == tx.id)
            ).scalar_one_or_none()
            if not exists:
                new_txs.append(tx)

        if new_txs:
            categories = self._categorizer.categorize(new_txs)
            for tx in new_txs:
                tx.category = categories.get(tx.id, "other")
                self._session.add(tx)

        all_txs = self._session.execute(select(Transaction)).scalars().all()
        subs = self._sub_detector.detect(list(all_txs))
        for sub in subs:
            existing = self._session.get(Subscription, sub.id)
            if existing:
                existing.last_charged = sub.last_charged
                existing.amount = sub.amount
            else:
                self._session.add(sub)

        sync_record = Sync(
            source=bank,
            synced_at=datetime.utcnow(),
            from_date=since,
            to_date=date.today(),
            tx_count=len(new_txs),
        )
        self._session.add(sync_record)
        self._session.commit()

        return {"bank": bank, "tx_count": len(new_txs)}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_sync_service.py -v
```

Expected: 1 test PASS

- [ ] **Step 5: Commit**

```bash
git add backend/sync_service.py tests/test_sync_service.py
git commit -m "feat: SyncService orchestrates scrape → parse → categorize → store"
```

---

## Task 12: FastAPI Routes

**Files:**
- Modify: `backend/main.py`
- Create: `backend/routes/__init__.py`
- Create: `backend/routes/sync.py`
- Create: `backend/routes/transactions.py`
- Create: `backend/routes/analysis.py`
- Create: `backend/routes/settings.py`
- Create: `tests/routes/test_routes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/routes/test_routes.py`:
```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from backend.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

def test_get_transactions_empty():
    with patch("backend.routes.transactions.get_session") as mock_session_fn:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session_fn.return_value = mock_session
        response = client.get("/transactions")
        assert response.status_code == 200
        assert response.json() == []

def test_get_subscriptions_empty():
    with patch("backend.routes.transactions.get_session") as mock_session_fn:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.execute.return_value.scalars.return_value.all.return_value = []
        mock_session_fn.return_value = mock_session
        response = client.get("/subscriptions")
        assert response.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/routes/test_routes.py::test_health -v
```

Expected: PASS (health already exists). Run all:
```bash
pytest tests/routes/test_routes.py -v
```

Expected: `ImportError` on route tests

- [ ] **Step 3: Create `backend/routes/__init__.py`**

```python
```
(empty)

- [ ] **Step 4: Create `backend/routes/transactions.py`**

```python
from typing import List, Optional
from fastapi import APIRouter
from sqlalchemy import select
from backend.db.database import get_session
from backend.db.models import Subscription, Transaction

router = APIRouter()

@router.get("/transactions")
def list_transactions(
    category: Optional[str] = None,
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
):
    with get_session() as session:
        q = select(Transaction).order_by(Transaction.date.desc())
        if category:
            q = q.where(Transaction.category == category)
        if source:
            q = q.where(Transaction.source == source)
        txs = session.execute(q).scalars().all()
        return [
            {
                "id": tx.id,
                "source": tx.source,
                "date": tx.date.isoformat(),
                "description": tx.description,
                "amount": tx.amount,
                "category": tx.category,
                "is_subscription": tx.is_subscription,
            }
            for tx in txs
        ]

@router.patch("/transactions/{tx_id}/category")
def update_category(tx_id: str, body: dict):
    with get_session() as session:
        tx = session.get(Transaction, tx_id)
        if not tx:
            return {"error": "not found"}, 404
        tx.category = body["category"]
        session.commit()
        return {"id": tx_id, "category": tx.category}

@router.get("/subscriptions")
def list_subscriptions():
    with get_session() as session:
        subs = session.execute(select(Subscription)).scalars().all()
        return [
            {
                "id": sub.id,
                "description": sub.description,
                "amount": sub.amount,
                "frequency": sub.frequency,
                "last_charged": sub.last_charged.isoformat() if sub.last_charged else None,
                "active": sub.active,
            }
            for sub in subs
        ]

@router.patch("/subscriptions/{sub_id}")
def update_subscription(sub_id: str, body: dict):
    with get_session() as session:
        sub = session.get(Subscription, sub_id)
        if not sub:
            return {"error": "not found"}, 404
        if "active" in body:
            sub.active = body["active"]
        session.commit()
        return {"id": sub_id, "active": sub.active}
```

- [ ] **Step 5: Create `backend/routes/analysis.py`**

```python
from collections import defaultdict
from datetime import date, timedelta
from fastapi import APIRouter
from sqlalchemy import select
from backend.db.database import get_session
from backend.db.models import Transaction
from backend.llm.factory import get_llm_provider
from backend.analysis.savings_advisor import SavingsAdvisor

router = APIRouter()

@router.get("/analysis/overview")
def get_overview():
    with get_session() as session:
        txs = session.execute(
            select(Transaction).where(Transaction.amount < 0)
        ).scalars().all()

        by_month: dict = defaultdict(lambda: defaultdict(float))
        for tx in txs:
            month_key = tx.date.strftime("%Y-%m")
            by_month[month_key]["total"] += abs(tx.amount)
            by_month[month_key][tx.category or "other"] += abs(tx.amount)

        return {"monthly": dict(by_month)}

@router.get("/analysis/category-summary")
def get_category_summary():
    three_months_ago = date.today() - timedelta(days=90)
    with get_session() as session:
        txs = session.execute(
            select(Transaction).where(
                Transaction.amount < 0,
                Transaction.date >= three_months_ago,
            )
        ).scalars().all()

        totals: dict = defaultdict(float)
        counts: dict = defaultdict(int)
        for tx in txs:
            cat = tx.category or "other"
            totals[cat] += abs(tx.amount)
            counts[cat] += 1

        return {
            cat: {"total": round(totals[cat], 2), "avg_monthly": round(totals[cat] / 3, 2), "count": counts[cat]}
            for cat in totals
        }

@router.post("/analysis/savings-tips")
def get_savings_tips():
    summary = get_category_summary()
    period_start = (date.today() - timedelta(days=90)).strftime("%b %Y")
    period_end = date.today().strftime("%b %Y")
    period = f"{period_start}–{period_end}"

    llm = get_llm_provider()
    advisor = SavingsAdvisor(llm=llm)
    tips = advisor.get_tips(summary, period=period)
    return {"tips": tips, "period": period}
```

- [ ] **Step 6: Create `backend/routes/sync.py`**

```python
from datetime import date
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from backend.credentials import credentials_store
from backend.db.database import get_session
from backend.llm.factory import get_llm_provider
from backend.sync_service import SyncService

router = APIRouter()

class SyncRequest(BaseModel):
    bank: str
    since: date

@router.post("/sync")
async def trigger_sync(req: SyncRequest):
    username = credentials_store.get_bank_credential(req.bank, "username")
    password = credentials_store.get_bank_credential(req.bank, "password")
    if not username or not password:
        return {"error": f"No credentials found for {req.bank}. Add them in Settings."}, 400

    with get_session() as session:
        service = SyncService(session=session, llm=get_llm_provider())
        result = await service.sync_bank(req.bank, since=req.since, username=username, password=password)
    return result
```

- [ ] **Step 7: Create `backend/routes/settings.py`**

```python
import json
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel
from backend.credentials import credentials_store

router = APIRouter()
CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"

class BankCredential(BaseModel):
    bank: str
    username: str
    password: str

class LLMConfig(BaseModel):
    provider: str
    api_key: str

@router.post("/settings/bank-credentials")
def save_bank_credentials(cred: BankCredential):
    credentials_store.save_bank_credential(cred.bank, "username", cred.username)
    credentials_store.save_bank_credential(cred.bank, "password", cred.password)
    return {"status": "saved", "bank": cred.bank}

@router.get("/settings/banks")
def get_configured_banks():
    banks = ["chase", "discover", "amex"]
    return {
        bank: credentials_store.get_bank_credential(bank, "username") is not None
        for bank in banks
    }

@router.post("/settings/llm")
def save_llm_config(config: LLMConfig):
    credentials_store.save_llm_key(config.provider, config.api_key)
    cfg = json.loads(CONFIG_PATH.read_text())
    cfg["llm_provider"] = config.provider
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    return {"status": "saved", "provider": config.provider}

@router.get("/settings/llm")
def get_llm_config():
    cfg = json.loads(CONFIG_PATH.read_text())
    return {"provider": cfg.get("llm_provider", "claude")}
```

- [ ] **Step 8: Update `backend/main.py` to register all routes**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.database import init_db
from backend.routes.transactions import router as tx_router
from backend.routes.analysis import router as analysis_router
from backend.routes.sync import router as sync_router
from backend.routes.settings import router as settings_router

app = FastAPI(title="PersonalFinance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tx_router)
app.include_router(analysis_router)
app.include_router(sync_router)
app.include_router(settings_router)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 9: Update `backend/db/database.py` to support context manager**

```python
from pathlib import Path
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.db.models import Base

DB_PATH = Path(__file__).parent.parent.parent / "finance.db"
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 10: Run all tests**

```bash
pytest tests/ -v --ignore=tests/scrapers
```

Expected: all tests PASS

- [ ] **Step 11: Verify API starts and routes are visible**

```bash
uvicorn backend.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` — should show all routes: `/sync`, `/transactions`, `/subscriptions`, `/analysis/overview`, `/analysis/savings-tips`, `/settings/bank-credentials`, etc.

- [ ] **Step 12: Commit**

```bash
git add backend/routes/ backend/main.py backend/db/database.py tests/routes/
git commit -m "feat: FastAPI routes for sync, transactions, analysis, and settings"
```

---

## Task 13: React App Shell + Sidebar

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/components/Sidebar.tsx`
- Create: `frontend/src/api/client.ts`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Create API client**

Create `frontend/src/api/client.ts`:
```typescript
import axios from "axios";

const api = axios.create({ baseURL: "http://localhost:8000" });

export const getTransactions = (params?: Record<string, string>) =>
  api.get("/transactions", { params }).then((r) => r.data);

export const updateTransactionCategory = (id: string, category: string) =>
  api.patch(`/transactions/${id}/category`, { category }).then((r) => r.data);

export const getSubscriptions = () =>
  api.get("/subscriptions").then((r) => r.data);

export const updateSubscription = (id: string, data: object) =>
  api.patch(`/subscriptions/${id}`, data).then((r) => r.data);

export const getOverview = () =>
  api.get("/analysis/overview").then((r) => r.data);

export const getCategorySummary = () =>
  api.get("/analysis/category-summary").then((r) => r.data);

export const getSavingsTips = () =>
  api.post("/analysis/savings-tips").then((r) => r.data);

export const triggerSync = (bank: string, since: string) =>
  api.post("/sync", { bank, since }).then((r) => r.data);

export const saveBankCredentials = (bank: string, username: string, password: string) =>
  api.post("/settings/bank-credentials", { bank, username, password }).then((r) => r.data);

export const getConfiguredBanks = () =>
  api.get("/settings/banks").then((r) => r.data);

export const getLLMConfig = () =>
  api.get("/settings/llm").then((r) => r.data);

export const saveLLMConfig = (provider: string, api_key: string) =>
  api.post("/settings/llm", { provider, api_key }).then((r) => r.data);
```

- [ ] **Step 2: Create `frontend/src/components/Sidebar.tsx`**

```tsx
import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Overview", icon: "📊" },
  { to: "/transactions", label: "Transactions", icon: "📋" },
  { to: "/categories", label: "Categories", icon: "🏷️" },
  { to: "/subscriptions", label: "Subscriptions", icon: "🔄" },
  { to: "/savings", label: "Savings Tips", icon: "💡" },
  { to: "/settings", label: "Settings", icon: "⚙️" },
];

export function Sidebar() {
  return (
    <nav style={{
      width: 200, minHeight: "100vh", background: "#1a1a2e",
      padding: "24px 0", display: "flex", flexDirection: "column",
    }}>
      <div style={{ color: "#fff", fontWeight: 700, fontSize: 18, padding: "0 20px 24px" }}>
        💰 FinanceApp
      </div>
      {links.map(({ to, label, icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          style={({ isActive }) => ({
            display: "flex", alignItems: "center", gap: 10,
            padding: "10px 20px", textDecoration: "none",
            color: isActive ? "#fff" : "#8888aa",
            background: isActive ? "rgba(124,106,247,0.2)" : "transparent",
            borderLeft: isActive ? "3px solid #7c6af7" : "3px solid transparent",
            fontSize: 14,
          })}
        >
          <span>{icon}</span>
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
```

- [ ] **Step 3: Update `frontend/src/App.tsx`**

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Overview } from "./pages/Overview";
import { Transactions } from "./pages/Transactions";
import { Categories } from "./pages/Categories";
import { Subscriptions } from "./pages/Subscriptions";
import { SavingsTips } from "./pages/SavingsTips";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ display: "flex", minHeight: "100vh", fontFamily: "system-ui, sans-serif" }}>
        <Sidebar />
        <main style={{ flex: 1, padding: 32, background: "#f8f8ff", overflowY: "auto" }}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/categories" element={<Categories />} />
            <Route path="/subscriptions" element={<Subscriptions />} />
            <Route path="/savings" element={<SavingsTips />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
```

- [ ] **Step 4: Create stub pages so the app compiles**

Create `frontend/src/pages/Overview.tsx`:
```tsx
export function Overview() { return <div><h1>Overview</h1></div>; }
```

Create `frontend/src/pages/Transactions.tsx`:
```tsx
export function Transactions() { return <div><h1>Transactions</h1></div>; }
```

Create `frontend/src/pages/Categories.tsx`:
```tsx
export function Categories() { return <div><h1>Categories</h1></div>; }
```

Create `frontend/src/pages/Subscriptions.tsx`:
```tsx
export function Subscriptions() { return <div><h1>Subscriptions</h1></div>; }
```

Create `frontend/src/pages/SavingsTips.tsx`:
```tsx
export function SavingsTips() { return <div><h1>Savings Tips</h1></div>; }
```

Create `frontend/src/pages/Settings.tsx`:
```tsx
export function Settings() { return <div><h1>Settings</h1></div>; }
```

- [ ] **Step 5: Verify app compiles and sidebar works**

```bash
cd ~/Documents/PersonalFinance/frontend && npm run dev
```

Open `http://localhost:5173` — sidebar should be visible and all nav links should work.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat: React app shell with sidebar navigation and route stubs"
```

---

## Task 14: Overview Page

**Files:**
- Modify: `frontend/src/pages/Overview.tsx`
- Create: `frontend/src/components/SpendingLineChart.tsx`
- Create: `frontend/src/components/CategoryStackedBar.tsx`

- [ ] **Step 1: Create `frontend/src/components/SpendingLineChart.tsx`**

```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

interface Props {
  data: { month: string; total: number }[];
}

export function SpendingLineChart({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#ececf8" />
        <XAxis dataKey="month" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `$${v}`} />
        <Tooltip formatter={(v: number) => `$${v.toFixed(2)}`} />
        <Line type="monotone" dataKey="total" stroke="#7c6af7" strokeWidth={2} dot={{ r: 4 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/CategoryStackedBar.tsx`**

```tsx
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

const CATEGORY_COLORS: Record<string, string> = {
  dining: "#7c6af7", groceries: "#a78bfa", transport: "#c4b5fd",
  shopping: "#60a5fa", entertainment: "#34d399", subscriptions: "#f59e0b",
  health: "#f87171", travel: "#38bdf8", utilities: "#94a3b8", other: "#d1d5db",
};

interface Props {
  data: { month: string; [category: string]: number | string }[];
  categories: string[];
}

export function CategoryStackedBar({ data, categories }: Props) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
        <XAxis dataKey="month" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `$${v}`} />
        <Tooltip formatter={(v: number) => `$${v.toFixed(2)}`} />
        <Legend />
        {categories.map((cat) => (
          <Bar key={cat} dataKey={cat} stackId="a" fill={CATEGORY_COLORS[cat] ?? "#d1d5db"} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 3: Implement `frontend/src/pages/Overview.tsx`**

```tsx
import { useEffect, useState } from "react";
import { getOverview, triggerSync, getConfiguredBanks } from "../api/client";
import { SpendingLineChart } from "../components/SpendingLineChart";
import { CategoryStackedBar } from "../components/CategoryStackedBar";

const CARD_STYLE = {
  background: "#fff", borderRadius: 10, padding: "16px 20px",
  boxShadow: "0 1px 4px rgba(0,0,0,0.07)", flex: 1,
};

export function Overview() {
  const [data, setData] = useState<any>(null);
  const [banks, setBanks] = useState<Record<string, boolean>>({});
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    getOverview().then(setData);
    getConfiguredBanks().then(setBanks);
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    const since = new Date();
    since.setMonth(since.getMonth() - 3);
    const sinceStr = since.toISOString().split("T")[0];
    const activeBanks = Object.entries(banks).filter(([, v]) => v).map(([k]) => k);
    await Promise.all(activeBanks.map((bank) => triggerSync(bank, sinceStr)));
    const fresh = await getOverview();
    setData(fresh);
    setSyncing(false);
  };

  if (!data) return <p>Loading...</p>;

  const months = Object.keys(data.monthly).sort().slice(-12);
  const lineData = months.map((m) => ({ month: m, total: data.monthly[m]?.total ?? 0 }));

  const allCats = new Set<string>();
  months.forEach((m) => Object.keys(data.monthly[m] ?? {}).filter((k) => k !== "total").forEach((c) => allCats.add(c)));
  const categories = Array.from(allCats);
  const barData = months.slice(-6).map((m) => ({
    month: m, ...Object.fromEntries(categories.map((c) => [c, data.monthly[m]?.[c] ?? 0])),
  }));

  const currentMonth = months[months.length - 1];
  const prevMonth = months[months.length - 2];
  const currentTotal = data.monthly[currentMonth]?.total ?? 0;
  const prevTotal = data.monthly[prevMonth]?.total ?? 1;
  const pctChange = (((currentTotal - prevTotal) / prevTotal) * 100).toFixed(1);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 24 }}>Overview</h1>
        <button onClick={handleSync} disabled={syncing} style={{
          background: "#7c6af7", color: "#fff", border: "none",
          borderRadius: 8, padding: "8px 20px", cursor: "pointer", fontSize: 14,
        }}>
          {syncing ? "Syncing…" : "Sync Now"}
        </button>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 32 }}>
        <div style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>Total Spent This Month</div>
          <div style={{ fontSize: 28, fontWeight: 700 }}>${currentTotal.toFixed(2)}</div>
        </div>
        <div style={CARD_STYLE}>
          <div style={{ color: "#888", fontSize: 12, marginBottom: 4 }}>vs Last Month</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: Number(pctChange) > 0 ? "#e05" : "#0a0" }}>
            {Number(pctChange) > 0 ? "+" : ""}{pctChange}%
          </div>
        </div>
      </div>

      <div style={{ background: "#fff", borderRadius: 10, padding: 24, marginBottom: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>Total Monthly Spending (12 months)</h2>
        <SpendingLineChart data={lineData} />
      </div>

      <div style={{ background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>Spending by Category (6 months)</h2>
        <CategoryStackedBar data={barData} categories={categories} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify page renders**

With backend and frontend running, visit `http://localhost:5173` — Overview should show summary cards and chart containers (empty if no data yet, which is expected).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Overview.tsx frontend/src/components/
git commit -m "feat: Overview page with line chart and category stacked bar"
```

---

## Task 15: Transactions Page

**Files:**
- Modify: `frontend/src/pages/Transactions.tsx`

- [ ] **Step 1: Implement `frontend/src/pages/Transactions.tsx`**

```tsx
import { useEffect, useState } from "react";
import { getTransactions, updateTransactionCategory } from "../api/client";

const CATEGORIES = [
  "dining", "groceries", "transport", "shopping", "entertainment",
  "subscriptions", "health", "travel", "utilities", "other",
];

const CATEGORY_COLORS: Record<string, string> = {
  dining: "#7c6af7", groceries: "#a78bfa", transport: "#c4b5fd",
  shopping: "#60a5fa", entertainment: "#34d399", subscriptions: "#f59e0b",
  health: "#f87171", travel: "#38bdf8", utilities: "#94a3b8", other: "#d1d5db",
};

export function Transactions() {
  const [txs, setTxs] = useState<any[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [filterCategory, setFilterCategory] = useState("");
  const [filterSource, setFilterSource] = useState("");

  useEffect(() => {
    const params: Record<string, string> = {};
    if (filterCategory) params.category = filterCategory;
    if (filterSource) params.source = filterSource;
    getTransactions(params).then(setTxs);
  }, [filterCategory, filterSource]);

  const handleCategoryChange = async (id: string, category: string) => {
    await updateTransactionCategory(id, category);
    setTxs((prev) => prev.map((tx) => tx.id === id ? { ...tx, category } : tx));
    setEditingId(null);
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 20 }}>Transactions</h1>

      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
        <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14 }}>
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={filterSource} onChange={(e) => setFilterSource(e.target.value)}
          style={{ padding: "6px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14 }}>
          <option value="">All Banks</option>
          <option value="chase">Chase</option>
          <option value="discover">Discover</option>
          <option value="amex">Amex</option>
        </select>
      </div>

      <div style={{ background: "#fff", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#f0f0f8", textAlign: "left" }}>
              <th style={{ padding: "12px 16px" }}>Date</th>
              <th style={{ padding: "12px 16px" }}>Description</th>
              <th style={{ padding: "12px 16px" }}>Bank</th>
              <th style={{ padding: "12px 16px" }}>Category</th>
              <th style={{ padding: "12px 16px", textAlign: "right" }}>Amount</th>
            </tr>
          </thead>
          <tbody>
            {txs.map((tx) => (
              <tr key={tx.id} style={{ borderTop: "1px solid #f0f0f0" }}>
                <td style={{ padding: "10px 16px", color: "#888" }}>{tx.date}</td>
                <td style={{ padding: "10px 16px" }}>{tx.description}</td>
                <td style={{ padding: "10px 16px", color: "#888", textTransform: "capitalize" }}>{tx.source}</td>
                <td style={{ padding: "10px 16px" }}>
                  {editingId === tx.id ? (
                    <select autoFocus defaultValue={tx.category}
                      onChange={(e) => handleCategoryChange(tx.id, e.target.value)}
                      onBlur={() => setEditingId(null)}
                      style={{ fontSize: 13, padding: "2px 6px", borderRadius: 4 }}>
                      {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  ) : (
                    <span onClick={() => setEditingId(tx.id)} style={{
                      background: CATEGORY_COLORS[tx.category] ?? "#d1d5db",
                      color: "#fff", padding: "2px 8px", borderRadius: 12,
                      fontSize: 12, cursor: "pointer",
                    }}>{tx.category ?? "—"}</span>
                  )}
                </td>
                <td style={{ padding: "10px 16px", textAlign: "right", color: tx.amount < 0 ? "#e05" : "#0a0", fontWeight: 600 }}>
                  {tx.amount < 0 ? "-" : "+"}${Math.abs(tx.amount).toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {txs.length === 0 && (
          <p style={{ textAlign: "center", color: "#aaa", padding: 40 }}>No transactions yet. Sync your accounts in Settings.</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify page renders and filters work**

Visit `http://localhost:5173/transactions` — table should show with filter dropdowns.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Transactions.tsx
git commit -m "feat: Transactions page with category filter, source filter, inline category edit"
```

---

## Task 16: Categories Page

**Files:**
- Modify: `frontend/src/pages/Categories.tsx`

- [ ] **Step 1: Implement `frontend/src/pages/Categories.tsx`**

```tsx
import { useEffect, useState } from "react";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { getCategorySummary } from "../api/client";

const COLORS = ["#7c6af7","#a78bfa","#c4b5fd","#60a5fa","#34d399","#f59e0b","#f87171","#38bdf8","#94a3b8","#d1d5db"];

export function Categories() {
  const [summary, setSummary] = useState<Record<string, any>>({});

  useEffect(() => { getCategorySummary().then(setSummary); }, []);

  const pieData = Object.entries(summary).map(([name, d]) => ({ name, value: d.total }));

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>Categories</h1>
      <p style={{ color: "#888", marginBottom: 24 }}>Last 3 months of spending by category</p>

      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <div style={{ background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", flex: "1 1 360px" }}>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={110} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip formatter={(v: number) => `$${v.toFixed(2)}`} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div style={{ flex: "1 1 280px" }}>
          {Object.entries(summary).sort((a, b) => b[1].total - a[1].total).map(([cat, d], i) => (
            <div key={cat} style={{ background: "#fff", borderRadius: 8, padding: "12px 16px", marginBottom: 10, boxShadow: "0 1px 3px rgba(0,0,0,0.06)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ width: 12, height: 12, borderRadius: "50%", background: COLORS[i % COLORS.length] }} />
                <span style={{ textTransform: "capitalize", fontSize: 14 }}>{cat}</span>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontWeight: 700, fontSize: 15 }}>${d.total.toFixed(2)}</div>
                <div style={{ color: "#888", fontSize: 12 }}>${d.avg_monthly.toFixed(2)}/mo</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify page renders**

Visit `http://localhost:5173/categories` — donut chart + breakdown list should render.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Categories.tsx
git commit -m "feat: Categories page with donut chart and per-category breakdown"
```

---

## Task 17: Subscriptions Page

**Files:**
- Modify: `frontend/src/pages/Subscriptions.tsx`

- [ ] **Step 1: Implement `frontend/src/pages/Subscriptions.tsx`**

```tsx
import { useEffect, useState } from "react";
import { getSubscriptions, updateSubscription } from "../api/client";

export function Subscriptions() {
  const [subs, setSubs] = useState<any[]>([]);

  useEffect(() => { getSubscriptions().then(setSubs); }, []);

  const toggleActive = async (id: string, active: boolean) => {
    await updateSubscription(id, { active: !active });
    setSubs((prev) => prev.map((s) => s.id === id ? { ...s, active: !active } : s));
  };

  const active = subs.filter((s) => s.active);
  const monthlyTotal = active.filter((s) => s.frequency === "monthly").reduce((sum, s) => sum + s.amount, 0);
  const annualTotal = active.reduce((sum, s) => sum + (s.frequency === "monthly" ? s.amount * 12 : s.amount), 0);

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>Subscriptions</h1>
      <p style={{ color: "#888", marginBottom: 16 }}>Auto-detected recurring charges</p>

      <div style={{ display: "flex", gap: 16, marginBottom: 28 }}>
        <div style={{ background: "#fff", borderRadius: 10, padding: "14px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
          <div style={{ color: "#888", fontSize: 12 }}>Monthly Total</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>${monthlyTotal.toFixed(2)}</div>
        </div>
        <div style={{ background: "#fff", borderRadius: 10, padding: "14px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
          <div style={{ color: "#888", fontSize: 12 }}>Annual Total</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>${annualTotal.toFixed(2)}</div>
        </div>
      </div>

      <div style={{ background: "#fff", borderRadius: 10, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ background: "#f0f0f8", textAlign: "left" }}>
              <th style={{ padding: "12px 16px" }}>Service</th>
              <th style={{ padding: "12px 16px" }}>Frequency</th>
              <th style={{ padding: "12px 16px" }}>Last Charged</th>
              <th style={{ padding: "12px 16px", textAlign: "right" }}>Amount</th>
              <th style={{ padding: "12px 16px", textAlign: "center" }}>Active</th>
            </tr>
          </thead>
          <tbody>
            {subs.map((sub) => (
              <tr key={sub.id} style={{ borderTop: "1px solid #f0f0f0", opacity: sub.active ? 1 : 0.5 }}>
                <td style={{ padding: "10px 16px", fontWeight: 500 }}>{sub.description}</td>
                <td style={{ padding: "10px 16px", color: "#888", textTransform: "capitalize" }}>{sub.frequency}</td>
                <td style={{ padding: "10px 16px", color: "#888" }}>{sub.last_charged ?? "—"}</td>
                <td style={{ padding: "10px 16px", textAlign: "right", fontWeight: 600 }}>${sub.amount.toFixed(2)}</td>
                <td style={{ padding: "10px 16px", textAlign: "center" }}>
                  <input type="checkbox" checked={sub.active} onChange={() => toggleActive(sub.id, sub.active)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {subs.length === 0 && (
          <p style={{ textAlign: "center", color: "#aaa", padding: 40 }}>No subscriptions detected yet. Sync your accounts first.</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Subscriptions.tsx
git commit -m "feat: Subscriptions page with monthly/annual totals and active toggle"
```

---

## Task 18: Savings Tips Page

**Files:**
- Modify: `frontend/src/pages/SavingsTips.tsx`

- [ ] **Step 1: Implement `frontend/src/pages/SavingsTips.tsx`**

```tsx
import { useState } from "react";
import { getSavingsTips, saveLLMConfig, getLLMConfig } from "../api/client";
import { useEffect } from "react";

export function SavingsTips() {
  const [tips, setTips] = useState<string[]>([]);
  const [period, setPeriod] = useState("");
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState("claude");

  useEffect(() => { getLLMConfig().then((c) => setProvider(c.provider)); }, []);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const result = await getSavingsTips();
      setTips(result.tips);
      setPeriod(result.period);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 8 }}>Savings Tips</h1>
      <p style={{ color: "#888", marginBottom: 24 }}>AI-generated suggestions based on your last 3 months of spending</p>

      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 24 }}>
        <select value={provider} onChange={(e) => setProvider(e.target.value)}
          style={{ padding: "8px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14 }}>
          <option value="claude">Claude (Anthropic)</option>
          <option value="gemini">Gemini (Google)</option>
        </select>
        <button onClick={handleGenerate} disabled={loading} style={{
          background: "#7c6af7", color: "#fff", border: "none",
          borderRadius: 8, padding: "8px 20px", cursor: "pointer", fontSize: 14,
        }}>
          {loading ? "Generating…" : tips.length ? "Regenerate Tips" : "Generate Tips"}
        </button>
      </div>

      {period && <p style={{ color: "#888", fontSize: 13, marginBottom: 16 }}>Analysis period: {period}</p>}

      {tips.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {tips.map((tip, i) => (
            <div key={i} style={{ background: "#fff", borderRadius: 10, padding: "16px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)", display: "flex", gap: 14 }}>
              <span style={{ fontSize: 20 }}>💡</span>
              <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6 }}>{tip}</p>
            </div>
          ))}
        </div>
      )}

      {tips.length === 0 && !loading && (
        <p style={{ color: "#aaa", textAlign: "center", marginTop: 60 }}>Click "Generate Tips" to get personalized saving suggestions.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/SavingsTips.tsx
git commit -m "feat: Savings Tips page with Claude/Gemini toggle and regenerate"
```

---

## Task 19: Settings Page

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Implement `frontend/src/pages/Settings.tsx`**

```tsx
import { useEffect, useState } from "react";
import { saveBankCredentials, getConfiguredBanks, saveLLMConfig, getLLMConfig } from "../api/client";

const BANKS = [
  { id: "chase", label: "Chase" },
  { id: "discover", label: "Discover" },
  { id: "amex", label: "American Express" },
];

const INPUT = { padding: "8px 12px", borderRadius: 6, border: "1px solid #ddd", fontSize: 14, width: "100%", boxSizing: "border-box" as const };
const SECTION = { background: "#fff", borderRadius: 10, padding: 24, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", marginBottom: 24 };

export function Settings() {
  const [configuredBanks, setConfiguredBanks] = useState<Record<string, boolean>>({});
  const [bankForms, setBankForms] = useState<Record<string, { username: string; password: string }>>({});
  const [llmProvider, setLlmProvider] = useState("claude");
  const [llmKey, setLlmKey] = useState("");
  const [savedMsg, setSavedMsg] = useState("");

  useEffect(() => {
    getConfiguredBanks().then(setConfiguredBanks);
    getLLMConfig().then((c) => setLlmProvider(c.provider));
  }, []);

  const handleBankSave = async (bank: string) => {
    const { username, password } = bankForms[bank] ?? {};
    if (!username || !password) return;
    await saveBankCredentials(bank, username, password);
    setConfiguredBanks((prev) => ({ ...prev, [bank]: true }));
    setBankForms((prev) => ({ ...prev, [bank]: { username: "", password: "" } }));
    setSavedMsg(`${bank} credentials saved.`);
    setTimeout(() => setSavedMsg(""), 3000);
  };

  const handleLLMSave = async () => {
    await saveLLMConfig(llmProvider, llmKey);
    setLlmKey("");
    setSavedMsg("LLM settings saved.");
    setTimeout(() => setSavedMsg(""), 3000);
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24 }}>Settings</h1>
      {savedMsg && <div style={{ background: "#d1fae5", color: "#065f46", padding: "10px 16px", borderRadius: 8, marginBottom: 20, fontSize: 14 }}>{savedMsg}</div>}

      <div style={SECTION}>
        <h2 style={{ fontSize: 16, marginTop: 0, marginBottom: 20 }}>Bank Credentials</h2>
        <p style={{ color: "#888", fontSize: 13, marginBottom: 20 }}>Credentials are saved to macOS Keychain — never written to disk.</p>
        {BANKS.map(({ id, label }) => (
          <div key={id} style={{ marginBottom: 24 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <span style={{ fontSize: 15, fontWeight: 600 }}>{label}</span>
              {configuredBanks[id] && <span style={{ background: "#d1fae5", color: "#065f46", fontSize: 11, padding: "2px 8px", borderRadius: 10 }}>Configured</span>}
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <input placeholder="Username" value={bankForms[id]?.username ?? ""} type="text"
                onChange={(e) => setBankForms((p) => ({ ...p, [id]: { ...p[id], username: e.target.value } }))}
                style={{ ...INPUT, maxWidth: 200 }} />
              <input placeholder="Password" value={bankForms[id]?.password ?? ""} type="password"
                onChange={(e) => setBankForms((p) => ({ ...p, [id]: { ...p[id], password: e.target.value } }))}
                style={{ ...INPUT, maxWidth: 200 }} />
              <button onClick={() => handleBankSave(id)} style={{ background: "#7c6af7", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: "pointer", fontSize: 14 }}>
                Save
              </button>
            </div>
          </div>
        ))}
      </div>

      <div style={SECTION}>
        <h2 style={{ fontSize: 16, marginTop: 0, marginBottom: 16 }}>AI Provider</h2>
        <div style={{ display: "flex", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
          <select value={llmProvider} onChange={(e) => setLlmProvider(e.target.value)}
            style={{ ...INPUT, maxWidth: 200 }}>
            <option value="claude">Claude (Anthropic)</option>
            <option value="gemini">Gemini (Google)</option>
          </select>
          <input placeholder={llmProvider === "claude" ? "sk-ant-..." : "AIza..."} type="password"
            value={llmKey} onChange={(e) => setLlmKey(e.target.value)}
            style={{ ...INPUT, maxWidth: 280 }} />
          <button onClick={handleLLMSave} style={{ background: "#7c6af7", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: "pointer", fontSize: 14 }}>
            Save
          </button>
        </div>
        <p style={{ color: "#888", fontSize: 13 }}>API keys are saved to macOS Keychain.</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify Settings page works end-to-end**

1. Start backend: `uvicorn backend.main:app --reload --port 8000`
2. Start frontend: `cd frontend && npm run dev`
3. Visit `http://localhost:5173/settings`
4. Enter credentials for one bank and click Save — should show green "Configured" badge
5. Enter an LLM API key and save

- [ ] **Step 3: Run full test suite**

```bash
cd ~/Documents/PersonalFinance
source .venv/bin/activate
pytest tests/ -v --ignore=tests/scrapers/test_scraper_structure.py
```

Expected: all tests PASS

- [ ] **Step 4: Final commit**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "feat: Settings page — bank credentials and LLM API key saved to Keychain"
```

---

## Post-Implementation Notes

### Manual Scraper Testing
The bank scrapers (Task 10) use hardcoded CSS selectors based on current bank website structure. Banks change their UIs periodically. After completing Tasks 1–19:

1. Set credentials in Settings for one bank
2. Trigger a sync from the Overview page
3. Watch the backend logs for selector errors (`TimeoutError`)
4. If a selector fails, inspect the bank's current login/download page and update the relevant selector in `backend/scrapers/<bank>.py`

### MFA Handling
The current scrapers call `await self._page.wait_for_url(...)` after login. If your bank requires an MFA code:
- The scraper will time out waiting for the dashboard URL
- A future enhancement would pause the scraper and surface an MFA input in the dashboard

### `.gitignore` reminder
Ensure `finance.db` is gitignored (already in the root `.gitignore` from Task 1). Never commit `finance.db` — it contains your transaction data.
