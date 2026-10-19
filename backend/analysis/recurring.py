"""Reconcile detector output while retaining explicit user subscription choices."""
import json
from datetime import datetime, timezone

from sqlalchemy import select

from backend.analysis.subscription_detector import SubscriptionDetector
from backend.db.models import Subscription, Transaction


def reconcile_subscriptions(session, transactions=None) -> list[Subscription]:
    transactions = transactions if transactions is not None else session.execute(select(Transaction)).scalars().all()
    detected = {sub.id: sub for sub in SubscriptionDetector().detect(list(transactions))}
    existing = [row for row in session.execute(select(Subscription)).scalars().all()
                if isinstance(row, Subscription)]
    by_id = {sub.id: sub for sub in existing}
    transactions_by_id = {tx.id: tx for tx in transactions}
    linked_existing: set[str] = set()

    for sub_id, candidate in detected.items():
        current = by_id.get(sub_id)
        candidate_ids = json.loads(candidate.supporting_transaction_ids or "[]")
        unassigned_series = bool(candidate_ids) and all(
            transactions_by_id.get(tx_id) is not None and transactions_by_id[tx_id].account_id is None
            for tx_id in candidate_ids
        )
        if current is None and unassigned_series:
            current = next((row for row in existing
                if row.origin in {"manual", "legacy"} and not row.dismissed
                and row.frequency == candidate.frequency
                and row.description.strip().casefold() == candidate.description.strip().casefold()), None)
        if current is not None:
            if current.dismissed:
                continue
            if current.origin in {"manual", "legacy"}:
                # Preserve the user's or legacy row's values while attaching
                # links only when every matching observation has no account ID.
                if unassigned_series:
                    current.supporting_transaction_ids = candidate.supporting_transaction_ids
                    linked_existing.add(current.id)
                continue
            current.description = candidate.description
            current.amount = candidate.amount
            current.frequency = candidate.frequency
            current.last_charged = candidate.last_charged
            current.supporting_transaction_ids = candidate.supporting_transaction_ids
            current.active = bool(current.user_active) if current.user_active is not None else bool(candidate.active)
            linked_existing.add(current.id)
        else:
            session.add(candidate)

    for current in existing:
        if current.origin in {"manual", "legacy"} or current.dismissed or current.id in detected or current.id in linked_existing:
            continue
        current.active = bool(current.user_active) if current.user_active is not None else False

    # Recompute the recurring filter marker from the persisted, non-dismissed
    # detector links so imports and re-detection cannot leave stale flags behind.
    linked_ids: set[str] = set()
    for sub in existing:
        if sub.dismissed:
            continue
        if sub.supporting_transaction_ids:
            linked_ids.update(json.loads(sub.supporting_transaction_ids))
    for candidate in detected.values():
        if candidate.id not in by_id and candidate.supporting_transaction_ids:
            linked_ids.update(json.loads(candidate.supporting_transaction_ids))
    for tx in transactions:
        tx.is_subscription = tx.id in linked_ids

    return [sub for sub_id, sub in detected.items() if not (sub_id in by_id and by_id[sub_id].dismissed)]


def set_manual_active(subscription: Subscription, active: bool) -> None:
    subscription.user_active = active
    subscription.active = active

