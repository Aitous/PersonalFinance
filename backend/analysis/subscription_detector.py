import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from typing import List, Optional
from backend.db.models import Subscription, Transaction
from backend.analysis.transaction_semantics import is_payment, purchase_amount

AMOUNT_TOLERANCE_PCT = 0.15   # 15% within a stable period
MONTHLY_DAYS_MIN, MONTHLY_DAYS_MAX = 20, 40
ANNUAL_DAYS_MIN, ANNUAL_DAYS_MAX = 340, 390

_NOISE = re.compile(r'\s+[A-Z0-9]{8,}$|\s+\d{6,}$|\s+DC\d+[A-Z0-9]*$|\s+[A-Z]{2}\d+[A-Z0-9]+$')

def _normalize(description: str) -> str:
    s = description.upper().strip()
    s = _NOISE.sub("", s).strip()
    s = re.sub(r'\s+[A-Z]{2}$', '', s).strip()
    return s


class SubscriptionDetector:
    def detect(self, transactions: List[Transaction]) -> List[Subscription]:
        expenses = [tx for tx in transactions if purchase_amount(tx) > 0 and not is_payment(tx)]

        groups: dict = defaultdict(list)
        for tx in expenses:
            key = tx.merchant_name if tx.merchant_name else _normalize(tx.description)
            # Keep cards distinct when account provenance is known; legacy rows
            # without an account can still be grouped together.
            key = (getattr(tx, "account_id", None), key)
            groups[key].append(tx)

        subscriptions: List[Subscription] = []
        seen_ids: set = set()

        for (account_id, description), txs in groups.items():
            txs_sorted = sorted(txs, key=lambda t: t.date)
            frequency = self._detect_frequency(txs_sorted)
            if frequency is not None:
                last_charged = txs_sorted[-1].date
                base_amount = float(purchase_amount(txs_sorted[-1]))
                identity = description if account_id is None else f"{account_id}:{description}"
                sub_id = hashlib.md5(identity.encode()).hexdigest()
                days_since = (date.today() - last_charged).days
                active = days_since <= 40 if frequency == "monthly" else days_since <= 400
                subscriptions.append(Subscription(
                    id=sub_id,
                    description=description,
                    amount=base_amount,
                    frequency=frequency,
                    last_charged=last_charged,
                    active=active,
                    origin="detected",
                    supporting_transaction_ids=json.dumps([tx.id for tx in txs_sorted]),
                ))
                seen_ids.add(sub_id)
                continue

            # Usage-based detection: ≥5 charges, avg gap < 20 days, spans ≥2 calendar months
            usage = self._detect_usage_based(description, txs_sorted, account_id)
            if usage:
                sub_id = hashlib.md5(f"{account_id or ''}:{description}_usage".encode()).hexdigest()
                if sub_id not in seen_ids:
                    subscriptions.append(usage)
                    seen_ids.add(sub_id)

        return subscriptions

    _USAGE_BASED_TYPES = {
        "software subscription", "saas", "cloud service", "cloud computing",
        "api service", "software", "streaming service", "digital service",
    }

    def _detect_usage_based(self, description: str, txs_sorted: List[Transaction], account_id=None) -> Optional[Subscription]:
        if len(txs_sorted) < 5:
            return None

        # Only apply to software/cloud merchants — not grocery stores, cafes, etc.
        merchant_types = {tx.merchant_type.lower() for tx in txs_sorted if tx.merchant_type}
        if not any(t in self._USAGE_BASED_TYPES for t in merchant_types):
            return None

        gaps = [(txs_sorted[i+1].date - txs_sorted[i].date).days for i in range(len(txs_sorted)-1)]
        avg_gap = sum(gaps) / len(gaps)
        if avg_gap >= MONTHLY_DAYS_MIN:
            return None  # not usage-based — gaps too long

        months_seen = {tx.date.strftime("%Y-%m") for tx in txs_sorted}
        if len(months_seen) < 2:
            return None  # all in one month — could be a one-off

        # Estimate monthly cost from most recent complete month
        from collections import defaultdict as _dd
        by_month: dict = _dd(float)
        for tx in txs_sorted:
            by_month[tx.date.strftime("%Y-%m")] += float(purchase_amount(tx))
        today = date.today()
        current_month_key = today.strftime("%Y-%m")
        complete_months = {m: v for m, v in by_month.items() if m != current_month_key}
        if not complete_months:
            return None
        avg_monthly = sum(complete_months.values()) / len(complete_months)

        last_charged = txs_sorted[-1].date
        days_since = (today - last_charged).days
        sub_id = hashlib.md5(f"{account_id or ''}:{description}_usage".encode()).hexdigest()
        return Subscription(
            id=sub_id,
            description=f"{description} (usage-based)",
            amount=round(avg_monthly, 2),
            frequency="monthly",
            last_charged=last_charged,
            active=days_since <= 40,
            origin="detected",
            supporting_transaction_ids=json.dumps([tx.id for tx in txs_sorted]),
        )

    def _detect_frequency(self, txs: List[Transaction]) -> Optional[str]:
        if len(txs) < 2:
            return None

        txs_sorted = sorted(txs, key=lambda t: t.date)

        # Check gap regularity
        gaps = [(txs_sorted[i+1].date - txs_sorted[i].date).days for i in range(len(txs_sorted)-1)]
        avg_gap = sum(gaps) / len(gaps)

        if MONTHLY_DAYS_MIN <= avg_gap <= MONTHLY_DAYS_MAX:
            frequency = "monthly"
        elif ANNUAL_DAYS_MIN <= avg_gap <= ANNUAL_DAYS_MAX:
            frequency = "annual"
        else:
            return None

        # Check amount consistency on the most recent 6 charges only.
        # This tolerates historical rate changes (e.g. insurance) while
        # still rejecting variable-spend merchants like grocery stores.
        recent = txs_sorted[-6:]
        amounts = [float(purchase_amount(tx)) for tx in recent]
        avg = sum(amounts) / len(amounts)
        if avg > 0 and (max(amounts) - min(amounts)) / avg > AMOUNT_TOLERANCE_PCT:
            return None

        return frequency
