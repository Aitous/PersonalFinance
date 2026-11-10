from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import reset_current_owner, set_current_owner
from backend.db import database
from backend.db.models import Base, EnrichmentJob, Transaction
import backend.db.tenancy  # noqa: F401 - register tenant-scoping ORM hooks


@pytest.fixture
def isolated_database(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    yield
    engine.dispose()


def _save_transaction(owner_id: str, transaction_id: str) -> None:
    owner_token = set_current_owner(owner_id)
    try:
        with database.get_session() as session:
            session.add(Transaction(
                id=transaction_id,
                source="test",
                date=date(2026, 1, 1),
                description=transaction_id,
                amount=10,
            ))
    finally:
        reset_current_owner(owner_token)


def test_queries_only_return_rows_owned_by_current_user(isolated_database):
    _save_transaction("user-a", "a-row")
    _save_transaction("user-b", "b-row")

    owner_token = set_current_owner("user-a")
    try:
        with database.get_session() as session:
            row_ids = session.scalars(
                select(Transaction.id).order_by(Transaction.id)
            ).all()
        assert row_ids == ["a-row"]
    finally:
        reset_current_owner(owner_token)


def test_cannot_write_a_row_for_another_user(isolated_database):
    owner_token = set_current_owner("user-a")
    try:
        with pytest.raises(PermissionError, match="another account"):
            with database.get_session() as session:
                session.add(Transaction(
                    id="foreign-row",
                    source="test",
                    date=date(2026, 1, 1),
                    description="foreign row",
                    amount=10,
                    owner_id="user-b",
                ))
    finally:
        reset_current_owner(owner_token)


def test_cannot_resume_another_users_job(isolated_database):
    from backend.jobs.enrichment import resume_stalled_job
    owner_token = set_current_owner("user-b")
    try:
        with database.get_session() as session:
            session.add(EnrichmentJob(id="other-job", mode="recategorize", status="running", total=1, done=0,
                                      updated_at=datetime.now(timezone.utc) - timedelta(hours=4)))
    finally:
        reset_current_owner(owner_token)
    owner_token = set_current_owner("user-a")
    try:
        assert resume_stalled_job("other-job") is False
    finally:
        reset_current_owner(owner_token)
    owner_token = set_current_owner("user-b")
    try:
        with database.get_session() as session:
            assert session.get(EnrichmentJob, "other-job").status == "running"
    finally:
        reset_current_owner(owner_token)
