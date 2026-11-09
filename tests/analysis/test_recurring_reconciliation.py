import json
import hashlib
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.analysis.recurring import build_amount_profile, reconcile_subscriptions
from backend.analysis.subscription_detector import SubscriptionDetector
from backend.db.models import Base, Subscription, Transaction


def tx(tx_id, description, amount, tx_date, account_id="card-a", merchant_type=None):
    return Transaction(id=tx_id, source="chase", date=tx_date,
        description=description, amount=amount, account_id=account_id,
        merchant_type=merchant_type)


def test_detects_annual_from_two_positive_purchase_observations_and_excludes_payments():
    today = date.today()
    rows = [tx("annual1", "CLOUD BACKUP", 120, today - timedelta(days=365), merchant_type="cloud storage subscription"),
            tx("annual2", "CLOUD BACKUP", 120, today, merchant_type="cloud storage subscription"),
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
               today - timedelta(days=60 - 30 * i), merchant_type="streaming service") for i in range(3)]
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
               today - timedelta(days=150 - 30 * i), merchant_type="streaming service") for i in range(3)]
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
            tx(f"{account_id}-0", "MUSIC SERVICE", 9.99, today - timedelta(days=60), account_id, "streaming service"),
            tx(f"{account_id}-1", "MUSIC SERVICE", 9.99, today - timedelta(days=30), account_id, "streaming service"),
            tx(f"{account_id}-2", "MUSIC SERVICE", 9.99, today, account_id, "streaming service"),
        ])
    detected = SubscriptionDetector().detect(rows)
    assert len(detected) == 2
    assert {tuple(json.loads(sub.supporting_transaction_ids)) for sub in detected} == {
        ("card-a-0", "card-a-1", "card-a-2"),
        ("card-b-0", "card-b-1", "card-b-2")}


def test_redetect_removes_stale_automatic_candidates_and_clears_transaction_flags():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    today = date.today()
    rows = [tx("purchase1", "LOCAL BAKERY", 14, today - timedelta(days=30)),
            tx("purchase2", "LOCAL BAKERY", 14, today)]
    stale = Subscription(id="stale", description="LOCAL BAKERY", amount=14,
        frequency="monthly", last_charged=today, active=True, origin="detected",
        supporting_transaction_ids=json.dumps([row.id for row in rows]))
    for row in rows:
        row.is_subscription = True

    with Session(engine) as session:
        session.add_all([*rows, stale])
        reconcile_subscriptions(session, rows)
        session.flush()
        assert session.get(Subscription, "stale") is None
        assert all(row.is_subscription is False for row in rows)
    engine.dispose()


def test_legacy_series_refreshes_charge_evidence_but_keeps_custom_amount():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    today = date.today()
    rows = [tx(f"legacy{i}", "LEGACY MUSIC", 10,
               today - timedelta(days=60 - 30 * i), account_id=None,
               merchant_type="streaming service") for i in range(3)]
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
        assert legacy.last_charged == today
        assert legacy.active is True
        assert json.loads(legacy.supporting_transaction_ids) == [row.id for row in rows]
        assert all(row.is_subscription for row in rows)
    engine.dispose()


def test_reconciliation_collapses_legacy_descriptor_rows_by_charge_evidence():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    rows = [
        tx("maple-jan", "MAPLE RIDGE WATER 800-555-0101 CA AUTH-A", 52.10,
           date(2026, 1, 15), account_id=None, merchant_type="water provider"),
        tx("maple-feb-a", "MAPLE RIDGE WATER 800-555-0101 CA AUTH-B", 52.10,
           date(2026, 2, 15), account_id=None, merchant_type="water provider"),
        tx("maple-mar-a", "MAPLE RIDGE WATER 800-555-0101 CA AUTH-C", 52.10,
           date(2026, 3, 15), account_id=None, merchant_type="water provider"),
        tx("maple-feb-b", "MAPLE RIDGE WATER SERVICES 800-555-0102 CA REF-X", 52.10,
           date(2026, 2, 15), account_id=None, merchant_type="water provider"),
        tx("maple-mar-b", "MAPLE RIDGE WATER SERVICES 800-555-0102 CA REF-Y", 52.10,
           date(2026, 3, 15), account_id=None, merchant_type="water provider"),
        tx("maple-apr", "MAPLE RIDGE WATER SERVICES 800-555-0102 CA REF-Z", 52.10,
           date(2026, 4, 15), account_id=None, merchant_type="water provider"),
    ]
    first_ids = [row.id for row in rows[:3]]
    second_ids = [row.id for row in rows[3:]]
    with Session(engine) as session:
        session.add_all(rows)
        session.add_all([
            Subscription(id="legacy-maple-a", description="Maple Ridge Water", amount=52.10,
                frequency="monthly", last_charged=date(2026, 3, 15), active=True,
                origin="legacy", supporting_transaction_ids=json.dumps(first_ids)),
            Subscription(id="legacy-maple-b", description="Maple Ridge Water Services", amount=52.10,
                frequency="monthly", last_charged=date(2026, 4, 15), active=True,
                origin="legacy", supporting_transaction_ids=json.dumps(second_ids)),
        ])
        reconcile_subscriptions(session, rows)
        session.flush()

        subscriptions = session.query(Subscription).all()
        assert len(subscriptions) == 1
        assert subscriptions[0].last_charged == date(2026, 4, 15)
        assert len(json.loads(subscriptions[0].supporting_transaction_ids)) == 4
    engine.dispose()


def test_manual_series_matching_unassigned_detector_is_not_duplicated():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    today = date.today()
    rows = [tx(f"manual{i}", "USER CONFIRMED MUSIC", 10,
               today - timedelta(days=60 - 30 * i), account_id=None,
               merchant_type="streaming service") for i in range(3)]
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


def test_variable_amount_profile_uses_monthly_totals_and_latest_charge():
    rows = [
        tx("cloud-apr", "GOOGLE CLOUD", 10, date(2026, 4, 1), None, "cloud computing"),
        tx("cloud-may", "GOOGLE CLOUD", 20, date(2026, 5, 1), None, "cloud computing"),
        tx("cloud-jun-a", "GOOGLE CLOUD", 30, date(2026, 6, 1), None, "cloud computing"),
        tx("cloud-jun-b", "GOOGLE CLOUD", 5, date(2026, 6, 8), None, "cloud computing"),
    ]

    profile = build_amount_profile(rows, "monthly", as_of=date(2026, 7, 1))

    assert profile == {
        "amount_type": "variable",
        "average_monthly_amount": 21.67,
        "latest_charge_amount": 5.0,
        "latest_period_amount": 35.0,
    }
