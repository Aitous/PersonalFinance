from __future__ import annotations

import json
from collections import defaultdict
from statistics import median
from typing import Any

from backend.analysis.transaction_semantics import purchase_amount, refund_amount
from backend.db.models import Transaction


def _merchant_name(tx: Transaction, aliases: dict[str, str]) -> str:
    name = tx.merchant_name.strip() if tx.merchant_name and tx.merchant_name.strip() else (tx.description or "Unknown").upper().strip()
    seen: set[str] = set()
    while name in aliases and name not in seen:
        seen.add(name)
        name = aliases[name]
    return name


def build_category_evidence(
    txs: list[Transaction], year: int, month: int, comparison: str,
    merchant_aliases: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Build deterministic category and merchant evidence for an LLM explanation."""
    aliases = merchant_aliases or {}
    current_rows: dict[str, list[Transaction]] = defaultdict(list)
    baseline_rows: dict[str, dict[str, list[Transaction]]] = defaultdict(lambda: defaultdict(list))

    if comparison == "prior":
        prior_year, prior_month = (year - 1, 12) if month == 1 else (year, month - 1)
        baseline_month_keys = [f"{prior_year:04d}-{prior_month:02d}"]
    elif comparison == "recent3":
        baseline_month_keys = []
        for offset in (3, 2, 1):
            index = year * 12 + month - 1 - offset
            baseline_year, zero_based_month = divmod(index, 12)
            baseline_month_keys.append(f"{baseline_year:04d}-{zero_based_month + 1:02d}")
    else:
        raise ValueError("comparison must be 'recent3' or 'prior'")

    month_activity: dict[str, dict[str, Any]] = {
        key: {"observed_activity": False, "transaction_count": 0, "source_counts": defaultdict(int)}
        for key in baseline_month_keys
    }

    for tx in txs:
        month_key = tx.date.strftime("%Y-%m")
        activity = month_activity.get(month_key)
        if activity is not None and (purchase_amount(tx) > 0 or refund_amount(tx) > 0):
            activity["observed_activity"] = True
            activity["transaction_count"] += 1
            activity["source_counts"][tx.source or "unknown"] += 1
        if purchase_amount(tx) <= 0:
            continue
        key = (tx.category or "other").strip() or "other"
        if tx.date.year == year and tx.date.month == month:
            current_rows[key].append(tx)
        elif month_key in baseline_month_keys:
            baseline_rows[key][month_key].append(tx)

    baseline_months_all_observed = all(item["observed_activity"] for item in month_activity.values())
    baseline_month_count = len(baseline_month_keys)
    baseline_divisor = baseline_month_count if comparison == "prior" or baseline_months_all_observed else 0
    baseline_month_evidence = [
        {
            "month": key,
            "observed_activity": month_activity[key]["observed_activity"],
            "transaction_count": month_activity[key]["transaction_count"],
            "source_counts": dict(month_activity[key]["source_counts"]),
        }
        for key in baseline_month_keys
    ]

    evidence: list[dict[str, Any]] = []
    for category in sorted(set(current_rows) | set(baseline_rows)):
        current = current_rows.get(category, [])
        current_by_merchant: dict[str, float] = defaultdict(float)
        current_counts: dict[str, int] = defaultdict(int)
        for tx in current:
            merchant = _merchant_name(tx, aliases)
            current_by_merchant[merchant] += float(purchase_amount(tx))
            current_counts[merchant] += 1

        baseline_by_merchant: dict[str, float] = defaultdict(float)
        merchant_month_amounts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        merchant_month_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        category_baseline_rows: list[Transaction] = []
        for month_key in baseline_month_keys:
            for tx in baseline_rows.get(category, {}).get(month_key, []):
                category_baseline_rows.append(tx)
                merchant = _merchant_name(tx, aliases)
                amount = float(purchase_amount(tx))
                baseline_by_merchant[merchant] += amount
                merchant_month_amounts[merchant][month_key] += amount
                merchant_month_counts[merchant][month_key] += 1

        category_baseline_months = []
        for month_key in baseline_month_keys:
            month_category_rows = baseline_rows.get(category, {}).get(month_key, [])
            category_baseline_months.append({
                **month_activity[month_key],
                "month": month_key,
                "source_counts": dict(month_activity[month_key]["source_counts"]),
                "category_gross_purchases": round(sum(float(purchase_amount(tx)) for tx in month_category_rows), 2),
                "category_transaction_count": len(month_category_rows),
            })
        baseline_category_amounts = [item["category_gross_purchases"] for item in category_baseline_months]
        baseline_category_median = median(baseline_category_amounts) if baseline_divisor else None

        current_total = sum(current_by_merchant.values())
        baseline_total = sum(baseline_by_merchant.values()) / baseline_divisor if baseline_divisor else None
        merchant_changes = []
        for merchant in set(current_by_merchant) | set(baseline_by_merchant):
            current_amount = current_by_merchant.get(merchant, 0.0)
            baseline_amount = baseline_by_merchant.get(merchant, 0.0) / baseline_divisor if baseline_divisor else 0.0
            merchant_changes.append({
                "merchant": merchant,
                "current_amount": round(current_amount, 2),
                "current_transactions": current_counts.get(merchant, 0),
                "baseline_monthly_average": round(baseline_amount, 2) if baseline_divisor else None,
                "baseline_active_month_count": sum(merchant_month_counts[merchant].get(key, 0) > 0 for key in baseline_month_keys),
                "baseline_month_amounts": [
                    {"month": key, "observed_activity": month_activity[key]["observed_activity"],
                     "amount": round(merchant_month_amounts[merchant].get(key, 0.0), 2)}
                    for key in baseline_month_keys
                ],
                "change": round(current_amount - baseline_amount, 2) if baseline_divisor else None,
            })
        merchant_changes.sort(key=lambda row: abs(row["change"] or 0), reverse=True)

        examples = sorted(current, key=lambda tx: float(purchase_amount(tx)), reverse=True)[:8]
        baseline_examples = sorted(category_baseline_rows, key=lambda tx: float(purchase_amount(tx)), reverse=True)[:5]
        evidence.append({
            "category": category,
            "current_gross_purchases": round(current_total, 2),
            "current_transaction_count": len(current),
            "baseline_type": "prior month" if comparison == "prior" else "three immediately preceding calendar months",
            "baseline_month_count": baseline_month_count,
            "baseline_observed_month_count": sum(item["observed_activity"] for item in baseline_month_evidence),
            "baseline_months_all_observed": baseline_months_all_observed,
            "baseline_months": category_baseline_months,
            "baseline_gross_purchases": round(baseline_total, 2) if baseline_total is not None else None,
            "baseline_category_median": round(float(baseline_category_median), 2) if baseline_category_median is not None else None,
            "baseline_category_range": [
                min(baseline_category_amounts), max(baseline_category_amounts),
            ] if baseline_divisor and baseline_category_amounts else None,
            "change": round(current_total - baseline_total, 2) if baseline_total is not None else None,
            "merchant_changes": merchant_changes[:8],
            "largest_current_transactions": [
                {
                    "date": tx.date.isoformat(),
                    "merchant": _merchant_name(tx, aliases),
                    "description": (tx.description or "")[:100],
                    "amount": round(float(purchase_amount(tx)), 2),
                }
                for tx in examples
            ],
            "largest_baseline_transactions": [
                {
                    "date": tx.date.isoformat(),
                    "month": tx.date.strftime("%Y-%m"),
                    "merchant": _merchant_name(tx, aliases),
                    "description": (tx.description or "")[:100],
                    "amount": round(float(purchase_amount(tx)), 2),
                }
                for tx in baseline_examples
            ],
        })
    return evidence


def build_explanation_prompt(year: int, month: int, comparison: str, evidence: list[dict[str, Any]]) -> str:
    baseline = "the prior calendar month" if comparison == "prior" else "the mean of the three immediately preceding calendar months"
    return (
        "Explain the category spending differences in this personal finance monthly report. "
        "Use only the evidence JSON below. It contains month-by-month category and merchant activity, source activity counts, and the largest current and baseline transactions. "
        "For every category, return one concise sentence (at most 32 words) explaining the main supported driver. "
        "Do not invent causes, merchants, transactions, or numeric amounts. Do not repeat the totals; the app displays exact calculated amounts separately. "
        "When one unusually large purchase in one baseline month raises the three-month mean, name that month and merchant if supported by the evidence. "
        "Use the three-month median and range to recognize a one-off spike, but explain the exact mean comparison shown by the app. "
        "Do not say spending stopped when transactions are absent; describe this only as no recorded activity in the available data. "
        "Source counts show observed rows only and do not prove complete card statement coverage. "
        "If evidence is too weak to explain a difference, say that the data does not identify a clear driver. "
        "Return valid JSON only, with this exact shape: {\"explanations\":[{\"category\":\"category name from evidence\",\"explanation\":\"one sentence\"}]}. "
        f"Selected period: {year:04d}-{month:02d}; comparison: {baseline}.\n"
        f"Evidence JSON:\n{json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))}"
    )


def parse_explanations(response: str, evidence: list[dict[str, Any]]) -> dict[str, str]:
    text = response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    payload = json.loads(text)
    rows = payload.get("explanations") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("LLM response did not contain an explanations list")
    allowed = {row["category"] for row in evidence}
    explanations: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        category = row.get("category")
        explanation = row.get("explanation")
        if category in allowed and isinstance(explanation, str) and explanation.strip():
            explanations[category] = explanation.strip()[:500]
    for category in allowed:
        explanations.setdefault(category, "The available transactions do not identify a clear merchant-level driver for this difference.")
    return explanations
