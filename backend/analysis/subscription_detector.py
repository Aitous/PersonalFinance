import hashlib
import re
from collections import defaultdict
from datetime import date
from typing import List, Optional
from backend.db.models import Subscription, Transaction

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
        expenses = [tx for tx in transactions if tx.amount > 0]

        groups: dict = defaultdict(list)
        for tx in expenses:
            key = tx.merchant_name if tx.merchant_name else _normalize(tx.description)
            groups[key].append(tx)

        subscriptions: List[Subscription] = []
        for description, txs in groups.items():
            if len(txs) < 3:  # Require at least 3 occurrences to reduce false positives
                continue
            txs_sorted = sorted(txs, key=lambda t: t.date)
            frequency = self._detect_frequency(txs_sorted)
            if frequency is None:
                continue
            last_charged = txs_sorted[-1].date
            base_amount = txs_sorted[-1].amount
            sub_id = hashlib.md5(description.encode()).hexdigest()
            # Mark inactive if monthly and last charge was more than 40 days ago
            if frequency == "monthly":
                days_since = (date.today() - last_charged).days
                active = days_since <= 40
            else:
                active = True
            subscriptions.append(Subscription(
                id=sub_id,
                description=description,
                amount=base_amount,
                frequency=frequency,
                last_charged=last_charged,
                active=active,
            ))
        return subscriptions

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
        amounts = [tx.amount for tx in recent]
        avg = sum(amounts) / len(amounts)
        if avg > 0 and (max(amounts) - min(amounts)) / avg > AMOUNT_TOLERANCE_PCT:
            return None

        return frequency
