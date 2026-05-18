# Personal Finance App — Design Spec
**Date:** 2026-05-17  
**Status:** Approved

---

## Overview

A local personal finance app that automatically downloads transaction data from Chase, Discover, and American Express using browser automation, stores it locally, and provides an interactive web dashboard with expense analysis, subscription detection, trend charts, and AI-powered saving tips.

---

## Architecture

```
┌─────────────────────────────────────────┐
│         React Dashboard (frontend)       │
│  Charts · Categories · Subscriptions    │
│  Saving Tips · Transaction Table        │
└────────────────┬────────────────────────┘
                 │ HTTP (REST API)
┌────────────────▼────────────────────────┐
│         FastAPI Backend (Python)         │
│  /sync  /transactions  /analysis        │
│  /subscriptions  /savings-tips          │
└──────┬──────────────────────┬───────────┘
       │                      │
┌──────▼──────┐     ┌─────────▼──────────┐
│  Playwright │     │   SQLite Database   │
│  Scrapers   │     │  finance.db         │
│  Chase      │     │  (local, persisted) │
│  Discover   │     └────────────────────┘
│  Amex       │
└──────┬──────┘
       │
┌──────▼──────────────────────────────────┐
│  Credentials Store                       │
│  macOS Keychain (via keyring library)    │
│  — passwords never written to disk       │
└─────────────────────────────────────────┘
```

**Key architectural decisions:**
- Credentials stored exclusively in macOS Keychain via Python `keyring` — never in config files or `.env`
- Transactions stored in local SQLite (`finance.db`) — no external database required
- Syncing is on-demand (user-triggered from dashboard), not scheduled
- LLM API keys stored in Keychain; provider choice stored in `config.json`
- All LLM calls happen server-side only

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + Recharts (for charts) |
| Backend | Python 3.11+ · FastAPI |
| Browser automation | Playwright (Python) |
| Database | SQLite via SQLAlchemy |
| Credential storage | macOS Keychain via `keyring` |
| LLM | Claude (Anthropic SDK) or Gemini (google-generativeai) — configurable |

---

## Bank Scrapers

### Interface

Each bank has a dedicated scraper class inheriting from `BaseScraper`:

```python
class BaseScraper:
    def login(self) -> None: ...
    def download_transactions(self, since: date) -> Path: ...  # returns path to downloaded CSV
    def logout(self) -> None: ...

class ChaseScraper(BaseScraper): ...
class DiscoverScraper(BaseScraper): ...
class AmexScraper(BaseScraper): ...
```

### Sync Flow

1. Retrieve credentials from macOS Keychain
2. Launch headless Playwright browser in a fresh, isolated context
3. Log in to bank site; if MFA is required, pause and prompt user via dashboard
4. Navigate to transaction export page
5. Set date range (`since` parameter — no hardcoded limit; defaults to last sync date on subsequent syncs)
6. Click download; file saved to a temp directory
7. Log out and close browser
8. Parser normalizes CSV to common `Transaction` schema
9. Upsert into SQLite (deduplicated by transaction ID hash)
10. Delete temp CSV file

### Date Range

- First sync: user selects start date via dashboard date picker (Chase supports up to 7 years, Amex up to 3 years, Discover up to 18 months)
- Subsequent syncs: automatically uses last sync date as `since`

### Security Constraints (enforced in `BaseScraper`)

- **Domain allowlist**: every navigation is intercepted via `page.route()`; requests outside the bank's allowlisted domains are aborted
- **Mutation blocking**: all non-GET requests are blocked at the network level after login completes — no form submissions, transfers, or payments can be sent
- **No persistent sessions**: each sync uses a fresh `browser.new_context()` — no shared cookies
- **Download scope**: `accept_downloads=True` scoped only to the bank's export endpoint; saved to a temp directory and deleted after parsing
- **Read-only by design**: scrapers only navigate to transaction history/export pages

---

## Data Model (SQLite)

```sql
CREATE TABLE transactions (
    id          TEXT PRIMARY KEY,  -- hash of (source + date + amount + description)
    source      TEXT NOT NULL,     -- 'chase' | 'discover' | 'amex'
    date        DATE NOT NULL,
    description TEXT NOT NULL,
    amount      REAL NOT NULL,     -- negative = expense, positive = credit/refund
    category    TEXT,              -- AI-assigned or manually overridden
    is_subscription INTEGER DEFAULT 0,
    metadata    TEXT,              -- JSON blob: bank-provided fields (MCC, type, etc.)
    raw_csv_row TEXT               -- original CSV row for debugging
);

CREATE TABLE subscriptions (
    id           TEXT PRIMARY KEY,
    description  TEXT NOT NULL,
    amount       REAL NOT NULL,
    frequency    TEXT NOT NULL,    -- 'monthly' | 'annual'
    last_charged DATE,
    active       INTEGER DEFAULT 1
);

CREATE TABLE syncs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,
    synced_at  DATETIME NOT NULL,
    from_date  DATE NOT NULL,
    to_date    DATE NOT NULL,
    tx_count   INTEGER NOT NULL
);
```

**Notes:**
- `metadata` is a flexible JSON column storing whatever each bank's CSV provides (e.g. merchant category code, transaction type) — no fixed per-bank columns
- Location data is not available from CSV exports; enrichment can be added later via a merchant API

---

## Analysis Engine

### 1. Categorizer
- Runs at import time for all new transactions
- Transactions are batched into a single LLM prompt (not one call per transaction)
- Returns a category label per transaction
- Categories: `dining`, `groceries`, `transport`, `shopping`, `entertainment`, `subscriptions`, `health`, `travel`, `utilities`, `other`
- Categories stored on the transaction; user can manually override via the Transactions page

### 2. Subscription Detector
- Runs after each sync
- Identifies transactions recurring on a regular interval (weekly / monthly / annual) with matching description and amount (±$1 tolerance)
- Upserts detected subscriptions into the `subscriptions` table
- User can mark any subscription as inactive

### 3. Savings Advisor
- Runs on-demand from the dashboard
- Sends aggregated spending summary (totals by category for last 3 months) to the LLM — not raw transaction descriptions
- LLM returns 3–5 specific, actionable saving tips
- User can switch between Claude and Gemini and regenerate tips at any time

### LLM Provider Abstraction

```python
class LLMProvider(Protocol):
    def complete(self, prompt: str) -> str: ...

class ClaudeProvider(LLMProvider): ...   # uses anthropic SDK
class GeminiProvider(LLMProvider): ...  # uses google-generativeai SDK
```

- Active provider configured in `config.json` (`{"llm_provider": "claude"}`)
- API keys stored in macOS Keychain
- All three analysis components use the abstraction — provider-agnostic

---

## React Dashboard

### Navigation
Sidebar layout with persistent left navigation:
- Overview
- Transactions
- Categories
- Subscriptions
- Savings Tips
- Settings

### Pages

**Overview**
- Summary cards: total spent this month, total subscriptions, % change vs last month
- Line chart: total monthly spending over last 12 months
- Stacked bar chart: spending by category over last 6 months (with color legend)
- Sync button (triggers scraper for all or selected banks)

**Transactions**
- Full transaction table: date, description, category, source, amount
- Filters: by category, by bank source, by date range
- Click a row to manually edit its category

**Categories**
- Donut chart of spending by category for selected month
- Month selector to browse historical breakdowns

**Subscriptions**
- Table of auto-detected recurring charges
- Monthly and annual cost totals
- Toggle active/inactive per subscription

**Savings Tips**
- AI-generated tips based on last 3 months of aggregated spend
- Provider toggle: Claude / Gemini
- Regenerate button

**Settings**
- Bank credential setup (one-time per bank; saved to Keychain)
- LLM provider selection
- LLM API key entry (saved to Keychain)
- Default sync date range

---

## Credential Setup Flow

1. User opens Settings for the first time
2. Enters username + password per bank
3. App saves credentials to macOS Keychain via `keyring`
4. Credentials are never written to disk, `.env`, or `config.json`
5. On sync, credentials are retrieved from Keychain at runtime

---

## Project Structure

```
PersonalFinance/
├── backend/
│   ├── main.py                  # FastAPI app + route definitions
│   ├── scrapers/
│   │   ├── base.py              # BaseScraper + security constraints
│   │   ├── chase.py
│   │   ├── discover.py
│   │   └── amex.py
│   ├── parsers/
│   │   └── csv_parser.py        # Per-bank CSV normalization
│   ├── analysis/
│   │   ├── categorizer.py
│   │   ├── subscription_detector.py
│   │   └── savings_advisor.py
│   ├── llm/
│   │   ├── base.py              # LLMProvider protocol
│   │   ├── claude_provider.py
│   │   └── gemini_provider.py
│   ├── db/
│   │   ├── models.py            # SQLAlchemy models
│   │   └── database.py          # SQLite connection + migrations
│   └── credentials.py           # Keychain read/write via keyring
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Overview.tsx
│   │   │   ├── Transactions.tsx
│   │   │   ├── Categories.tsx
│   │   │   ├── Subscriptions.tsx
│   │   │   ├── SavingsTips.tsx
│   │   │   └── Settings.tsx
│   │   ├── components/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── SpendingLineChart.tsx
│   │   │   ├── CategoryStackedBar.tsx
│   │   │   └── TransactionTable.tsx
│   │   └── App.tsx
│   └── package.json
├── config.json                  # Non-sensitive config (llm_provider, etc.)
├── finance.db                   # SQLite database (gitignored)
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-05-17-personal-finance-design.md
```

---

## Out of Scope (for this version)

- Mobile app
- Multi-user / cloud sync
- Merchant logo / location enrichment (can be added later via API)
- Automatic scheduled syncing (on-demand only)
- Budget setting / alerts
