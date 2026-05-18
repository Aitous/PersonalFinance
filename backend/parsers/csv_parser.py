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
