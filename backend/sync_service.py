from datetime import date, datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Subscription, Sync, Transaction
from backend.ofx.client import download_transactions
from backend.analysis.categorizer import Categorizer
from backend.analysis.subscription_detector import SubscriptionDetector
from backend.llm.base import LLMProvider

SUPPORTED_BANKS = {"chase", "discover", "amex"}


class SyncService:
    def __init__(self, session: Session, llm: LLMProvider):
        self._session = session
        self._llm = llm
        self._categorizer = Categorizer(llm=llm)
        self._sub_detector = SubscriptionDetector()

    def sync_bank(
        self,
        bank: Literal["chase", "discover", "amex"],
        since: date,
        username: str,
        password: str,
    ) -> dict:
        if bank not in SUPPORTED_BANKS:
            raise ValueError(f"Unknown bank: {bank}")

        transactions = download_transactions(bank, username, password, since)

        new_txs = []
        for tx in transactions:
            exists = self._session.execute(
                select(Transaction).where(Transaction.id == tx.id)
            ).scalar_one_or_none()
            if not exists:
                new_txs.append(tx)

        if new_txs:
            categories = self._categorizer.categorize(new_txs)
            for tx in new_txs:
                tx.category = categories.get(tx.id, "other")
                self._session.add(tx)

        all_txs = self._session.execute(select(Transaction)).scalars().all()
        subs = self._sub_detector.detect(list(all_txs))
        for sub in subs:
            existing = self._session.get(Subscription, sub.id)
            if existing:
                existing.last_charged = sub.last_charged
                existing.amount = sub.amount
            else:
                self._session.add(sub)

        sync_record = Sync(
            source=bank,
            synced_at=datetime.now(timezone.utc),
            from_date=since,
            to_date=date.today(),
            tx_count=len(new_txs),
        )
        self._session.add(sync_record)
        self._session.commit()

        return {"bank": bank, "tx_count": len(new_txs)}
