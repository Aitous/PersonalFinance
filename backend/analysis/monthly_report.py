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

    all_cats = set(current_by_cat) | set(prior_by_cat)
    categories = sorted(
        [
            {
                "name": cat,
                "current": round(current_by_cat[cat], 2),
                "prior": round(prior_by_cat[cat], 2),
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


def get_subscriptions_due(subs, report_month_end: date) -> list:
    """Return active renewals before the end of the next calendar month."""
    window_end = _add_months_clamped(report_month_end, 1)

    due = []
    for sub in subs:
        if not sub.active or sub.last_charged is None:
            continue
        if sub.frequency == "monthly":
            next_date = _add_months_clamped(sub.last_charged, 1)
        elif sub.frequency == "annual":
            next_date = _add_year_clamped(sub.last_charged)
        else:
            continue
        if report_month_end < next_date <= window_end:
            due.append({
                "description": sub.description,
                "amount": sub.amount,
                "next_date": next_date.isoformat(),
            })

    return sorted(due, key=lambda x: x["next_date"])
