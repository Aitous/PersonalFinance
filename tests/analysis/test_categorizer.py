import pytest
from unittest.mock import MagicMock
from datetime import date
from backend.analysis.categorizer import Categorizer, VALID_CATEGORIES
from backend.db.models import Transaction

def make_tx(id, description, amount):
    return Transaction(
        id=id, source="chase", date=date(2025, 5, 1),
        description=description, amount=amount
    )

def test_categorizes_batch_of_transactions():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = (
        "tx1: groceries\ntx2: dining\ntx3: subscriptions"
    )
    categorizer = Categorizer(llm=mock_llm)
    txs = [
        make_tx("tx1", "WHOLE FOODS", -84.20),
        make_tx("tx2", "UBER EATS", -32.50),
        make_tx("tx3", "NETFLIX.COM", -15.99),
    ]
    result = categorizer.categorize(txs)
    assert result["tx1"] == "groceries"
    assert result["tx2"] == "dining"
    assert result["tx3"] == "subscriptions"

def test_falls_back_to_other_for_unknown_category():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "tx1: banana_stuff"
    categorizer = Categorizer(llm=mock_llm)
    txs = [make_tx("tx1", "RANDOM MERCHANT", -10.00)]
    result = categorizer.categorize(txs)
    assert result["tx1"] == "other"

def test_empty_list_returns_empty_dict():
    mock_llm = MagicMock()
    categorizer = Categorizer(llm=mock_llm)
    result = categorizer.categorize([])
    assert result == {}
    mock_llm.complete.assert_not_called()
