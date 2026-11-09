"""Shared ingestion identity and overlap reconciliation helpers."""
from collections import defaultdict
import json
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models import Transaction
from backend.parsers.csv_parser import _make_id
from backend.auth import current_owner_id


def namespace_transaction_ids(transactions: list[Transaction]) -> None:
    """Keep globally-primary-keyed transaction IDs unique across accounts."""
    owner_id = current_owner_id()
    if owner_id == "local-owner":
        return
    prefix = f"{owner_id}:"
    for tx in transactions:
        if tx.id and not tx.id.startswith(prefix):
            tx.id = prefix + tx.id


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


def reconcile_unassigned_description_overlaps(session: Session, transactions: list[Transaction]) -> dict[str, str]:
    """Match unassigned CSV rows when a bank export truncates the description.

    This conservative fallback requires the same bank, date, amount, no account or
    FITID, and one description to be a prefix of the other after whitespace folding.
    A stored row can satisfy only one incoming row, preserving repeated purchases.
    """
    grouped: dict[tuple, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        if tx.account_id is None and not tx.bank_fitid:
            grouped[(tx.source, tx.date, round(float(tx.amount), 2))].append(tx)

    def normalize_description(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip()).casefold()

    remap: dict[str, str] = {}
    for (source, tx_date, amount), incoming in grouped.items():
        existing = session.execute(
            select(Transaction).where(
                Transaction.source == source,
                Transaction.account_id.is_(None),
                Transaction.bank_fitid.is_(None),
                Transaction.date == tx_date,
                Transaction.amount == amount,
            ).order_by(Transaction.id)
        ).scalars().all()
        used_ids = set()
        existing_by_id = {row.id: row for row in existing}
        for row in incoming:
            if row.id in existing_by_id:
                used_ids.add(row.id)
        for row in incoming:
            if row.id in existing_by_id:
                continue
            incoming_description = normalize_description(row.description)
            if len(incoming_description) < 5:
                continue
            candidates = [old for old in existing if old.id not in used_ids and (
                normalize_description(old.description).startswith(incoming_description)
                or incoming_description.startswith(normalize_description(old.description))
            )]
            if len(candidates) == 1:
                old = candidates[0]
                used_ids.add(old.id)
                remap[row.id] = old.id
                row.id = old.id
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
