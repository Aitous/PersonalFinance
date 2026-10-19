import json
import hashlib
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.analysis.recurring import reconcile_subscriptions
from backend.analysis.subscription_detector import SubscriptionDetector
from backend.db.models import Base, Subscription, Transaction


def tx(tx_id, description, amount, tx_date, account_id="card-a"):
    return Transaction(id=tx_id, source="chase", date=tx_date,
        description=description, amount=amount, account_id=account_id)


def test_detects_annual_from_two_positive_purchase_observations_and_excludes_payments():
    today = date.today()
    rows = [tx("annual1", "CLOUD BACKUP", 120, today - timedelta(days=365)),
            tx("annual2", "CLOUD BACKUP", 120, today),
            tx("payment1", "CLOUD BACKUP PAYMENT", 120, today - timedelta(days=365)),
            tx("payment2", "CLOUD BACKUP PAYMENT", 120, today, "card-b")]
    detected = SubscriptionDetector().detect(rows)
    assert len(detected) == 1
    assert detected[0].frequency == "annual"
    assert json.loads(detected[0].supporting_transaction_ids) == ["annual1", "annual2"]


def test_reconciliation_keeps_manual_and_dismissed_rows_and_sets_support_flags():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    today = date.today()
    rows = [tx(f"stream{i}", "STREAMING SERVICE", 12.99,
               today - timedelta(days=60 - 30 * i)) for i in range(3)]
    candidate = SubscriptionDetector().detect(rows)[0]
    with Session(engine) as session:
        session.add_all(rows)
        session.add(Subscription(id=candidate.id, description=candidate.description,
            amount=candidate.amount, frequency=candidate.frequency,
            last_charged=candidate.last_charged, active=False, dismissed=True,
            origin="detected"))
        session.add(Subscription(id="manual-id", description="Gym", amount=25,
            frequency="monthly", last_charged=today, active=True, origin="manual"))
        session.flush()
        reconcile_subscriptions(session, rows)
        session.flush()
        assert session.get(Subscription, "manual-id").active is True
        dismissed = session.get(Subscription, candidate.id)
        assert dismissed.dismissed is True
        assert dismissed.active is False
        assert all(not row.is_subscription for row in rows)
    engine.dispose()


def test_detected_stale_monthly_series_keeps_links_and_becomes_inactive():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    today = date.today()
    rows = [tx(f"old{i}", "OLD MONTHLY", 8,
               today - timedelta(days=150 - 30 * i)) for i in range(3)]
    with Session(engine) as session:
        session.add_all(rows)
        detected = reconcile_subscriptions(session, rows)
        assert len(detected) == 1
        assert detected[0].active is False
        assert all(row.is_subscription for row in rows)
        assert json.loads(detected[0].supporting_transaction_ids) == [row.id for row in rows]
    engine.dispose()


def test_known_accounts_produce_separate_recurring_series():
    today = date.today()
    rows = []
    for account_id in ("card-a", "card-b"):
        rows.extend([
            tx(f"{account_id}-1", "MUSIC SERVICE", 9.99, today - timedelta(days=30), account_id),
            tx(f"{account_id}-2", "MUSIC SERVICE", 9.99, today, account_id),
        ])
    detected = SubscriptionDetector().detect(rows)
    assert len(detected) == 2
    assert {tuple(json.loads(sub.supporting_transaction_ids)) for sub in detected} == {
        ("card-a-1", "card-a-2"), ("card-b-1", "card-b-2")}


def test_confirmed_legacy_series_gets_links_without_changing_legacy_values():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    today = date.today()
    rows = [tx(f"legacy{i}", "LEGACY MUSIC", 10,
               today - timedelta(days=60 - 30 * i), account_id=None) for i in range(3)]
    legacy_id = hashlib.md5("LEGACY MUSIC".encode()).hexdigest()
    with Session(engine) as session:
        session.add_all(rows)
        legacy = Subscription(id=legacy_id, description="LEGACY MUSIC", amount=19,
            frequency="monthly", last_charged=today - timedelta(days=30),
            active=False, origin="legacy")
        session.add(legacy)
        reconcile_subscriptions(session, rows)
        session.flush()
        assert len(session.query(Subscription).all()) == 1
        assert legacy.amount == 19
        assert legacy.active is False
        assert json.loads(legacy.supporting_transaction_ids) == [row.id for row in rows]
        assert all(row.is_subscription for row in rows)
    engine.dispose()


def test_manual_series_matching_unassigned_detector_is_not_duplicated():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    today = date.today()
    rows = [tx(f"manual{i}", "USER CONFIRMED MUSIC", 10,
               today - timedelta(days=60 - 30 * i), account_id=None) for i in range(3)]
    with Session(engine) as session:
        session.add_all(rows)
        manual = Subscription(id="user-created-id", description="USER CONFIRMED MUSIC",
            amount=25, frequency="monthly", last_charged=today - timedelta(days=1),
            active=True, origin="manual")
        session.add(manual)
        reconcile_subscriptions(session, rows)
        session.flush()
        assert len(session.query(Subscription).all()) == 1
        assert manual.amount == 25
        assert manual.active is True
        assert all(row.is_subscription for row in rows)
    engine.dispose()
