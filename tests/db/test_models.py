import pytest
from datetime import date, datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.db.models import Base, Transaction, Subscription, Sync, MonthlyReportCache

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_create_transaction(db):
    tx = Transaction(
        id="abc123",
        source="chase",
        date=date(2025, 5, 1),
        description="WHOLE FOODS",
        amount=-84.20,
        category="groceries",
        is_subscription=False,
    )
    db.add(tx)
    db.commit()
    result = db.get(Transaction, "abc123")
    assert result.description == "WHOLE FOODS"
    assert result.amount == -84.20

def test_create_subscription(db):
    sub = Subscription(
        id="sub1",
        description="NETFLIX.COM",
        amount=15.99,
        frequency="monthly",
        last_charged=date(2025, 5, 1),
        active=True,
    )
    db.add(sub)
    db.commit()
    result = db.get(Subscription, "sub1")
    assert result.frequency == "monthly"

def test_create_sync(db):
    sync = Sync(
        source="chase",
        synced_at=datetime(2025, 5, 1, 10, 0, 0),
        from_date=date(2025, 1, 1),
        to_date=date(2025, 5, 1),
        tx_count=42,
    )
    db.add(sync)
    db.commit()
    assert sync.id is not None

def test_create_monthly_report_cache(db):
    entry = MonthlyReportCache(year=2026, month=4, narrative="You spent a lot.", created_at=datetime.now(timezone.utc))
    db.add(entry)
    db.commit()
    result = db.query(MonthlyReportCache).filter_by(year=2026, month=4).first()
    assert result is not None
    assert result.narrative == "You spent a lot."
    assert result.year == 2026
    assert result.month == 4
