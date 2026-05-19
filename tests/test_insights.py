import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock

def _tx(description, amount, category="dining", days_ago=0, source="chase"):
    tx = MagicMock()
    tx.description = description
    tx.amount = amount
    tx.category = category
    tx.date = date.today() - timedelta(days=days_ago)
    tx.source = source
    return tx

# ── anomalies ──────────────────────────────────────────────────────────────

def test_anomaly_detected_when_current_is_2x_average():
    from backend.analysis.insights import get_spending_anomalies
    today = date.today()
    txs = []
    for months_back in [1, 2, 3]:
        for _ in range(3):
            d = today.replace(day=5) - timedelta(days=months_back * 30)
            tx = MagicMock()
            tx.description = "RESTAURANT"
            tx.amount = 35.0
            tx.category = "dining"
            tx.date = d
            tx.source = "chase"
            txs.append(tx)
    # Current month: 4 transactions totalling $260
    for i in range(4):
        tx = MagicMock()
        tx.description = "RESTAURANT"
        tx.amount = 65.0
        tx.category = "dining"
        tx.date = today.replace(day=i + 1)
        tx.source = "chase"
        txs.append(tx)
    result = get_spending_anomalies(txs)
    assert len(result) == 1
    assert result[0]["category"] == "dining"
    assert result[0]["ratio"] >= 2.0

def test_no_anomaly_when_below_2x():
    from backend.analysis.insights import get_spending_anomalies
    today = date.today()
    txs = []
    for months_back in [1, 2, 3]:
        for _ in range(3):
            d = today.replace(day=5) - timedelta(days=months_back * 30)
            tx = MagicMock()
            tx.description = "RESTAURANT"
            tx.amount = 50.0
            tx.category = "dining"
            tx.date = d
            tx.source = "chase"
            txs.append(tx)
    for _ in range(3):
        tx = MagicMock()
        tx.description = "RESTAURANT"
        tx.amount = 55.0
        tx.category = "dining"
        tx.date = today.replace(day=1)
        tx.source = "chase"
        txs.append(tx)
    result = get_spending_anomalies(txs)
    assert result == []

def test_no_anomaly_when_fewer_than_3_txs_current_month():
    from backend.analysis.insights import get_spending_anomalies
    today = date.today()
    txs = []
    for months_back in [1, 2, 3]:
        for _ in range(3):
            d = today.replace(day=5) - timedelta(days=months_back * 30)
            tx = MagicMock()
            tx.description = "RESTAURANT"
            tx.amount = 30.0
            tx.category = "dining"
            tx.date = d
            tx.source = "chase"
            txs.append(tx)
    # Only 2 txs this month but very large
    for _ in range(2):
        tx = MagicMock()
        tx.description = "RESTAURANT"
        tx.amount = 500.0
        tx.category = "dining"
        tx.date = today.replace(day=1)
        tx.source = "chase"
        txs.append(tx)
    result = get_spending_anomalies(txs)
    assert result == []

# ── duplicates ─────────────────────────────────────────────────────────────

def test_duplicate_same_amount_within_7_days():
    from backend.analysis.insights import get_duplicate_charges
    today = date.today()
    txs = [
        _tx("NETFLIX.COM", 15.49, "subscriptions", days_ago=3),
        _tx("NETFLIX.COM", 15.49, "subscriptions", days_ago=0),
    ]
    result = get_duplicate_charges(txs)
    assert len(result) == 1
    assert result[0]["merchant"] == "NETFLIX.COM"
    assert result[0]["amount"] == 15.49

def test_no_duplicate_beyond_7_days():
    from backend.analysis.insights import get_duplicate_charges
    txs = [
        _tx("NETFLIX.COM", 15.49, "subscriptions", days_ago=35),
        _tx("NETFLIX.COM", 15.49, "subscriptions", days_ago=0),
    ]
    result = get_duplicate_charges(txs)
    assert result == []

def test_no_duplicate_for_recurring_merchant():
    from backend.analysis.insights import get_duplicate_charges
    today = date.today()
    # 8 monthly charges of same amount — should be treated as recurring, not duplicate
    txs = [_tx("SPOTIFY", 9.99, "subscriptions", days_ago=i*30) for i in range(8)]
    result = get_duplicate_charges(txs)
    assert result == []

# ── price increases ────────────────────────────────────────────────────────

def test_price_increase_detected():
    from backend.analysis.insights import get_price_increases
    today = date.today()
    txs = [_tx("SPOTIFY", 9.99, "subscriptions", days_ago=(9-i)*30) for i in range(8)]
    txs.append(_tx("SPOTIFY", 13.99, "subscriptions", days_ago=30))
    txs.append(_tx("SPOTIFY", 13.99, "subscriptions", days_ago=0))
    result = get_price_increases(txs)
    assert len(result) == 1
    assert result[0]["merchant"] == "SPOTIFY"
    assert result[0]["old_amount"] == 9.99
    assert result[0]["new_amount"] == 13.99

def test_no_price_increase_within_5_pct():
    from backend.analysis.insights import get_price_increases
    txs = [_tx("SPOTIFY", 9.99, "subscriptions", days_ago=i*30) for i in range(10)]
    txs.append(_tx("SPOTIFY", 10.29, "subscriptions", days_ago=0))  # ~3% increase
    result = get_price_increases(txs)
    assert result == []

# ── merchant breakdown ─────────────────────────────────────────────────────

def test_merchant_breakdown_aggregates_and_sorts():
    from backend.analysis.insights import get_merchant_breakdown
    txs = [
        _tx("AMAZON.COM", 50.0, "shopping", days_ago=5),
        _tx("AMAZON.COM", 30.0, "shopping", days_ago=2),
        _tx("COSTCO WHSE", 200.0, "groceries", days_ago=3),
    ]
    result = get_merchant_breakdown(txs)
    assert result[0]["name"] == "COSTCO WHSE"
    assert result[0]["total"] == 200.0
    assert result[1]["name"] == "AMAZON.COM"
    assert result[1]["total"] == 80.0
    assert result[1]["tx_count"] == 2

# ── day of week ────────────────────────────────────────────────────────────

def test_day_of_week_returns_7_entries():
    from backend.analysis.insights import get_day_of_week
    txs = [_tx("SHOP", 10.0, days_ago=i) for i in range(14)]
    result = get_day_of_week(txs)
    assert len(result["days"]) == 7
    assert "weekend_pct" in result
    assert 0 <= result["weekend_pct"] <= 100

# ── year over year ─────────────────────────────────────────────────────────

def test_yoy_insufficient_data_when_only_one_year():
    from backend.analysis.insights import get_year_over_year
    txs = [_tx("SHOP", 100.0, days_ago=i*10) for i in range(5)]
    result = get_year_over_year(txs)
    assert result["insufficient_data"] is True

def test_yoy_returns_two_years():
    from backend.analysis.insights import get_year_over_year
    today = date.today()
    txs = []
    for i in range(5):
        tx = MagicMock()
        tx.description = "SHOP"
        tx.amount = 100.0
        tx.category = "shopping"
        tx.date = today.replace(year=today.year - 1, month=i + 1, day=1)
        tx.source = "chase"
        txs.append(tx)
    for i in range(3):
        tx = MagicMock()
        tx.description = "SHOP"
        tx.amount = 120.0
        tx.category = "shopping"
        tx.date = today.replace(month=i + 1, day=1)
        tx.source = "chase"
        txs.append(tx)
    result = get_year_over_year(txs)
    assert result["insufficient_data"] is False
    assert len(result["years"]) == 2
    assert result["on_pace"] is not None
