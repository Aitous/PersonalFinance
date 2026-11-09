"""Reconcile detector output while retaining explicit user subscription choices."""
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from statistics import mean
from typing import Optional

from sqlalchemy import select

from backend.analysis.subscription_detector import AMOUNT_TOLERANCE_PCT, SubscriptionDetector, _normalize
from backend.analysis.transaction_semantics import is_payment, purchase_amount
from backend.db.models import Subscription, Transaction


def build_amount_profile(transactions, frequency: str, as_of: Optional[date] = None,
                         fallback_amount: float = 0.0) -> dict:
    """Summarize a recurring series using monthly totals, not single charges."""
    as_of = as_of or date.today()
    monthly_totals: dict[tuple[int, int], float] = defaultdict(float)
    annual_totals: dict[int, float] = defaultdict(float)
    charges = []
    for tx in transactions:
        if tx.date > as_of:
            continue
        amount = float(purchase_amount(tx))
        if amount <= 0 or is_payment(tx):
            continue
        monthly_totals[(tx.date.year, tx.date.month)] += amount
        annual_totals[tx.date.year] += amount
        charges.append((tx.date, amount))

    latest_charge = max(charges, key=lambda item: item[0])[1] if charges else float(fallback_amount)
    if frequency == "annual":
        latest_period = annual_totals[max(year for year in annual_totals)] if annual_totals else float(fallback_amount)
        prior_periods = [annual_totals[year] for year in sorted(annual_totals) if year < as_of.year][-6:]
        annual_amounts = prior_periods or ([latest_period] if annual_totals else [])
        average_monthly = (mean(annual_amounts) / 12) if annual_amounts else float(fallback_amount) / 12
        variation_amounts = annual_amounts
    else:
        latest_month = max(monthly_totals) if monthly_totals else None
        latest_period = monthly_totals[latest_month] if latest_month else float(fallback_amount)
        current_month = (as_of.year, as_of.month)
        prior_periods = [monthly_totals[month] for month in sorted(monthly_totals) if month < current_month][-6:]
        average_monthly = mean(prior_periods) if prior_periods else float(fallback_amount)
        variation_amounts = prior_periods
    amount_type = "fixed"
    if len(variation_amounts) > 1 and mean(variation_amounts) > 0:
        spread = (max(variation_amounts) - min(variation_amounts)) / mean(variation_amounts)
        if spread > AMOUNT_TOLERANCE_PCT:
            amount_type = "variable"

    return {
        "amount_type": amount_type,
        "average_monthly_amount": round(average_monthly, 2),
        "latest_charge_amount": round(latest_charge, 2),
        "latest_period_amount": round(latest_period, 2),
    }


def _name_key(value: Optional[str]) -> str:
    value = (value or "").strip().casefold()
    value = re.sub(r"\s*\(usage-based\)\s*$", "", value)
    value = re.sub(r"^www\.", "", value)
    value = re.sub(r"\.com$", "", value)
    return re.sub(r"[^a-z0-9]", "", value)


def _candidate_name_keys(candidate: Subscription, transactions_by_id: dict) -> set[str]:
    values = {candidate.description}
    for tx_id in _load_transaction_ids(candidate.supporting_transaction_ids):
        tx = transactions_by_id.get(tx_id)
        if tx:
            values.update((tx.description, tx.merchant_name))
            normalized = _normalize(tx.description or "")
            if normalized:
                values.add(normalized)
    return {key for value in values if (key := _name_key(value))}


def _charge_fingerprint(tx: Transaction) -> tuple:
    return (
        getattr(tx, "account_id", None),
        (getattr(tx, "source", "") or "").strip().casefold(),
        tx.date,
        round(float(purchase_amount(tx)), 2),
    )


def _load_transaction_ids(raw: Optional[str]) -> list[str]:
    try:
        values = json.loads(raw or "[]")
        return list(dict.fromkeys(value for value in values if isinstance(value, str))) if isinstance(values, list) else []
    except (TypeError, ValueError):
        return []


def is_effectively_active(subscription: Subscription, as_of: Optional[date] = None) -> bool:
    """Use a current recency window for automatic detections; preserve user choices."""
    if getattr(subscription, "dismissed", False):
        return False
    user_active = getattr(subscription, "user_active", None)
    if user_active is not None:
        return bool(user_active)
    origin = getattr(subscription, "origin", "legacy")
    if origin == "detected":
        if not getattr(subscription, "last_charged", None):
            return False
        days_since = ((as_of or date.today()) - subscription.last_charged).days
        return 0 <= days_since <= (40 if subscription.frequency == "monthly" else 400)
    return bool(getattr(subscription, "active", False))


def subscription_amount_profile(subscription: Subscription, transactions,
                                as_of: Optional[date] = None) -> dict:
    """Return one cost profile while keeping user-maintained amounts authoritative."""
    profile = build_amount_profile(
        transactions, subscription.frequency, as_of=as_of,
        fallback_amount=subscription.amount,
    )
    if subscription.origin in {"manual", "legacy"}:
        per_month = float(subscription.amount) / (12 if subscription.frequency == "annual" else 1)
        return {
            "amount_type": "fixed",
            "average_monthly_amount": round(per_month, 2),
            "latest_charge_amount": round(float(subscription.amount), 2),
            "latest_period_amount": round(float(subscription.amount), 2),
        }
    return profile


def reconcile_subscriptions(session, transactions=None) -> list[Subscription]:
    transactions = transactions if transactions is not None else session.execute(select(Transaction)).scalars().all()
    detected_rows = SubscriptionDetector().detect(list(transactions))
    existing = [row for row in session.execute(select(Subscription)).scalars().all()
                if isinstance(row, Subscription)]
    by_id = {sub.id: sub for sub in existing}
    transactions_by_id = {tx.id: tx for tx in transactions}
    live_transaction_ids = set(transactions_by_id)
    for sub in existing:
        old_ids = _load_transaction_ids(sub.supporting_transaction_ids)
        live_ids = [tx_id for tx_id in old_ids if tx_id in live_transaction_ids]
        if live_ids != old_ids:
            sub.supporting_transaction_ids = json.dumps(live_ids)
            linked_transactions = [transactions_by_id[tx_id] for tx_id in live_ids]
            if sub.last_charged and not any(tx.date == sub.last_charged for tx in linked_transactions):
                sub.last_charged = max((tx.date for tx in linked_transactions), default=None)

    # Match saved rows to one validated candidate by merchant evidence or by
    # strong overlap in their charge fingerprints. Requiring one candidate keeps
    # generic merchant labels from joining separate products or accounts.
    candidates_by_id = {candidate.id: candidate for candidate in detected_rows}
    candidate_keys = {candidate.id: _candidate_name_keys(candidate, transactions_by_id) for candidate in detected_rows}
    manual_match_by_candidate: dict[str, Subscription] = {}
    legacy_matches_by_candidate: dict[str, list[Subscription]] = defaultdict(list)
    for current in existing:
        if current.origin not in {"manual", "legacy"} or current.dismissed:
            continue
        key = _name_key(current.description)
        if not key:
            continue
        current_ids = _load_transaction_ids(current.supporting_transaction_ids)
        current_fingerprints = {
            _charge_fingerprint(transactions_by_id[tx_id])
            for tx_id in current_ids if tx_id in transactions_by_id
        }
        matches = []
        for candidate in detected_rows:
            candidate_ids = _load_transaction_ids(candidate.supporting_transaction_ids)
            candidate_fingerprints = {
                _charge_fingerprint(transactions_by_id[tx_id])
                for tx_id in candidate_ids if tx_id in transactions_by_id
            }
            overlap = len(current_fingerprints & candidate_fingerprints)
            name_match = key in candidate_keys[candidate.id]
            evidence_match = (
                current.origin == "legacy"
                and overlap >= 2
                and overlap / max(1, len(current_fingerprints)) >= 0.8
            )
            if name_match or evidence_match:
                matches.append(candidate)
        # A candidate can intentionally cover multiple bank descriptors once
        # text identity and charge timing establish that they form one series.
        if len(matches) == 1:
            candidate = matches[0]
            if current.origin == "legacy":
                legacy_matches_by_candidate[candidate.id].append(current)
            else:
                previous = manual_match_by_candidate.get(candidate.id)
                if previous is None or (
                    current.last_charged or date.min,
                    len(_load_transaction_ids(current.supporting_transaction_ids)),
                ) > (
                    previous.last_charged or date.min,
                    len(_load_transaction_ids(previous.supporting_transaction_ids)),
                ):
                    manual_match_by_candidate[candidate.id] = current

    linked_existing: set[str] = set()
    removed_detected: set[str] = set()
    manual_links: dict[str, set[str]] = defaultdict(set)
    new_candidates: list[Subscription] = []
    suppressed_candidates: set[str] = set()

    for candidate in detected_rows:
        candidate_ids = _load_transaction_ids(candidate.supporting_transaction_ids)
        legacy_matches = legacy_matches_by_candidate.get(candidate.id, [])
        current = manual_match_by_candidate.get(candidate.id) or by_id.get(candidate.id)
        if current is None and legacy_matches:
            current = max(legacy_matches, key=lambda row: (
                row.last_charged or date.min,
                len(_load_transaction_ids(row.supporting_transaction_ids)),
            ))
        if current is None:
            candidate_set = set(candidate_ids)
            overlap_candidates = []
            dismissed_overlap_candidates = []
            for row in existing:
                if row.origin != "detected" or row.id in linked_existing or row.id in removed_detected:
                    continue
                overlap = candidate_set.intersection(_load_transaction_ids(row.supporting_transaction_ids))
                if overlap:
                    target = dismissed_overlap_candidates if row.dismissed else overlap_candidates
                    target.append((len(overlap), row))
            if overlap_candidates:
                current = max(overlap_candidates, key=lambda item: item[0])[1]
            elif dismissed_overlap_candidates:
                current = max(dismissed_overlap_candidates, key=lambda item: item[0])[1]
        if current is not None:
            if current.dismissed:
                suppressed_candidates.add(candidate.id)
                candidate_set = set(candidate_ids)
                for duplicate in existing:
                    if duplicate is current or duplicate.origin != "detected" or duplicate.dismissed:
                        continue
                    if candidate_set.intersection(_load_transaction_ids(duplicate.supporting_transaction_ids)):
                        session.delete(duplicate)
                        removed_detected.add(duplicate.id)
                continue
            if current.origin == "manual":
                manual_links[current.id].update(candidate_ids)
                if candidate.last_charged and (current.last_charged is None or candidate.last_charged > current.last_charged):
                    current.last_charged = candidate.last_charged
                linked_existing.add(current.id)
                for duplicate in existing:
                    if duplicate.origin != "detected" or duplicate.dismissed:
                        continue
                    if duplicate.id == candidate.id or set(candidate_ids).intersection(_load_transaction_ids(duplicate.supporting_transaction_ids)):
                        session.delete(duplicate)
                        removed_detected.add(duplicate.id)
                continue
            if current.origin == "legacy":
                # Preserve imported legacy amounts and user active state.
                current.last_charged = candidate.last_charged
                current.active = bool(current.user_active) if current.user_active is not None else bool(candidate.active)
                current.supporting_transaction_ids = json.dumps(candidate_ids)
                linked_existing.add(current.id)
                for duplicate in legacy_matches:
                    if duplicate is current:
                        continue
                    if duplicate.user_active is not None and current.user_active is None:
                        current.user_active = duplicate.user_active
                        current.active = duplicate.user_active
                    session.delete(duplicate)
                    removed_detected.add(duplicate.id)
                continue
            current.description = candidate.description
            current.amount = candidate.amount
            current.frequency = candidate.frequency
            current.last_charged = candidate.last_charged
            current.supporting_transaction_ids = candidate.supporting_transaction_ids
            current.active = bool(current.user_active) if current.user_active is not None else bool(candidate.active)
            linked_existing.add(current.id)
            # Collapse older duplicate detected rows that refer to the same
            # evidence, carrying a user's active override onto the survivor.
            for duplicate in existing:
                if duplicate is current or duplicate.origin != "detected" or duplicate.dismissed:
                    continue
                if set(candidate_ids).intersection(_load_transaction_ids(duplicate.supporting_transaction_ids)):
                    if duplicate.user_active is not None and current.user_active is None:
                        current.user_active = duplicate.user_active
                        current.active = duplicate.user_active
                    session.delete(duplicate)
                    removed_detected.add(duplicate.id)
        else:
            session.add(candidate)
            new_candidates.append(candidate)

    for current in existing:
        if current.id in manual_links:
            linked = set(_load_transaction_ids(current.supporting_transaction_ids))
            linked.update(manual_links[current.id])
            current.supporting_transaction_ids = json.dumps(sorted(linked))

    for current in existing:
        if current.origin in {"manual", "legacy"} or current.dismissed or current.id in candidates_by_id or current.id in linked_existing:
            continue
        if current.origin == "detected" and current.user_active is None:
            # These rows are derived entirely from transaction patterns. Once
            # the detector no longer supports one, remove it so stale guesses
            # do not remain beside current candidates after a re-detection.
            removed_detected.add(current.id)
            session.delete(current)
            continue
        current.active = bool(current.user_active) if current.user_active is not None else False

    # Recompute the recurring filter marker from the persisted, non-dismissed
    # detector links so imports and re-detection cannot leave stale flags behind.
    linked_ids: set[str] = set()
    for sub in existing:
        if sub.dismissed or sub.id in removed_detected:
            continue
        linked_ids.update(_load_transaction_ids(sub.supporting_transaction_ids))
    for candidate in new_candidates:
        linked_ids.update(_load_transaction_ids(candidate.supporting_transaction_ids))
    for tx in transactions:
        tx.is_subscription = tx.id in linked_ids

    return [candidate for candidate in detected_rows if candidate.id not in suppressed_candidates]


def set_manual_active(subscription: Subscription, active: bool) -> None:
    subscription.user_active = active
    subscription.active = active

