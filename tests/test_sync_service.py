from datetime import date
from unittest.mock import MagicMock, patch

from backend.analysis.categorizer import TransactionEnrichment
from backend.db.models import Transaction
from backend.sync_service import SyncService


def _make_execute_side_effect(dedup_result, all_txs_result):
    """Return a side_effect function for session.execute.

    The first N calls are dedup checks (returning scalar_one_or_none),
    the last call fetches all transactions (returning scalars().all()).
    We detect which call it is by checking the query string for a WHERE clause.
    """
    call_results = []

    def side_effect(stmt):
        # Inspect compiled statement; dedup queries have a WHERE clause
        stmt_str = str(stmt)
        if "WHERE" in stmt_str.upper():
            mock = MagicMock()
            mock.scalar_one_or_none.return_value = dedup_result
            call_results.append("dedup")
            return mock
        else:
            mock = MagicMock()
            mock.scalars.return_value.all.return_value = all_txs_result
            call_results.append("all_txs")
            return mock

    return side_effect


@patch("backend.sync_service.download_transactions")
def test_sync_saves_new_transactions(mock_download):
    tx = Transaction(
        id="abc123",
        source="chase",
        date=date(2025, 5, 14),
        description="WHOLE FOODS",
        amount=-84.20,
    )
    mock_download.return_value = [tx]

    session = MagicMock()
    session.execute.side_effect = _make_execute_side_effect(
        dedup_result=None, all_txs_result=[tx]
    )

    llm = MagicMock()
    service = SyncService(session=session, llm=llm)
    service._categorizer.categorize = MagicMock(return_value={
        tx.id: TransactionEnrichment(
            id=tx.id, category="groceries", merchant_name="Whole Foods",
            city=None, is_online=False, merchant_type="grocery store",
        )
    })
    service._sub_detector.detect = MagicMock(return_value=[])

    result = service.sync_bank("chase", since=date(2025, 1, 1), username="u", password="p")

    assert result["tx_count"] == 1
    session.add.assert_called()
    session.commit.assert_called()


@patch("backend.sync_service.download_transactions")
def test_sync_deduplicates_existing(mock_download):
    tx = Transaction(
        id="abc123",
        source="chase",
        date=date(2025, 5, 14),
        description="WHOLE FOODS",
        amount=-84.20,
    )
    mock_download.return_value = [tx]

    session = MagicMock()
    session.execute.side_effect = _make_execute_side_effect(
        dedup_result=tx, all_txs_result=[tx]
    )

    service = SyncService(session=session, llm=MagicMock())
    result = service.sync_bank("chase", since=date(2025, 1, 1), username="u", password="p")

    assert result["tx_count"] == 0


def _make_transaction(tx_id: str = "tx1") -> Transaction:
    return Transaction(
        id=tx_id,
        source="csv",
        date=date(2024, 1, 1),
        description="NETFLIX",
        amount=-15.99,
    )


def _make_session(dedup_result=None, all_txs_result=None):
    session = MagicMock()
    session.execute.side_effect = _make_execute_side_effect(
        dedup_result=dedup_result,
        all_txs_result=all_txs_result if all_txs_result is not None else [],
    )
    session.get.return_value = None
    return session


def _make_service(session, categorize_return):
    llm = MagicMock()
    service = SyncService(session=session, llm=llm)
    service._categorizer.categorize = MagicMock(return_value=categorize_return)
    service._sub_detector.detect = MagicMock(return_value=[])
    return service


def test_import_saves_all_enrichment_fields():
    tx = _make_transaction("tx1")
    enrichment = TransactionEnrichment(
        id="tx1",
        category="entertainment",
        merchant_name="Netflix",
        city=None,
        is_online=True,
        merchant_type="streaming service",
    )
    session = _make_session()
    service = _make_service(session, {"tx1": enrichment})

    service.import_transactions([tx])

    assert tx.category == "entertainment"
    assert tx.merchant_name == "Netflix"
    assert tx.city is None
    assert tx.is_online is True
    assert tx.merchant_type == "streaming service"
    session.add.assert_any_call(tx)


def test_import_fallback_when_enrichment_missing():
    tx = _make_transaction("tx2")
    session = _make_session()
    service = _make_service(session, {})

    service.import_transactions([tx])

    assert tx.category == "other"
    session.add.assert_any_call(tx)


def test_import_skips_duplicate_transactions():
    tx1 = _make_transaction("tx_dup")
    tx2 = _make_transaction("tx_dup")

    enrichment = TransactionEnrichment(
        id="tx_dup",
        category="dining",
        merchant_name="Chipotle",
        city="New York",
        is_online=False,
        merchant_type="restaurant",
    )
    session = _make_session()
    service = _make_service(session, {"tx_dup": enrichment})

    service.import_transactions([tx1, tx2])

    tx_add_calls = [c for c in session.add.call_args_list if isinstance(c.args[0], Transaction)]
    assert len(tx_add_calls) == 1
