import json
from unittest.mock import MagicMock
import pytest

from backend.analysis.categorizer import Categorizer, TransactionEnrichment


def make_tx(id, description, amount=10.0):
    tx = MagicMock()
    tx.id = id
    tx.description = description
    tx.amount = amount
    return tx


def test_categorize_returns_enrichment_objects():
    llm = MagicMock()
    llm.complete_json.return_value = json.dumps([
        {
            "id": "tx1",
            "category": "groceries",
            "merchant_name": "Trader Joe's",
            "city": "San Francisco",
            "is_online": False,
            "merchant_type": "grocery store",
        }
    ])
    categorizer = Categorizer(llm)
    result = categorizer.categorize([make_tx("tx1", "TRADER JOES #123 SAN FRANCISCO", 45.00)])

    assert "tx1" in result
    enrichment = result["tx1"]
    assert isinstance(enrichment, TransactionEnrichment)
    assert enrichment.category == "groceries"
    assert enrichment.merchant_name == "Trader Joe's"
    assert enrichment.city == "San Francisco"
    assert enrichment.is_online is False
    assert enrichment.merchant_type == "grocery store"


def test_categorize_empty_returns_empty_dict():
    llm = MagicMock()
    categorizer = Categorizer(llm)
    result = categorizer.categorize([])
    assert result == {}
    llm.complete_json.assert_not_called()


def test_categorize_invalid_json_falls_back():
    llm = MagicMock()
    llm.complete_json.return_value = "not valid json at all!!!"
    categorizer = Categorizer(llm)
    txs = [make_tx("tx1", "SOME STORE"), make_tx("tx2", "ANOTHER STORE")]
    result = categorizer.categorize(txs)

    assert set(result.keys()) == {"tx1", "tx2"}
    for tx_id, enrichment in result.items():
        assert isinstance(enrichment, TransactionEnrichment)
        assert enrichment.category == "other"
        assert enrichment.is_online is False
        assert enrichment.merchant_type == "unknown"
        assert enrichment.city is None


def test_categorize_invalid_category_kept():
    """If LLM returns an unrecognized category, keep it as-is (no forced normalization)."""
    llm = MagicMock()
    llm.complete_json.return_value = json.dumps([
        {
            "id": "tx1",
            "category": "weird_unknown_category",
            "merchant_name": "Mystery Store",
            "city": None,
            "is_online": False,
            "merchant_type": "unknown store",
        }
    ])
    categorizer = Categorizer(llm)
    result = categorizer.categorize([make_tx("tx1", "MYSTERY STORE")])

    assert "tx1" in result
    assert result["tx1"].category == "weird_unknown_category"


def test_categorize_city_and_online_fields():
    llm = MagicMock()
    llm.complete_json.return_value = json.dumps([
        {
            "id": "tx1",
            "category": "subscriptions",
            "merchant_name": "Netflix",
            "city": None,
            "is_online": True,
            "merchant_type": "streaming service",
        },
        {
            "id": "tx2",
            "category": "dining",
            "merchant_name": "In-N-Out Burger",
            "city": "Los Angeles",
            "is_online": False,
            "merchant_type": "fast food restaurant",
        },
    ])
    categorizer = Categorizer(llm)
    txs = [
        make_tx("tx1", "NETFLIX.COM", 15.99),
        make_tx("tx2", "IN N OUT BURGER LOS ANGELES", 12.50),
    ]
    result = categorizer.categorize(txs)

    assert result["tx1"].city is None
    assert result["tx1"].is_online is True
    assert result["tx2"].city == "Los Angeles"
    assert result["tx2"].is_online is False
