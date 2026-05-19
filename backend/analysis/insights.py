import re
import statistics
from collections import defaultdict
from datetime import date
from typing import List

from backend.analysis.subscription_detector import (
    _normalize, MONTHLY_DAYS_MIN, MONTHLY_DAYS_MAX, ANNUAL_DAYS_MAX,
)
from backend.db.models import Transaction

# Strips payment terminal prefixes (Square, Toast, etc.) and store numbers
_PREFIXES = re.compile(r'^(?:SAMPAY|TST\*|SQ\s*\*|UEP\*|SP\s+)\s*', re.IGNORECASE)
_STORE_NUM = re.compile(r'\s*#\s*\d+.*$|\s+\d{5,}.*$')

def _normalize_merchant(description: str) -> str:
    """More aggressive normalization for merchant grouping in the breakdown view."""
    s = description.upper().strip()
    s = _PREFIXES.sub("", s).strip()   # strip terminal prefixes
    s = _normalize(s)                   # strip trailing IDs / noise
    s = _STORE_NUM.sub("", s).strip()   # strip store numbers like #0147
    return s


def get_spending_anomalies(txs: List[Transaction]) -> List[dict]:
    today = date.today()
    current_month = today.strftime("%Y-%m")

    by_cat_month: dict = defaultdict(lambda: defaultdict(list))
    for tx in txs:
        month_key = tx.date.strftime("%Y-%m")
        cat = tx.category or "other"
        by_cat_month[cat][month_key].append(tx.amount)

    anomalies = []
    for cat, months_data in by_cat_month.items():
        if current_month not in months_data:
            continue
        current_txs = months_data[current_month]
        if len(current_txs) < 3:
            continue
        current_amount = sum(current_txs)

        prior_months = sorted(m for m in months_data if m != current_month)
        if len(prior_months) < 3:
            continue
        recent_prior = prior_months[-3:]
        prior_totals = [sum(months_data[m]) for m in recent_prior]
        avg = sum(prior_totals) / len(prior_totals)

        if avg > 0 and current_amount / avg >= 2.0:
            anomalies.append({
                "category": cat,
                "current_amount": round(current_amount, 2),
                "avg_amount": round(avg, 2),
                "ratio": round(current_amount / avg, 2),
                "tx_count": len(current_txs),
            })

    return sorted(anomalies, key=lambda x: -x["ratio"])


def get_duplicate_charges(txs: List[Transaction]) -> List[dict]:
    groups: dict = defaultdict(list)
    for tx in txs:
        key = _normalize(tx.description)
        groups[key].append(tx)

    recurring: set = set()
    for key, merchant_txs in groups.items():
        if len(merchant_txs) >= 6:
            amounts = [t.amount for t in merchant_txs]
            avg = sum(amounts) / len(amounts)
            if avg > 0 and (max(amounts) - min(amounts)) / avg <= 0.15:
                recurring.add(key)

    duplicates = []
    for key, merchant_txs in groups.items():
        if key in recurring:
            continue
        sorted_txs = sorted(merchant_txs, key=lambda t: t.date)
        seen_pairs: set = set()
        for i, tx1 in enumerate(sorted_txs):
            for tx2 in sorted_txs[i + 1:]:
                days_apart = (tx2.date - tx1.date).days
                if days_apart > 3:
                    break
                if abs(tx1.amount - tx2.amount) < 0.01:
                    pair_key = (round(tx1.amount, 2), tx1.date.isoformat())
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        duplicates.append({
                            "merchant": key,
                            "amount": round(tx1.amount, 2),
                            "dates": [tx1.date.isoformat(), tx2.date.isoformat()],
                            "sources": list({tx1.source, tx2.source}),
                        })
    return duplicates


def get_price_increases(txs: List[Transaction]) -> List[dict]:
    groups: dict = defaultdict(list)
    for tx in txs:
        key = _normalize(tx.description)
        groups[key].append(tx)

    increases = []
    for key, merchant_txs in groups.items():
        if len(merchant_txs) < 6:
            continue
        sorted_txs = sorted(merchant_txs, key=lambda t: t.date)

        gaps = [
            (sorted_txs[i + 1].date - sorted_txs[i].date).days
            for i in range(len(sorted_txs) - 1)
        ]
        avg_gap = sum(gaps) / len(gaps)
        if not (MONTHLY_DAYS_MIN <= avg_gap <= ANNUAL_DAYS_MAX):
            continue

        prior = sorted_txs[:-2]
        recent = sorted_txs[-2:]
        if not prior:
            continue

        prior_amounts = [t.amount for t in prior]
        prior_avg = sum(prior_amounts) / len(prior_amounts)
        prior_variance = (max(prior_amounts) - min(prior_amounts)) / prior_avg if prior_avg > 0 else 1.0
        # Skip merchants with variable prior amounts — they're not subscriptions
        if prior_variance > 0.10:
            continue

        prior_median = statistics.median(prior_amounts)
        last_amount = recent[-1].amount

        if prior_median > 0 and (last_amount - prior_median) / prior_median > 0.05:
            increases.append({
                "merchant": key,
                "old_amount": round(prior_median, 2),
                "new_amount": round(last_amount, 2),
                "delta": round(last_amount - prior_median, 2),
                "first_new_date": recent[-1].date.isoformat(),
            })

    return increases


def get_merchant_breakdown(txs: List[Transaction]) -> List[dict]:
    groups: dict = defaultdict(list)
    for tx in txs:
        key = tx.merchant_name if tx.merchant_name else _normalize_merchant(tx.description)
        groups[key].append(tx)

    merchants = []
    for name, merchant_txs in groups.items():
        total = sum(t.amount for t in merchant_txs)
        last_date = max(t.date for t in merchant_txs)
        cat_counts: dict = defaultdict(int)
        for t in merchant_txs:
            cat_counts[t.category or "other"] += 1
        top_cat = max(cat_counts, key=lambda k: cat_counts[k])
        type_counts: dict = defaultdict(int)
        for t in merchant_txs:
            if t.merchant_type:
                type_counts[t.merchant_type] += 1
        top_type = max(type_counts, key=lambda k: type_counts[k]) if type_counts else None
        merchants.append({
            "name": name,
            "total": round(total, 2),
            "tx_count": len(merchant_txs),
            "category": top_cat,
            "merchant_type": top_type,
            "last_date": last_date.isoformat(),
        })

    return sorted(merchants, key=lambda x: -x["total"])


def get_day_of_week(txs: List[Transaction]) -> dict:
    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    totals: dict = defaultdict(float)
    counts: dict = defaultdict(int)

    for tx in txs:
        dow = tx.date.weekday()
        totals[dow] += tx.amount
        counts[dow] += 1

    total_all = sum(totals.values())
    weekend_total = totals[5] + totals[6]
    weekend_pct = round(weekend_total / total_all * 100, 1) if total_all > 0 else 0.0

    return {
        "days": [
            {
                "day": i,
                "day_name": DAY_NAMES[i],
                "total": round(totals[i], 2),
                "tx_count": counts[i],
                "avg_per_tx": round(totals[i] / counts[i], 2) if counts[i] > 0 else 0.0,
            }
            for i in range(7)
        ],
        "weekend_pct": weekend_pct,
    }


def get_year_over_year(txs: List[Transaction]) -> dict:
    today = date.today()
    by_year_cat: dict = defaultdict(lambda: defaultdict(float))

    for tx in txs:
        by_year_cat[tx.date.year][tx.category or "other"] += tx.amount

    years_present = sorted(by_year_cat.keys())
    if len(years_present) < 2:
        return {"insufficient_data": True, "years": [], "on_pace": None, "on_pace_pct_change": None}

    years_to_show = years_present[-2:]
    years_data = []
    for y in years_to_show:
        cats = dict(by_year_cat[y])
        total = sum(cats.values())
        years_data.append({
            "year": y,
            "total": round(total, 2),
            "categories": {k: round(v, 2) for k, v in cats.items()},
        })

    on_pace = None
    on_pace_pct_change = None
    if years_to_show[-1] == today.year:
        day_of_year = today.timetuple().tm_yday
        ytd = sum(by_year_cat[today.year].values())
        on_pace = round(ytd / day_of_year * 365, 2)
        prior_total = sum(by_year_cat[years_to_show[0]].values())
        if prior_total > 0:
            on_pace_pct_change = round((on_pace - prior_total) / prior_total * 100, 1)

    return {
        "insufficient_data": False,
        "years": years_data,
        "on_pace": on_pace,
        "on_pace_pct_change": on_pace_pct_change,
    }
