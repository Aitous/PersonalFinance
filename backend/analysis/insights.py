from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date
from typing import List

from backend.analysis.subscription_detector import (
    _normalize, MONTHLY_DAYS_MIN, MONTHLY_DAYS_MAX, ANNUAL_DAYS_MAX,
)
from backend.db.models import Transaction
from backend.analysis.transaction_semantics import is_payment, purchase_amount, refund_amount

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
        by_cat_month[cat][month_key].append(tx)

    anomalies = []
    for cat, months_data in by_cat_month.items():
        if current_month not in months_data:
            continue
        current_txs = months_data[current_month]
        if len(current_txs) < 3:
            continue
        current_amount = sum(t.amount for t in current_txs)

        prior_months = sorted(m for m in months_data if m != current_month)
        if len(prior_months) < 3:
            continue
        recent_prior = prior_months[-3:]
        prior_totals = [sum(t.amount for t in months_data[m]) for m in recent_prior]
        avg = sum(prior_totals) / len(prior_totals)

        if avg > 0 and current_amount / avg >= 2.0:
            anomalies.append({
                "category": cat,
                "current_amount": round(current_amount, 2),
                "avg_amount": round(avg, 2),
                "ratio": round(current_amount / avg, 2),
                "tx_count": len(current_txs),
                "tx_ids": [t.id for t in current_txs],
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
                            "tx_ids": [tx1.id, tx2.id],
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
                "tx_ids": [t.id for t in recent],
            })

    return increases


def get_merchant_breakdown(txs: List[Transaction], merchant_aliases: dict[str, str] | None = None) -> List[dict]:
    groups: dict = defaultdict(list)
    for tx in txs:
        key = tx.merchant_name if tx.merchant_name else _normalize_merchant(tx.description)
        if merchant_aliases:
            seen = set()
            while key in merchant_aliases and key not in seen:
                seen.add(key)
                key = merchant_aliases[key]
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
        city_counts: dict = defaultdict(int)
        for t in merchant_txs:
            if t.city:
                city_counts[t.city] += 1
        top_city = max(city_counts, key=lambda k: city_counts[k]) if city_counts else None
        merchants.append({
            "name": name,
            "total": round(total, 2),
            "tx_count": len(merchant_txs),
            "category": top_cat,
            "merchant_type": top_type,
            "city": top_city,
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
    current_year = today.year
    current_month = today.month
    current_day = today.day

    by_year_cat: dict = defaultdict(lambda: defaultdict(float))
    by_year_cat_ytd: dict = defaultdict(lambda: defaultdict(float))

    for tx in txs:
        y = tx.date.year
        by_year_cat[y][tx.category or "other"] += tx.amount
        if (tx.date.month, tx.date.day) <= (current_month, current_day):
            by_year_cat_ytd[y][tx.category or "other"] += tx.amount

    years_present = sorted(by_year_cat.keys())
    if len(years_present) < 2:
        return {"insufficient_data": True, "years": [], "on_pace": None, "on_pace_pct_change": None,
                "same_period_pct_change": None, "same_period_label": ""}

    # Up to 3 years: last 2 complete + current
    years_to_show = years_present[-3:]
    curr_year = years_to_show[-1]
    prior_year = years_to_show[-2]

    years_data = []
    for y in years_to_show:
        is_current = (y == current_year)
        cats_full = dict(by_year_cat[y])
        cats_ytd = dict(by_year_cat_ytd[y])
        # Current year: show YTD only. Past years: show full year total but use YTD slice for bar chart
        years_data.append({
            "year": y,
            "total": round(sum(cats_ytd.values()), 2) if is_current else round(sum(cats_full.values()), 2),
            "is_partial": is_current,
            "categories": {k: round(v, 2) for k, v in (cats_ytd if is_current else cats_full).items()},
        })

    on_pace = None
    on_pace_pct_change = None
    if curr_year == current_year:
        day_of_year = today.timetuple().tm_yday
        ytd = sum(by_year_cat[current_year].values())
        on_pace = round(ytd / day_of_year * 365, 2)
        prior_total = sum(by_year_cat[prior_year].values())
        if prior_total > 0:
            on_pace_pct_change = round((on_pace - prior_total) / prior_total * 100, 1)

    prior_ytd = sum(by_year_cat_ytd[prior_year].values())
    curr_ytd = sum(by_year_cat_ytd[curr_year].values())
    same_period_pct_change = round((curr_ytd - prior_ytd) / prior_ytd * 100, 1) if prior_ytd > 0 else None

    return {
        "insufficient_data": False,
        "years": years_data,
        "on_pace": on_pace,
        "on_pace_pct_change": on_pace_pct_change,
        "same_period_pct_change": same_period_pct_change,
        "same_period_label": f"Jan–{today.strftime('%b %d')}",
    }


def get_monthly_averages(txs: List[Transaction], date_from: date, date_to: date, covered_months=None) -> dict:
    """Average observed spend over full, non-current calendar months.

    Empty months count as zero only when explicitly supplied in covered_months,
    whose YYYY-MM values must come from imported statement-period evidence.
    """
    today = date.today()
    current_month_key = today.strftime("%Y-%m")
    by_month: dict = defaultdict(lambda: defaultdict(float))
    refunds_by_month: dict = defaultdict(float)
    for tx in txs:
        if tx.date < date_from or tx.date > date_to or is_payment(tx):
            continue
        month_key = tx.date.strftime("%Y-%m")
        purchase = float(purchase_amount(tx))
        refund = float(refund_amount(tx))
        if purchase:
            by_month[month_key][tx.category or "other"] += purchase
        if refund:
            refunds_by_month[month_key] += refund

    # Only full calendar months inside the requested bounds are eligible.
    import calendar
    eligible = set()
    year, month = date_from.year, date_from.month
    while (year, month) <= (date_to.year, date_to.month):
        key = f"{year:04d}-{month:02d}"
        last_day = calendar.monthrange(year, month)[1]
        if (year, month) != (today.year, today.month) and date_from <= date(year, month, 1) and date_to >= date(year, month, last_day):
            eligible.add(key)
        month += 1
        if month > 12:
            year, month = year + 1, 1

    observed_months = eligible.intersection(by_month.keys() | refunds_by_month.keys())
    verified_months = set(covered_months or ()).intersection(eligible)
    denominator_months = observed_months | verified_months
    n = len(denominator_months)
    gross_by_cat: dict = defaultdict(float)
    refund_total = 0.0
    for key in denominator_months:
        for cat, amount in by_month[key].items():
            gross_by_cat[cat] += amount
        refund_total += refunds_by_month[key]

    gross = sum(gross_by_cat.values())
    net = gross - refund_total
    categories = sorted([
        {"category": cat, "avg": round(amount / n, 2),
         "pct": round(amount / gross * 100, 1) if gross else 0.0,
         "months_with_spend": sum(by_month[key].get(cat, 0) > 0 for key in denominator_months)}
        for cat, amount in gross_by_cat.items()
    ], key=lambda row: -row["avg"]) if n else []
    return {
        "months_count": n,
        "total_avg": round(gross / n, 2) if n else 0.0,
        "gross_purchases": round(gross, 2),
        "refunds": round(refund_total, 2),
        "net_spending": round(net, 2),
        "categories": categories,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "coverage": {
            "basis": "verified_statement_periods_and_observed_activity",
            "observed_months": sorted(observed_months),
            "verified_zero_months": sorted(verified_months - observed_months),
            "unknown_months": sorted(eligible - denominator_months),
            "note": "Observed transactions do not prove a complete statement period. Empty months are excluded unless import coverage explicitly verifies the full month.",
        },
    }
