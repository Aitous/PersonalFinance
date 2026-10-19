from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.analysis.recurring import reconcile_subscriptions
from backend.db.database import initialize_schema
from backend.db.models import Subscription


def test_pre_origin_subscription_migrates_as_preserved_legacy_state():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE subscriptions (
            id VARCHAR PRIMARY KEY, description VARCHAR NOT NULL, amount FLOAT NOT NULL,
            frequency VARCHAR NOT NULL, last_charged DATE, active BOOLEAN
        )"""))
        connection.execute(text("""INSERT INTO subscriptions
            (id, description, amount, frequency, last_charged, active)
            VALUES ('old-manual-id', 'User added service', 17.25, 'monthly', NULL, 1)"""))

    initialize_schema(engine)
    with Session(engine) as session:
        row = session.get(Subscription, "old-manual-id")
        assert row.origin == "legacy"
        assert row.dismissed is False
        assert row.user_active is None
        assert row.active is True
        reconcile_subscriptions(session, [])
        session.flush()
        assert row.active is True
        assert row.amount == 17.25
        assert row.description == "User added service"
    engine.dispose()
