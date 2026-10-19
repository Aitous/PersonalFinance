import pytest
from datetime import date
from unittest.mock import MagicMock
from backend.analysis.monthly_report import get_monthly_report_data


def _tx(amount, category, year, month, day=1, description="SHOP", merchant_name=None):
    tx = MagicMock()
    tx.amount = amount
    tx.category = category
    tx.date = date(year, month, day)
    tx.description = description
    tx.merchant_name = merchant_name
    return tx


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

    monthly_sub = MagicMock()
    monthly_sub.description = "Netflix"
    monthly_sub.amount = 15.99
    monthly_sub.frequency = "monthly"
    monthly_sub.last_charged = date(2026, 4, 3)   # next = May 3 — within 30 days
    monthly_sub.active = True

    annual_sub = MagicMock()
    annual_sub.description = "Adobe CC"
    annual_sub.amount = 599.0
    annual_sub.frequency = "annual"
    annual_sub.last_charged = date(2025, 5, 10)   # next = 2026-05-10 — within 30 days
    annual_sub.active = True

    far_sub = MagicMock()
    far_sub.description = "AWS"
    far_sub.amount = 9.99
    far_sub.frequency = "monthly"
    far_sub.last_charged = date(2026, 3, 1)        # next = Mar 31 — already past
    far_sub.active = True

    result = get_subscriptions_due([monthly_sub, annual_sub, far_sub], report_month_end=today)
    names = [r["description"] for r in result]
    assert "Netflix" in names
    assert "Adobe CC" in names
    assert "AWS" not in names


def test_inactive_subscriptions_excluded():
    from backend.analysis.monthly_report import get_subscriptions_due
    from datetime import date

    sub = MagicMock()
    sub.description = "Old Service"
    sub.amount = 9.99
    sub.frequency = "monthly"
    sub.last_charged = date(2026, 4, 1)
    sub.active = False

    result = get_subscriptions_due([sub], report_month_end=date(2026, 4, 30))
    assert result == []


def test_monthly_due_date_clamps_january_31_to_february_end():
    from backend.analysis.monthly_report import get_subscriptions_due

    sub = MagicMock()
    sub.description = "Monthly service"
    sub.amount = 10.0
    sub.frequency = "monthly"
    sub.last_charged = date(2026, 1, 31)
    sub.active = True

    result = get_subscriptions_due([sub], report_month_end=date(2026, 1, 31))
    assert result[0]["next_date"] == "2026-02-28"


def test_annual_due_date_clamps_leap_day_and_stale_charge_is_not_rolled_forward():
    from backend.analysis.monthly_report import get_subscriptions_due

    annual = MagicMock()
    annual.description = "Annual service"
    annual.amount = 100.0
    annual.frequency = "annual"
    annual.last_charged = date(2024, 2, 29)
    annual.active = True

    stale = MagicMock()
    stale.description = "Stale monthly service"
    stale.amount = 5.0
    stale.frequency = "monthly"
    stale.last_charged = date(2024, 3, 31)
    stale.active = True

    result = get_subscriptions_due([annual, stale], report_month_end=date(2025, 1, 31))
    assert result == [{
        "description": "Annual service", "amount": 100.0, "next_date": "2025-02-28",
    }]
