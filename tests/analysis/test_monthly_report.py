import pytest
from datetime import date
from unittest.mock import MagicMock
from types import SimpleNamespace
from backend.analysis.monthly_report import get_monthly_report_data


def _tx(amount, category, year, month, day=1, description="SHOP", merchant_name=None):
    tx = MagicMock()
    tx.amount = amount
    tx.category = category
    tx.date = date(year, month, day)
    tx.description = description
    tx.merchant_name = merchant_name
    return tx


def _subscription(description, amount, frequency, last_charged, active=True):
    return SimpleNamespace(
        description=description,
        amount=amount,
        frequency=frequency,
        last_charged=last_charged,
        active=active,
        dismissed=False,
        user_active=None,
        origin="legacy",
        supporting_transaction_ids="[]",
    )


def test_total_and_tx_count():
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
    txs = [_tx(float(i), f"cat{i}", 2026, 4, description=f"MERCHANT{i}") for i in range(1, 12)]
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert len(result["merchants"]) == 8
    # First merchant should be the one with the highest amount
    assert result["merchants"][0]["total"] == 11.0


def test_empty_month_returns_zeros():
    txs = [_tx(100.0, "dining", 2026, 3)]  # only prior month has data
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert result["total"] == 0.0
    assert result["tx_count"] == 0
    # Categories should include prior-only categories with current=0
    assert len(result["categories"]) == 1
    assert result["categories"][0]["name"] == "dining"
    assert result["categories"][0]["current"] == 0.0
    assert result["categories"][0]["prior"] == 100.0
    assert result["merchants"] == []


def test_merchants_uses_merchant_name_when_available():
    txs = [
        _tx(50.0, "dining", 2026, 4, description="SQ *CHIPOTLE 1234", merchant_name="Chipotle"),
        _tx(30.0, "dining", 2026, 4, description="SQ *CHIPOTLE 5678", merchant_name="Chipotle"),
    ]
    result = get_monthly_report_data(txs, year=2026, month=4)
    assert result["merchants"][0]["name"] == "Chipotle"
    assert result["merchants"][0]["total"] == 80.0


def test_categories_includes_prior_only_categories():
    txs = [
        _tx(100.0, "dining", 2026, 4),
        _tx(200.0, "travel", 2026, 3),   # travel only in prior month
    ]
    result = get_monthly_report_data(txs, year=2026, month=4)
    names = [c["name"] for c in result["categories"]]
    assert "travel" in names
    travel = next(c for c in result["categories"] if c["name"] == "travel")
    assert travel["current"] == 0.0
    assert travel["prior"] == 200.0


def test_prior_month_wraps_to_december_for_january():
    txs = [
        _tx(150.0, "dining", 2026, 1),
        _tx(80.0, "dining", 2025, 12),   # December prior year
    ]
    result = get_monthly_report_data(txs, year=2026, month=1)
    assert result["total"] == 150.0
    assert result["prev_total"] == 80.0


def test_subscriptions_due_within_next_calendar_month():
    from backend.analysis.monthly_report import get_subscriptions_due
    from datetime import date

    today = date(2026, 4, 30)  # last day of report month

    monthly_sub = _subscription("Netflix", 15.99, "monthly", date(2026, 4, 3))
    annual_sub = _subscription("Adobe CC", 599.0, "annual", date(2025, 5, 10))
    far_sub = _subscription("AWS", 9.99, "monthly", date(2026, 3, 1))

    result = get_subscriptions_due([monthly_sub, annual_sub, far_sub], report_month_end=today)
    names = [r["description"] for r in result]
    assert "Netflix" in names
    assert "Adobe CC" in names
    assert "AWS" not in names


def test_inactive_subscriptions_excluded():
    from backend.analysis.monthly_report import get_subscriptions_due
    from datetime import date

    sub = _subscription("Old Service", 9.99, "monthly", date(2026, 4, 1), active=False)

    result = get_subscriptions_due([sub], report_month_end=date(2026, 4, 30))
    assert result == []


def test_monthly_due_date_clamps_january_31_to_february_end():
    from backend.analysis.monthly_report import get_subscriptions_due

    sub = _subscription("Monthly service", 10.0, "monthly", date(2026, 1, 31))

    result = get_subscriptions_due([sub], report_month_end=date(2026, 1, 31))
    assert result[0]["next_date"] == "2026-02-28"


def test_annual_due_date_clamps_leap_day_and_stale_charge_is_not_rolled_forward():
    from backend.analysis.monthly_report import get_subscriptions_due

    annual = _subscription("Annual service", 100.0, "annual", date(2024, 2, 29))
    stale = _subscription("Stale monthly service", 5.0, "monthly", date(2024, 3, 31))

    result = get_subscriptions_due([annual, stale], report_month_end=date(2025, 1, 31))
    assert result == [{
        "description": "Annual service", "amount": 100.0, "next_date": "2025-02-28",
    }]
