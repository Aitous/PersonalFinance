import pytest
from datetime import date
from unittest.mock import MagicMock


def _tx(amount, category, year, month, day=15):
    tx = MagicMock()
    tx.amount = amount
    tx.category = category
    tx.date = date(year, month, day)
    return tx


def test_averages_over_complete_months():
    from backend.analysis.insights import get_monthly_averages
    txs = [
        _tx(100.0, "dining", 2026, 1),
        _tx(200.0, "dining", 2026, 2),
        _tx(150.0, "groceries", 2026, 1),
        _tx(50.0, "groceries", 2026, 2),
    ]
    result = get_monthly_averages(txs, date_from=date(2026, 1, 1), date_to=date(2026, 2, 28))
    assert result["months_count"] == 2
    assert result["total_avg"] == 250.0
    cats = {c["category"]: c for c in result["categories"]}
    assert cats["dining"]["avg"] == 150.0
    assert cats["dining"]["pct"] == 60.0
    assert cats["groceries"]["avg"] == 100.0
    assert cats["groceries"]["pct"] == 40.0


def test_current_partial_month_excluded():
    from backend.analysis.insights import get_monthly_averages
    from datetime import date as _date
    from dateutil.relativedelta import relativedelta

    today = _date.today()
    two_months_ago = (today.replace(day=1) - relativedelta(months=2)).replace(day=15)
    one_month_ago = (today.replace(day=1) - relativedelta(months=1)).replace(day=15)

    txs = [
        _tx(100.0, "dining", two_months_ago.year, two_months_ago.month, two_months_ago.day),
        _tx(100.0, "dining", one_month_ago.year, one_month_ago.month, one_month_ago.day),
        _tx(999.0, "dining", today.year, today.month, 1),  # current month — should be excluded
    ]
    date_from = (today.replace(day=1) - relativedelta(months=2))
    result = get_monthly_averages(txs, date_from=date_from, date_to=today)
    assert result["total_avg"] == 100.0


def test_categories_sorted_descending_by_avg():
    from backend.analysis.insights import get_monthly_averages
    txs = [
        _tx(50.0, "dining", 2026, 1),
        _tx(200.0, "groceries", 2026, 1),
        _tx(10.0, "entertainment", 2026, 1),
    ]
    result = get_monthly_averages(txs, date_from=date(2026, 1, 1), date_to=date(2026, 1, 31))
    avgs = [c["avg"] for c in result["categories"]]
    assert avgs == sorted(avgs, reverse=True)


def test_empty_transactions_returns_zeros():
    from backend.analysis.insights import get_monthly_averages
    result = get_monthly_averages([], date_from=date(2026, 1, 1), date_to=date(2026, 3, 31))
    assert result["total_avg"] == 0.0
    assert result["categories"] == []
    assert result["months_count"] == 0


def test_months_with_spend_counts_correctly():
    from backend.analysis.insights import get_monthly_averages
    txs = [
        _tx(90.0, "dining", 2026, 1),
        _tx(90.0, "dining", 2026, 2),
        _tx(90.0, "dining", 2026, 3),
        _tx(300.0, "travel", 2026, 2),  # travel only in Feb
    ]
    result = get_monthly_averages(txs, date_from=date(2026, 1, 1), date_to=date(2026, 3, 31))
    cats = {c["category"]: c for c in result["categories"]}
    assert cats["travel"]["months_with_spend"] == 1
    assert cats["dining"]["months_with_spend"] == 3
