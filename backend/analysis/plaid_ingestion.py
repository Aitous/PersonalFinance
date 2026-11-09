"""Apply Plaid transaction deltas to the local ledger conservatively."""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Account, PlaidTransactionIdentity, Transaction
from backend.ingestion import namespace_transaction_ids
from backend.auth import current_owner_id


def _source_for_institution(institution_name: str) -> str:
    value = re.sub(r"[^a-z]+", " ", (institution_name or "").casefold()).strip()
    if "discover" in value:
        return "discover"
    if "american express" in value or value == "amex":
        return "amex"
    if "chase" in value or "jpmorgan" in value:
        return "chase"
    return "plaid"


def _normalize(value: str | None) -> str:
    return "".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def _descriptions_match(existing: Transaction, incoming: dict[str, Any]) -> bool:
    old_values = {_normalize(existing.description), _normalize(existing.merchant_name)} - {""}
    new_values = {_normalize(incoming.get(key)) for key in ("name", "original_description", "merchant_name")}
    new_values.discard("")
    for old in old_values:
        for new in new_values:
            if old == new:
                return True
            shorter, longer = sorted((old, new), key=len)
            if len(shorter) >= 8 and longer.startswith(shorter):
                return True
    return False


def _account_for(session: Session, environment: str, source: str,
                 account_id: str, account_info: dict[str, Any]) -> Account:
    external_id = f"plaid:{environment}:{account_id}"
    account = session.execute(select(Account).where(Account.external_id == external_id)).scalar_one_or_none()
    if account:
        return account
    mask = account_info.get("mask")
    account = Account(
        id=f"plaid:{environment}:{account_id}", bank=source,
        name=account_info.get("name") or "Plaid account",
        last4=mask if isinstance(mask, str) and len(mask) == 4 and mask.isdigit() else None,
        external_id=external_id,
    )
    session.add(account)
    session.flush()
    return account


def _identity(session: Session, environment: str, transaction_id: str) -> PlaidTransactionIdentity | None:
    return session.get(PlaidTransactionIdentity, (current_owner_id(), environment, transaction_id))


def _manual_fields(tx: Transaction) -> set[str]:
    try:
        fields = json.loads(tx.manual_fields or "[]")
        return set(fields) if isinstance(fields, list) else set()
    except (TypeError, json.JSONDecodeError):
        return set()


def _remove_pending_predecessor(session: Session, environment: str, pending_id: str | None) -> bool:
    if not pending_id:
        return False
    identity = _identity(session, environment, pending_id)
    if not identity:
        return False
    tx = session.get(Transaction, identity.transaction_id)
    deleted = bool(identity.plaid_owned and tx and not tx.manual_category and not _manual_fields(tx))
    if deleted:
        session.delete(tx)
    session.delete(identity)
    return deleted


def _plaid_row_id(environment: str, plaid_transaction_id: str) -> str:
    return f"plaid:{environment}:{plaid_transaction_id}"


def _find_csv_overlap(session: Session, source: str, tx_date: date, amount: float,
                      incoming: dict[str, Any], claimed: set[str],
                      plaid_account: Account) -> Transaction | None:
    """Find a unique date/amount/merchant match; ambiguity is never auto-merged."""
    if source == "plaid":
        return None
    candidates = session.execute(select(Transaction).where(
        Transaction.source == source, Transaction.date == tx_date,
        Transaction.id.not_in(claimed) if claimed else Transaction.id.is_not(None),
    )).scalars().all()
    # Rounded comparison avoids depending on SQLite float equality.
    account_filtered = []
    for tx in candidates:
        if tx.account_id and tx.account_id != plaid_account.id:
            previous_account = session.get(Account, tx.account_id)
            if (not previous_account or not plaid_account.last4
                    or previous_account.last4 != plaid_account.last4):
                continue
        account_filtered.append(tx)
    candidates = [tx for tx in account_filtered if round(float(tx.amount), 2) == round(amount, 2)
                  and not tx.id.startswith("plaid:") and _descriptions_match(tx, incoming)]
    return candidates[0] if len(candidates) == 1 else None


def apply_transaction_deltas(
    session: Session,
    *,
    environment: str,
    item_id: str,
    institution_name: str,
    accounts: list[dict[str, Any]],
    added: list[dict[str, Any]],
    modified: list[dict[str, Any]],
    removed: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply one fully-paginated sync; caller owns the transaction/commit."""
    source = _source_for_institution(institution_name)
    accounts_by_id = {row.get("account_id"): row for row in accounts if row.get("account_id")}
    claimed_csv_ids: set[str] = set()
    counts = {"imported": 0, "duplicates": 0, "modified": 0, "removed": 0}
    new_ids: list[str] = []

    for row in added:
        plaid_id = row.get("transaction_id")
        if not isinstance(plaid_id, str) or not plaid_id or row.get("pending"):
            continue
        if _remove_pending_predecessor(session, environment, row.get("pending_transaction_id")):
            counts["removed"] += 1
        if _identity(session, environment, plaid_id):
            continue
        account_ref = row.get("account_id")
        if not isinstance(account_ref, str) or not account_ref:
            continue
        account_info = accounts_by_id.get(account_ref, {"name": "Plaid account"})
        account = _account_for(session, environment, source, account_ref, account_info)
        tx_date = date.fromisoformat(row["date"])
        amount = round(float(row["amount"]), 2)
        duplicate = _find_csv_overlap(session, source, tx_date, amount, row,
                                      claimed_csv_ids, account)
        if duplicate:
            claimed_csv_ids.add(duplicate.id)
            session.add(PlaidTransactionIdentity(
                environment=environment, plaid_transaction_id=plaid_id, item_id=item_id,
                account_id=account.id, transaction_id=duplicate.id, plaid_owned=False,
            ))
            counts["duplicates"] += 1
            continue

        local_id = _plaid_row_id(environment, plaid_id)
        description = row.get("original_description") or row.get("name") or row.get("merchant_name") or "Plaid transaction"
        tx = Transaction(
            id=local_id, source=source, date=tx_date, description=str(description), amount=amount,
            category="other", merchant_name=row.get("merchant_name"), account_id=account.id,
            original_amount=amount, amount_minor=round(amount * 100),
            currency=row.get("iso_currency_code") or row.get("unofficial_currency_code"),
            kind="purchase" if amount >= 0 else "refund", enrichment_status=None,
        )
        namespace_transaction_ids([tx])
        local_id = tx.id
        session.add(tx)
        session.add(PlaidTransactionIdentity(
            environment=environment, plaid_transaction_id=plaid_id, item_id=item_id,
            account_id=account.id, transaction_id=local_id, plaid_owned=True,
        ))
        new_ids.append(local_id)
        counts["imported"] += 1

    for row in modified:
        plaid_id = row.get("transaction_id")
        if not isinstance(plaid_id, str):
            continue
        identity = _identity(session, environment, plaid_id)
        tx = session.get(Transaction, identity.transaction_id) if identity else None
        if not identity or not identity.plaid_owned or not tx:
            continue
        tx_date = date.fromisoformat(row["date"])
        amount = round(float(row["amount"]), 2)
        tx.date = tx_date
        tx.amount = amount
        tx.kind = "purchase" if amount >= 0 else "refund"
        tx.original_amount = amount
        tx.amount_minor = round(amount * 100)
        tx.currency = row.get("iso_currency_code") or row.get("unofficial_currency_code") or tx.currency
        tx.description = str(row.get("original_description") or row.get("name") or tx.description)
        account_ref = row.get("account_id")
        if isinstance(account_ref, str) and account_ref:
            account_info = accounts_by_id.get(account_ref, {"name": "Plaid account"})
            account = _account_for(session, environment, source, account_ref, account_info)
            tx.account_id = account.id
            identity.account_id = account.id
        if "merchant_name" not in _manual_fields(tx) and row.get("merchant_name"):
            tx.merchant_name = row.get("merchant_name")
        if not tx.manual_category:
            tx.category = tx.category or "other"
        counts["modified"] += 1

    for row in removed:
        plaid_id = row.get("transaction_id")
        if not isinstance(plaid_id, str):
            continue
        identity = _identity(session, environment, plaid_id)
        if not identity:
            continue
        tx = session.get(Transaction, identity.transaction_id)
        if identity.plaid_owned and tx and not tx.manual_category and not _manual_fields(tx):
            session.delete(tx)
            counts["removed"] += 1
        session.delete(identity)

    return {**counts, "new_transaction_ids": new_ids}
