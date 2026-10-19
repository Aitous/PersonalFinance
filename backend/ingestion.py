"""Shared ingestion identity and overlap reconciliation helpers."""
from collections import defaultdict
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models import Transaction
from backend.parsers.csv_parser import _make_id


def reconcile_account_overlaps(session: Session, transactions: list[Transaction]) -> dict[str, str]:
    """Map incoming row IDs to existing transaction IDs by account and occurrence.

    Match exact date/description/normalized amount. Occurrence counts ensure two
    identical purchases remain two records while overlapping exports stay idempotent.
    Legacy rows without an account are intentionally excluded as ambiguous.
    """
    grouped: dict[tuple, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.account_id:
            grouped[(tx.account_id, tx.date, tx.description.strip().casefold(), round(float(tx.amount), 2))].append(tx)
    remap: dict[str, str] = {}
    for (account_id, tx_date, description, amount), incoming in grouped.items():
        matches = session.execute(
            select(Transaction).where(
                Transaction.account_id == account_id,
                Transaction.date == tx_date,
                func.lower(Transaction.description) == description,
                Transaction.amount == amount,
            ).order_by(Transaction.id)
        ).scalars().all()
        matches_by_id = {row.id: row for row in matches}
        used_ids = set()
        # Reserve rows already carrying the same source identity before considering
        # cross-format matches. Distinct FITIDs identify distinct bank transactions.
        for row in incoming:
            if row.id in matches_by_id:
                used_ids.add(row.id)
        for row in incoming:
            if row.id in matches_by_id:
                continue
            candidate = next((existing for existing in matches
                if existing.id not in used_ids
                and not (row.bank_fitid and existing.bank_fitid)
                and (not row.bank_fitid or not existing.bank_fitid)), None)
            if candidate:
                used_ids.add(candidate.id)
                remap[row.id] = candidate.id
                row.id = candidate.id
    return remap


def reconcile_legacy_csv_ids(session: Session, transactions: list[Transaction]) -> dict[str, str]:
    """Remap unassigned first-occurrence CSV rows to proven sign-era legacy IDs.

    The old ID may hash the opposite amount sign while the stored transaction
    already has the normalized amount. Require source/date/description/amount and
    exact decoded raw-row equality. Malformed raw data and assigned accounts are
    skipped conservatively; this function never rewrites database rows.
    """
    remap: dict[str, str] = {}
    for tx in transactions:
        if tx.account_id is not None or not tx.raw_csv_row:
            continue
        current_id = _make_id(tx.source, tx.date, tx.description, tx.amount)
        if tx.id != current_id:
            continue  # repeated occurrences have distinct IDs and must remain distinct
        try:
            incoming_raw = json.loads(tx.raw_csv_row)
        except (TypeError, json.JSONDecodeError):
            continue
        legacy_id = _make_id(tx.source, tx.date, tx.description, -tx.amount)
        if legacy_id == tx.id:
            continue
        legacy = session.get(Transaction, legacy_id)
        if not legacy or not legacy.raw_csv_row:
            continue
        if (legacy.source, legacy.date, legacy.description, legacy.amount) != (
            tx.source, tx.date, tx.description, tx.amount
        ):
            continue
        try:
            legacy_raw = json.loads(legacy.raw_csv_row)
        except (TypeError, json.JSONDecodeError):
            continue
        if legacy_raw == incoming_raw:
            previous_id = tx.id
            tx.id = legacy.id
            remap[previous_id] = legacy.id
    return remap
