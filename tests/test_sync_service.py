from datetime import date
from unittest.mock import MagicMock, patch

from backend.db.models import Transaction
from backend.sync_service import SyncService


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
    session.execute.return_value.scalar_one_or_none.return_value = None
    session.execute.return_value.scalars.return_value.all.return_value = [tx]

    llm = MagicMock()
    llm.complete.return_value = f"{tx.id}: groceries"

    service = SyncService(session=session, llm=llm)
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
    # tx already exists in DB
    session.execute.return_value.scalar_one_or_none.return_value = tx
    session.execute.return_value.scalars.return_value.all.return_value = [tx]

    service = SyncService(session=session, llm=MagicMock())
    result = service.sync_bank("chase", since=date(2025, 1, 1), username="u", password="p")

    assert result["tx_count"] == 0
