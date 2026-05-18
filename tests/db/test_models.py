import pytest
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.db.models import Base, Transaction, Subscription, Sync

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
        synced_at="2025-05-01T10:00:00",
        from_date=date(2025, 1, 1),
        to_date=date(2025, 5, 1),
        tx_count=42,
    )
    db.add(sync)
    db.commit()
    assert sync.id is not None
