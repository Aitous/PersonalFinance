import pytest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from backend.sync_service import SyncService

@pytest.fixture
def mock_session():
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    return session

@pytest.mark.asyncio
async def test_sync_saves_transactions(mock_session, tmp_path):
    csv_file = tmp_path / "chase.csv"
    csv_file.write_text(
        "Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
        "05/14/2025,05/15/2025,WHOLE FOODS,Groceries,Sale,-84.20,\n"
    )
    mock_scraper = AsyncMock()
    mock_scraper.sync.return_value = csv_file
    mock_scraper.SOURCE = "chase"

    mock_llm = MagicMock()
    mock_llm.complete.return_value = ""

    service = SyncService(session=mock_session, llm=mock_llm)
    with patch("backend.sync_service.ChaseScraper", return_value=mock_scraper):
        result = await service.sync_bank("chase", since=date(2025, 1, 1), username="u", password="p")

    assert result["tx_count"] == 1
    mock_session.add.assert_called()
    mock_session.commit.assert_called()
