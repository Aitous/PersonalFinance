import pytest
from datetime import date
from unittest.mock import MagicMock


def _tx(amount, category, year, month, day=1, description="SHOP", merchant_name=None):
    tx = MagicMock()
    tx.amount = amount
    tx.category = category
    tx.date = date(year, month, day)
    tx.description = description
    tx.merchant_name = merchant_name
    return tx


def test_total_and_tx_count():
    from backend.analysis.monthly_report import get_monthly_report_data
    txs = [
        _tx(100.0, "dining", 2026, 4),
        _tx(200.0, "groceries", 2026, 4),
        _tx(50.0, "dining", 2026, 3),  # prior month
    ]
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert result["total"] == 300.0
    assert result["tx_count"] == 2
    assert result["prev_total"] == 50.0


def test_categories_sorted_by_current_descending():
    from backend.analysis.monthly_report import get_monthly_report_data
    txs = [
        _tx(50.0, "dining", 2026, 4),
        _tx(200.0, "groceries", 2026, 4),
        _tx(40.0, "groceries", 2026, 3),
    ]
    result = get_monthly_report_data(txs, year=2026, month=4)
    cats = result["categories"]
    assert cats[0]["name"] == "groceries"
    assert cats[0]["current"] == 200.0
    assert cats[0]["prior"] == 40.0
    assert cats[1]["name"] == "dining"
    assert cats[1]["current"] == 50.0
    assert cats[1]["prior"] == 0.0


def test_top_merchants_limited_to_8():
    from backend.analysis.monthly_report import get_monthly_report_data
    txs = [_tx(float(i), f"cat{i}", 2026, 4, description=f"MERCHANT{i}") for i in range(1, 12)]
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert len(result["merchants"]) == 8
    # First merchant should be the one with the highest amount
    assert result["merchants"][0]["total"] == 11.0


def test_empty_month_returns_zeros():
    from backend.analysis.monthly_report import get_monthly_report_data
    txs = [_tx(100.0, "dining", 2026, 3)]  # only prior month has data
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert result["total"] == 0.0
    assert result["tx_count"] == 0
    assert result["categories"] == []
    assert result["merchants"] == []


def test_merchants_uses_merchant_name_when_available():
    from backend.analysis.monthly_report import get_monthly_report_data
    txs = [
        _tx(50.0, "dining", 2026, 4, description="SQ *CHIPOTLE 1234", merchant_name="Chipotle"),
        _tx(30.0, "dining", 2026, 4, description="SQ *CHIPOTLE 5678", merchant_name="Chipotle"),
    ]
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert result["merchants"][0]["name"] == "Chipotle"
    assert result["merchants"][0]["total"] == 80.0
