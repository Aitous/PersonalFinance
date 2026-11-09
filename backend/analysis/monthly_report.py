from __future__ import annotations

from collections import defaultdict
from datetime import date
import calendar
from typing import List
from backend.db.models import Transaction
from backend.analysis.transaction_semantics import purchase_amount, refund_amount


def get_monthly_report_data(txs: List[Transaction], year: int, month: int,
                            merchant_aliases: dict[str, str] | None = None) -> dict:
    """
    Pure function — computes all report fields except the AI narrative.
    Accepts a pre-filtered list of spending transactions (no payments, amount > 0).
    """
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1

    current_txs = [t for t in txs if t.date.year == year and t.date.month == month]
    prior_txs = [t for t in txs if t.date.year == prev_year and t.date.month == prev_month]
    gross = lambda rows: round(sum(float(purchase_amount(t)) for t in rows), 2)
    refunds = lambda rows: round(sum(float(refund_amount(t)) for t in rows), 2)
    total = gross(current_txs)  # legacy field remains gross purchases
    prev_total = gross(prior_txs)
    tx_count = sum(purchase_amount(t) > 0 for t in current_txs)

    # Categories: include only categories with spending in current month
    current_by_cat: dict = defaultdict(float)
    for t in current_txs:
        current_by_cat[t.category or "other"] += float(purchase_amount(t))

    prior_by_cat: dict = defaultdict(float)
    for t in prior_txs:
        prior_by_cat[t.category or "other"] += float(purchase_amount(t))

    # The recent baseline is fixed to the three calendar months immediately
    # before the selected month; missing months are never backfilled from older data.
    recent_months: list[dict] = []
    recent_month_lookup: dict[str, dict] = {}
    for offset in (3, 2, 1):
        month_index = year * 12 + month - 1 - offset
        recent_year, zero_based_month = divmod(month_index, 12)
        recent_month = zero_based_month + 1
        month_key = f"{recent_year:04d}-{recent_month:02d}"
        entry = {
            "month": month_key,
            "observed_activity": False,
            "transaction_count": 0,
            "source_counts": defaultdict(int),
            "gross_purchases": 0.0,
            "category_totals": defaultdict(float),
        }
        recent_months.append(entry)
        recent_month_lookup[month_key] = entry

    for tx in txs:
        entry = recent_month_lookup.get(tx.date.strftime("%Y-%m"))
        if entry is None:
            continue
        purchase = float(purchase_amount(tx))
        refund = float(refund_amount(tx))
        if purchase <= 0 and refund <= 0:
            continue
        entry["observed_activity"] = True
        entry["transaction_count"] += 1
        entry["source_counts"][tx.source or "unknown"] += 1
        if purchase > 0:
            entry["gross_purchases"] += purchase
            entry["category_totals"][tx.category or "other"] += purchase

    recent_three_months_all_observed = all(entry["observed_activity"] for entry in recent_months)
    recent_three_month_months = [
        {
            "month": entry["month"],
            "observed_activity": entry["observed_activity"],
            "transaction_count": entry["transaction_count"],
            "source_counts": dict(entry["source_counts"]),
        }
        for entry in recent_months
    ]

    # Compare a selected month with the other observed calendar months. Including
    # the selected month in its own baseline pulls the comparison toward zero.
    baseline_txs = [t for t in txs if not (t.date.year == year and t.date.month == month)]
    observed_dates = [t.date for t in txs if purchase_amount(t) > 0 or refund_amount(t) > 0]
    baseline_dates = [t.date for t in baseline_txs if purchase_amount(t) > 0 or refund_amount(t) > 0]
    if observed_dates and baseline_dates:
        earliest = min(observed_dates)
        latest = max(observed_dates)
        month_span = (latest.year - earliest.year) * 12 + latest.month - earliest.month + 1
        selected_in_span = (earliest.year, earliest.month) <= (year, month) <= (latest.year, latest.month)
        average_month_count = month_span - int(selected_in_span)
        baseline_earliest = min(baseline_dates)
        baseline_latest = max(baseline_dates)
        average_period_start = f"{baseline_earliest.year:04d}-{baseline_earliest.month:02d}"
        average_period_end = f"{baseline_latest.year:04d}-{baseline_latest.month:02d}"
    else:
        average_period_start = None
        average_period_end = None
        average_month_count = 0

    all_data_by_cat: dict = defaultdict(float)
    all_data_total = 0.0
    for t in baseline_txs:
        purchase = float(purchase_amount(t))
        if purchase > 0:
            all_data_by_cat[t.category or "other"] += purchase
            all_data_total += purchase

    all_cats = set(current_by_cat) | set(prior_by_cat) | set(all_data_by_cat)
    categories = sorted(
        [
            {
                "name": cat,
                "current": round(current_by_cat[cat], 2),
                "prior": round(prior_by_cat[cat], 2),
                "recent_three_month_average": round(
                    sum(entry["category_totals"].get(cat, 0.0) for entry in recent_months) / 3, 2,
                ) if recent_three_months_all_observed else None,
                "all_data_monthly_average": round(all_data_by_cat[cat] / average_month_count, 2) if average_month_count else None,
            }
            for cat in all_cats
        ],
        key=lambda x: -x["current"],
    )

    # Top 8 merchants by spend in current month
    merchant_totals: dict = defaultdict(float)
    for t in current_txs:
        name = t.merchant_name if t.merchant_name else (t.description or "Unknown").upper().strip()
        if merchant_aliases:
            seen = set()
            while name in merchant_aliases and name not in seen:
                seen.add(name)
                name = merchant_aliases[name]
        purchase = float(purchase_amount(t))
        if purchase > 0:
            merchant_totals[name] += purchase

    merchants = sorted(
        [{"name": k, "total": round(v, 2)} for k, v in merchant_totals.items()],
        key=lambda x: -x["total"],
    )[:8]

    return {
        "year": year,
        "month": month,
        "total": total,
        "gross_purchases": total,
        "refunds": refunds(current_txs),
        "net_spending": round(total - refunds(current_txs), 2),
        "prev_total": prev_total,
        "prev_gross_purchases": prev_total,
        "prev_refunds": refunds(prior_txs),
        "prev_net_spending": round(prev_total - refunds(prior_txs), 2),
        "all_data_monthly_average": round(all_data_total / average_month_count, 2) if average_month_count else None,
        "average_period_start": average_period_start,
        "average_period_end": average_period_end,
        "average_month_count": average_month_count,
        "recent_three_months": recent_three_month_months,
        "recent_three_months_all_observed": recent_three_months_all_observed,
        "recent_three_month_average_total": round(
            sum(entry["gross_purchases"] for entry in recent_months) / 3, 2,
        ) if recent_three_months_all_observed else None,
        "tx_count": tx_count,
        "categories": categories,
        "merchants": merchants,
    }


def _add_months_clamped(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    if year > date.max.year:
        return date.max
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _add_year_clamped(value: date) -> date:
    if value.year == date.max.year:
        return date.max
    year = value.year + 1
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return date(year, value.month, day)


def get_subscriptions_due(subs, report_month_end: date, transactions=None) -> list:
    """Return active renewals before the end of the next calendar month."""
    import json
    from backend.analysis.recurring import is_effectively_active, subscription_amount_profile

    window_end = _add_months_clamped(report_month_end, 1)
    transactions_by_id = {tx.id: tx for tx in (transactions or [])}

    due = []
    for sub in subs:
        if not is_effectively_active(sub, as_of=report_month_end) or sub.last_charged is None:
            continue
        if sub.frequency == "monthly":
            next_date = _add_months_clamped(sub.last_charged, 1)
        elif sub.frequency == "annual":
            next_date = _add_year_clamped(sub.last_charged)
        else:
            continue
        if report_month_end < next_date <= window_end:
            try:
                evidence_ids = json.loads(sub.supporting_transaction_ids or "[]")
                evidence_ids = evidence_ids if isinstance(evidence_ids, list) else []
            except (TypeError, ValueError):
                evidence_ids = []
            evidence = [transactions_by_id[tx_id] for tx_id in evidence_ids if tx_id in transactions_by_id]
            profile = subscription_amount_profile(sub, evidence, as_of=report_month_end)
            due.append({
                "description": sub.description,
                "amount": profile["latest_period_amount"],
                "next_date": next_date.isoformat(),
            })

    return sorted(due, key=lambda x: x["next_date"])
