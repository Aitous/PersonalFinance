import hashlib
from collections import defaultdict
from datetime import date
from typing import List
from backend.db.models import Subscription, Transaction

AMOUNT_TOLERANCE = 1.00  # dollars
MONTHLY_DAYS_MIN, MONTHLY_DAYS_MAX = 25, 35
ANNUAL_DAYS_MIN, ANNUAL_DAYS_MAX = 350, 380

class SubscriptionDetector:
    def detect(self, transactions: List[Transaction]) -> List[Subscription]:
        expenses = [tx for tx in transactions if tx.amount < 0]
        groups: dict[str, list[Transaction]] = defaultdict(list)
        for tx in expenses:
            groups[tx.description.upper()].append(tx)

        subscriptions: List[Subscription] = []
        for description, txs in groups.items():
            if len(txs) < 2:
                continue
            txs_sorted = sorted(txs, key=lambda t: t.date)
            frequency = self._detect_frequency(txs_sorted)
            if frequency is None:
                continue
            base_amount = abs(txs_sorted[-1].amount)
            sub_id = hashlib.md5(description.encode()).hexdigest()
            subscriptions.append(Subscription(
                id=sub_id,
                description=description,
                amount=base_amount,
                frequency=frequency,
                last_charged=txs_sorted[-1].date,
                active=True,
            ))
        return subscriptions

    def _detect_frequency(self, txs: List[Transaction]):
        if len(txs) < 2:
            return None
        amounts = [abs(tx.amount) for tx in txs]
        if max(amounts) - min(amounts) > AMOUNT_TOLERANCE:
            return None

        gaps = [
            (txs[i + 1].date - txs[i].date).days
            for i in range(len(txs) - 1)
        ]
        avg_gap = sum(gaps) / len(gaps)

        if MONTHLY_DAYS_MIN <= avg_gap <= MONTHLY_DAYS_MAX:
            return "monthly"
        if ANNUAL_DAYS_MIN <= avg_gap <= ANNUAL_DAYS_MAX:
            return "annual"
        return None
