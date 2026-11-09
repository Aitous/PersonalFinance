from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import reset_current_owner, set_current_owner
from backend.db import database
from backend.db.models import AIConsent, Base, LLMPlatformUsage, LLMUsage
from backend.llm.metering import reserve_request


@pytest.fixture
def metering_database(monkeypatch):
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


def _accept_ai_consent(owner_id: str) -> None:
    owner_token = set_current_owner(owner_id)
    try:
        with database.get_session() as session:
            session.add(AIConsent(owner_id=owner_id, policy_version=1, accepted=True))
    finally:
        reset_current_owner(owner_token)


def test_monthly_request_limit_is_enforced_for_each_user(metering_database, monkeypatch):
    owner_id = "user-a"
    monkeypatch.setenv("LLM_MONTHLY_REQUEST_LIMIT", "1")
    monkeypatch.setenv("LLM_GLOBAL_DAILY_REQUEST_LIMIT", "10")
    _accept_ai_consent(owner_id)

    owner_token = set_current_owner(owner_id)
    try:
        with database.get_session() as session:
            session.add(LLMUsage(provider="gemini", model="test-model", status="succeeded"))

        with pytest.raises(HTTPException) as exc_info:
            reserve_request("gemini", "test-model")
        assert exc_info.value.status_code == 429
        assert exc_info.value.detail["code"] == "llm_monthly_limit"
    finally:
        reset_current_owner(owner_token)


def test_platform_daily_request_limit_is_enforced(metering_database, monkeypatch):
    owner_id = "user-a"
    monkeypatch.setenv("LLM_MONTHLY_REQUEST_LIMIT", "10")
    monkeypatch.setenv("LLM_GLOBAL_DAILY_REQUEST_LIMIT", "1")
    _accept_ai_consent(owner_id)

    owner_token = set_current_owner(owner_id)
    try:
        with database.get_session() as session:
            session.add(LLMPlatformUsage(created_at=datetime.now(timezone.utc)))

        with pytest.raises(HTTPException) as exc_info:
            reserve_request("gemini", "test-model")
        assert exc_info.value.status_code == 503
    finally:
        reset_current_owner(owner_token)
