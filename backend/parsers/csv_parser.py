import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional

from backend.db.models import Transaction

BANK_SCHEMAS = {
    "chase": {"date_col": "Transaction Date", "description_col": "Description", "amount_col": "Amount", "date_fmt": "%m/%d/%Y", "extra_cols": ["Category", "Type", "Memo"]},
    "discover": {"date_col": "Trans. Date", "description_col": "Description", "amount_col": "Amount", "date_fmt": "%m/%d/%Y", "extra_cols": ["Category"]},
    "amex": {"date_col": "Date", "description_col": "Description", "amount_col": "Amount", "date_fmt": "%m/%d/%Y", "extra_cols": ["Category", "City/State", "Country"]},
}


def _make_id(source: str, tx_date: date, description: str, amount: float) -> str:
    raw = f"{source}:{tx_date.isoformat()}:{description}:{amount:.2f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def stable_transaction_id(source: str, tx_date: date, description: str, amount: float,
                          account_id: Optional[str], occurrence: int = 1, fitid: Optional[str] = None) -> str:
    """Stable identity scoped to an account, preserving repeated same-day rows."""
    if fitid:
        identity = f"{source}:{account_id or ''}:fitid:{fitid}"
    elif account_id:
        identity = f"{source}:{account_id}:{tx_date.isoformat()}:{description.strip().casefold()}:{amount:.2f}:{occurrence}"
    elif occurrence == 1:
        return _make_id(source, tx_date, description, amount)  # retain legacy IDs
    else:
        identity = f"{source}:unassigned:{tx_date.isoformat()}:{description.strip().casefold()}:{amount:.2f}:{occurrence}"
    return hashlib.sha256(identity.encode()).hexdigest()[:16]


def normalize_amount(source: str, raw_amount: Decimal, *, ofx: bool = False) -> Decimal:
    """Normalize CSV/OFX signs to positive purchases and negative credits."""
    return -raw_amount if ofx or source == "chase" else raw_amount


def classify_kind(
    description: str,
    transaction_type: str = "",
    category: str = "",
    amount: Optional[float] = None,
) -> str:
    """Classify from normalized sign and explicit bank type/payment wording.

    `category` is accepted for compatibility with the prior call signature but
    deliberately ignored: merchant/category substrings such as RETURN or REWARD
    are not evidence that a transaction is a credit.
    """
    kind_type = re.sub(r"[^a-z]+", " ", (transaction_type or "").casefold()).strip()
    words = set(re.findall(r"[a-z]+", (description or "").casefold()))
    payment_words = {"payment", "autopay", "directpay", "epay"}
    payment_phrase = bool(words & payment_words) or {"direct", "pay"} <= words
    transfer_phrase = "transfer" in words
    explicit = {
        "payment": "payment", "pmt": "payment", "transfer": "transfer", "xfer": "transfer",
        "refund": "refund", "return": "refund", "credit": "refund",
        "sale": "purchase", "debit": "purchase", "purchase": "purchase", "charge": "purchase",
        "pos": "purchase",
    }.get(kind_type)

    if explicit in {"payment", "transfer"}:
        kind = explicit
    elif amount is not None and amount > 0:
        kind = explicit or "purchase"
    elif amount is not None and amount < 0:
        if payment_phrase:
            kind = "payment"
        elif transfer_phrase:
            kind = "transfer"
        elif explicit == "purchase":
            kind = explicit
        else:
            kind = explicit or "refund"
    elif explicit is not None:
        kind = explicit
    elif payment_phrase:
        kind = "payment"
    elif transfer_phrase:
        kind = "transfer"
    else:
        kind = "purchase"

    if amount is not None:
        if kind in {"payment", "refund"} and amount > 0:
            raise ValueError(f"{kind} type has a positive normalized amount")
        if kind == "purchase" and amount < 0:
            raise ValueError("purchase type has a negative normalized amount")
    return kind


@dataclass
class ParseResult:
    transactions: List[Transaction]
    input_rows: int
    errors: list[dict]
    warnings: list[str]
    checksum: str

    @property
    def parsed_rows(self) -> int:
        return len(self.transactions)


def parse_csv_detailed(file_path: Path, source: str, account_id: Optional[str] = None) -> ParseResult:
    if source not in BANK_SCHEMAS:
        raise ValueError(f"Unknown source '{source}'. Valid sources: {list(BANK_SCHEMAS.keys())}")
    path = Path(file_path)
    content = path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    text_content = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text_content, newline=""))
    schema = BANK_SCHEMAS[source]
    required = (schema["date_col"], schema["description_col"], schema["amount_col"])
    if not reader.fieldnames:
        raise ValueError("CSV is empty or has no header row")
    normalized = {h.strip(): h for h in reader.fieldnames if h}
    missing = [column for column in required if column not in normalized]
    if missing:
        raise ValueError(f"Invalid {source} CSV headers; missing: {', '.join(missing)}")

    transactions: list[Transaction] = []
    errors: list[dict] = []
    occurrences: dict[tuple, int] = {}
    input_rows = 0
    while True:
        row = next(reader, None)
        if row is None:
            break
        row_number = reader.line_num
        if not row or not any((v or "").strip() for v in row.values() if isinstance(v, str)):
            continue
        input_rows += 1
        try:
            raw_date = (row.get(normalized[schema["date_col"]]) or "").strip()
            description = (row.get(normalized[schema["description_col"]]) or "").strip()
            raw_amount_text = (row.get(normalized[schema["amount_col"]]) or "").strip().replace(",", "").replace("$", "")
            if not description:
                raise ValueError("description is empty")
            tx_date = datetime.strptime(raw_date, schema["date_fmt"]).date()
            original_amount = Decimal(raw_amount_text)
            kind = (row.get("Type") or "").strip()
            category = (row.get("Category") or "").strip()
            amount_decimal = normalize_amount(source, original_amount)
            amount = float(amount_decimal)
            if not original_amount.is_finite():
                raise ValueError("amount is not finite")
            if original_amount != original_amount.quantize(Decimal("0.01")):
                raise ValueError("amount has more than two decimal places")
            tx_kind = classify_kind(description, kind, category, amount)
        except (ValueError, InvalidOperation, KeyError) as exc:
            errors.append({"row_number": row_number, "reason": str(exc) or "invalid date or amount",
                           "raw_data": json.dumps(dict(row), ensure_ascii=False)})
            continue

        metadata = {col: (row.get(col) or "").strip() for col in schema["extra_cols"] if (row.get(col) or "").strip()}
        fitid = (row.get("FITID") or row.get("FitID") or "").strip() or None
        key = (tx_date, description.casefold(), amount)
        occurrences[key] = occurrences.get(key, 0) + 1
        tx = Transaction(
            id=stable_transaction_id(source, tx_date, description, amount, account_id, occurrences[key], fitid),
            source=source, date=tx_date, description=description, amount=amount,
            account_id=account_id, original_amount=float(original_amount),
            amount_minor=int((amount_decimal * 100).quantize(Decimal("1"))), currency="USD",
            bank_fitid=fitid, metadata_=json.dumps(metadata) if metadata else None,
            kind=tx_kind,
            raw_csv_row=json.dumps(dict(row), ensure_ascii=False),
        )
        tx._import_row_number = row_number
        transactions.append(tx)

    if input_rows == 0:
        raise ValueError("CSV contains no transaction rows")
    if not transactions:
        raise ValueError("CSV contains no valid transaction rows")
    warnings = [] if account_id else ["Transactions will be imported without an assigned account."]
    return ParseResult(transactions, input_rows, errors, warnings, checksum)


def parse_csv(file_path: Path, source: str, account_id: Optional[str] = None) -> List[Transaction]:
    return parse_csv_detailed(file_path, source, account_id).transactions
