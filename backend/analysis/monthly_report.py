from collections import defaultdict
from datetime import date, timedelta
from typing import List
from backend.db.models import Transaction


def get_monthly_report_data(txs: List[Transaction], year: int, month: int) -> dict:
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

    total = round(sum(t.amount for t in current_txs), 2)
    prev_total = round(sum(t.amount for t in prior_txs), 2)
    tx_count = len(current_txs)

    # Categories: include only categories with spending in current month
    current_by_cat: dict = defaultdict(float)
    for t in current_txs:
        current_by_cat[t.category or "other"] += t.amount

    prior_by_cat: dict = defaultdict(float)
    for t in prior_txs:
        prior_by_cat[t.category or "other"] += t.amount

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
        merchant_totals[name] += t.amount

    merchants = sorted(
        [{"name": k, "total": round(v, 2)} for k, v in merchant_totals.items()],
        key=lambda x: -x["total"],
    )[:8]

    return {
        "year": year,
        "month": month,
        "total": total,
        "prev_total": prev_total,
        "tx_count": tx_count,
        "categories": categories,
        "merchants": merchants,
    }
