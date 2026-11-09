from datetime import date, datetime, timezone
import json
import uuid
from typing import List, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Account, Subscription, Sync, Transaction
from backend.db.database import invalidate_derived_data
from backend.ingestion import reconcile_account_overlaps, reconcile_legacy_csv_ids, reconcile_unassigned_description_overlaps, namespace_transaction_ids
from backend.ofx.client import download_transactions
from backend.analysis.categorizer import Categorizer
from backend.analysis.subscription_detector import SubscriptionDetector
from backend.analysis.recurring import reconcile_subscriptions
from backend.llm.base import LLMProvider
from backend.parsers.csv_parser import stable_transaction_id

SUPPORTED_BANKS = {"chase", "discover", "amex"}


class SyncService:
    def __init__(self, session: Session, llm: LLMProvider):
        self._session = session
        self._llm = llm
        self._categorizer = Categorizer(llm=llm) if llm is not None else None
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
        occurrences = {}
        for tx in transactions:
            try:
                acct_id = json.loads(tx.metadata_ or "{}").get("acct_id")
            except (TypeError, json.JSONDecodeError):
                acct_id = None
            if acct_id:
                account = self._session.execute(select(Account).where(
                    Account.bank == bank, Account.external_id == acct_id
                )).scalar_one_or_none()
                if not account:
                    account = Account(id=uuid.uuid4().hex, bank=bank,
                        name=f"{bank.title()} account •{acct_id[-4:]}", last4=acct_id[-4:], external_id=acct_id)
                    self._session.add(account)
                    self._session.flush()
                tx.account_id = account.id
                occurrence_key = (account.id, tx.date, tx.description.casefold(), round(tx.amount, 2))
                occurrences[occurrence_key] = occurrences.get(occurrence_key, 0) + 1
                tx.id = stable_transaction_id(bank, tx.date, tx.description, tx.amount, account.id,
                    occurrences[occurrence_key], tx.bank_fitid)

        namespace_transaction_ids(transactions)
        reconcile_account_overlaps(self._session, transactions)
        reconcile_legacy_csv_ids(self._session, transactions)
        reconcile_unassigned_description_overlaps(self._session, transactions)
        reconcile_legacy_csv_ids(self._session, transactions)

        new_txs = []
        for tx in transactions:
            if tx.id is None:
                raise ValueError(f"Transaction missing id: {tx}")
            exists = self._session.execute(
                select(Transaction).where(Transaction.id == tx.id)
            ).scalar_one_or_none()
            if not exists:
                new_txs.append(tx)

        for tx in new_txs:
            tx.category = tx.category or "other"
            self._session.add(tx)

        all_txs = self._session.execute(select(Transaction)).scalars().all()
        reconcile_subscriptions(self._session, all_txs)

        sync_record = Sync(
            source=bank,
            synced_at=datetime.now(timezone.utc),
            from_date=since,
            to_date=date.today(),
            tx_count=len(new_txs),
        )
        self._session.add(sync_record)
        if new_txs:
            invalidate_derived_data(self._session)
        self._session.commit()

        return {"bank": bank, "tx_count": len(new_txs), "new_transaction_ids": [tx.id for tx in new_txs]}

    def import_transactions(self, transactions: List[Transaction], run_enrichment: bool = True, commit: bool = True) -> dict:
        """Import pre-parsed transactions (e.g. from CSV files), running full pipeline."""
        if not transactions:
            return {"tx_count": 0, "total_parsed": 0, "duplicate_count": 0, "new_transaction_ids": []}

        namespace_transaction_ids(transactions)

        reconcile_account_overlaps(self._session, transactions)
        reconcile_legacy_csv_ids(self._session, transactions)

        # Deduplicate within the incoming list itself before querying the DB
        seen_ids: set = set()
        unique_transactions = []
        for tx in transactions:
            if tx.id is None:
                raise ValueError(f"Transaction missing id: {tx}")
            if tx.id not in seen_ids:
                seen_ids.add(tx.id)
                unique_transactions.append(tx)
        transactions = unique_transactions

        new_txs = []
        for tx in transactions:
            exists = self._session.execute(
                select(Transaction).where(Transaction.id == tx.id)
            ).scalar_one_or_none()
            if not exists:
                new_txs.append(tx)

        if new_txs and run_enrichment and self._categorizer is not None:
            try:
                enrichments = self._categorizer.categorize(new_txs)
            except Exception:
                enrichments = {}
            for tx in new_txs:
                e = enrichments.get(tx.id)
                if e:
                    tx.enrichment_status = "fallback" if e.outcome == "fallback" else "complete"
                    if e.outcome != "fallback":
                        import json
                        tx.raw_enrichment = json.dumps(e.model_dump(exclude={"outcome"}), ensure_ascii=False)
                        tx.category = e.category
                        tx.merchant_name = e.merchant_name
                        tx.city = e.city
                        tx.is_online = e.is_online
                        tx.merchant_type = e.merchant_type
                else:
                    tx.category = "other"
        for tx in new_txs:
            if not tx.category:
                tx.category = "other"
            self._session.add(tx)

        all_txs = self._session.execute(select(Transaction)).scalars().all()
        reconcile_subscriptions(self._session, all_txs)

        sync_record = Sync(
            source=transactions[0].source if transactions else "csv",
            synced_at=datetime.now(timezone.utc),
            from_date=min(t.date for t in transactions) if transactions else date.today(),
            to_date=date.today(),
            tx_count=len(new_txs),
        )
        self._session.add(sync_record)
        if new_txs:
            invalidate_derived_data(self._session)
        if commit:
            self._session.commit()

        return {"tx_count": len(new_txs), "total_parsed": len(transactions),
                "duplicate_count": len(transactions) - len(new_txs),
                "new_transaction_ids": [tx.id for tx in new_txs]}
