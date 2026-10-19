import pytest
from datetime import date
from backend.analysis.subscription_detector import SubscriptionDetector
from backend.db.models import Transaction

def make_tx(id, description, amount, tx_date):
    return Transaction(
        id=id, source="chase", date=tx_date,
        description=description, amount=amount
    )

def test_detects_monthly_subscription():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "NETFLIX.COM", 15.99, date(2025, 3, 15)),
        make_tx("t2", "NETFLIX.COM", 15.99, date(2025, 4, 15)),
        make_tx("t3", "NETFLIX.COM", 15.99, date(2025, 5, 15)),
    ]
    subs = detector.detect(txs)
    assert len(subs) == 1
    assert subs[0].description == "NETFLIX.COM"
    assert subs[0].frequency == "monthly"
    assert subs[0].amount == 15.99

def test_detects_annual_subscription():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "AMAZON PRIME", 139.00, date(2024, 5, 1)),
        make_tx("t2", "AMAZON PRIME", 139.00, date(2025, 5, 1)),
    ]
    subs = detector.detect(txs)
    assert len(subs) == 1
    assert subs[0].frequency == "annual"

def test_ignores_non_recurring():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "RANDOM STORE", -50.00, date(2025, 3, 1)),
        make_tx("t2", "ANOTHER STORE", -75.00, date(2025, 4, 15)),
    ]
    subs = detector.detect(txs)
    assert subs == []

def test_amount_tolerance():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "SPOTIFY", 10.99, date(2025, 3, 5)),
        make_tx("t2", "SPOTIFY", 10.99, date(2025, 4, 5)),
        make_tx("t3", "SPOTIFY", 11.49, date(2025, 5, 5)),  # tax variation
    ]
    subs = detector.detect(txs)
    assert len(subs) == 1
