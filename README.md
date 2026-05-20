# PersonalFinance

A local-first personal finance dashboard. Import bank CSVs, enrich transactions with AI, track subscriptions, and get spending insights — all running on your machine with no data sent to third-party servers except the LLM API.

![Dashboard](https://img.shields.io/badge/stack-FastAPI%20%2B%20React-7c6af7)

## Features

- **Import** — Upload CSVs from Chase, Discover, and Amex
- **AI Enrichment** — Extracts merchant names, cities, and merchant types using Gemini
- **Search** — Keyword and semantic (embedding-based) search across all transactions
- **Categories** — Pie chart breakdown with configurable date ranges
- **Insights** — Spending anomalies, duplicate charge detection, price increases, merchant breakdown, day-of-week patterns, year-over-year comparison
- **Subscriptions** — Auto-detected recurring charges, manual entry, usage-based detection for API services
- **Savings Tips** — AI-generated suggestions based on your actual spending
- **Export** — Download any filtered view as CSV

## Requirements

- Python 3.11+
- Node.js 18+
- A Gemini API key (Google AI Studio — [get one free](https://aistudio.google.com/app/apikey))
- Optionally an Anthropic API key for Claude-based savings tips

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Aitous/PersonalFinance.git
cd PersonalFinance
```

### 2. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Frontend

```bash
cd frontend
npm install
cd ..
```

### 4. Configure your LLM API key

Start the backend once to initialize the database, then open Settings in the app and save your Gemini (or Anthropic) API key. Keys are stored in macOS Keychain and never written to disk.

Alternatively, set them directly via the API:

```bash
curl -X POST http://localhost:8000/settings/llm \
  -H "Content-Type: application/json" \
  -d '{"provider": "gemini", "api_key": "YOUR_KEY"}'
```

## Running

Open two terminals:

**Terminal 1 — Backend:**
```bash
source .venv/bin/activate
uvicorn backend.main:app --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Then open [http://localhost:5173](http://localhost:5173).

## Importing Transactions

1. Download CSVs from your bank's website
2. Go to **Overview** → drag and drop or use the file picker
3. Supported formats: Chase, Discover, Amex (the app auto-detects the bank from the filename)
4. Click **Enrich new transactions** to run AI extraction of merchant names, cities, and types
5. Click **Re-detect** on the Subscriptions page to refresh recurring charge detection

## Project Structure

```
backend/
  routes/          # FastAPI endpoints
  analysis/        # Insights, categorization, subscription detection, merchant normalization
  search/          # Embedding-based semantic search
  parsers/         # CSV parsers per bank
  llm/             # LLM provider abstraction (Claude / Gemini)
  db/              # SQLAlchemy models and session

frontend/
  src/
    pages/         # Overview, Transactions, Categories, Insights, Subscriptions, SavingsTips
    api/           # API client
    components/    # Shared chart components
```

## Data Privacy

- The SQLite database (`finance.db`) is excluded from git via `.gitignore`
- Your CSV files (`transactions/`) are excluded from git
- API keys are stored in macOS Keychain, never in config files
- Transaction descriptions are sent to the Gemini API for enrichment — no other data leaves your machine

## LLM Models Used

| Task | Model |
|------|-------|
| Transaction enrichment | `gemini-3.1-flash-lite` |
| Savings tips | `gemini-3.1-pro-preview` |
| Embeddings (semantic search) | local `sentence-transformers` |
