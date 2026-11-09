"""Managed LLM request reservations and account/platform usage limits."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import os

from fastapi import HTTPException
from sqlalchemy import func, select, text

from backend.auth import current_owner_id, hosted_auth_enabled
from backend.db.database import get_session
from backend.db.models import AIConsent, LLMPlatformUsage, LLMUsage


def reserve_request(provider: str, model: str | None) -> int:
    owner_id = current_owner_id()
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    user_limit = int(os.getenv("LLM_MONTHLY_REQUEST_LIMIT", "100"))
    global_daily_limit = int(os.getenv("LLM_GLOBAL_DAILY_REQUEST_LIMIT", "2000"))
    with get_session() as session:
        consent = session.get(AIConsent, owner_id)
        if consent is None or not consent.accepted or consent.policy_version < 1:
            raise HTTPException(status_code=428, detail={
                "code": "ai_consent_required",
                "message": "Review and accept the AI data-use notice in the app before using AI features.",
            })
        # Serialize reservations across workers so simultaneous calls cannot
        # race past either cap. This lock is available on the hosted database.
        if session.bind and session.bind.dialect.name == "postgresql":
            session.execute(text("SELECT pg_advisory_xact_lock(hashtext('llm-usage-global'))"))
            session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"), {
                "lock_key": f"llm-usage:{owner_id}:{month_start:%Y-%m}"
            })
        user_count = session.scalar(select(func.count(LLMUsage.id)).where(LLMUsage.created_at >= month_start)) or 0
        global_count = session.scalar(select(func.count(LLMPlatformUsage.id)).where(
            LLMPlatformUsage.created_at >= day_start
        )) or 0
        if user_count >= user_limit:
            raise HTTPException(status_code=429, detail={
                "code": "llm_monthly_limit", "message": "Your monthly AI request allowance has been used.",
                "resets_at": (month_start.replace(day=28) + timedelta(days=4)).replace(day=1).isoformat(),
            })
        if global_count >= global_daily_limit:
            raise HTTPException(status_code=503, detail="AI requests are temporarily paused while the service reaches its daily safety limit.")
        usage = LLMUsage(feature="ai", provider=provider, model=model, status="reserved")
        session.add(usage)
        session.add(LLMPlatformUsage())
        session.flush()
        usage_id = usage.id
    return usage_id


def _finish_request(usage_id: int, status: str) -> None:
    owner_id = current_owner_id()
    with get_session() as session:
        usage = session.get(LLMUsage, usage_id)
        if usage is not None and usage.owner_id == owner_id:
            usage.status = status


class MeteredProvider:
    def __init__(self, provider, provider_name: str, model: str | None):
        self._provider = provider
        self._provider_name = provider_name
        self._model = model

    def complete(self, prompt: str) -> str:
        usage_id = reserve_request(self._provider_name, self._model) if hosted_auth_enabled() else None
        try:
            result = self._provider.complete(prompt)
        except Exception:
            if usage_id is not None:
                _finish_request(usage_id, "failed")
            raise
        if usage_id is not None:
            _finish_request(usage_id, "succeeded")
        return result

    def complete_json(self, prompt: str) -> str:
        usage_id = reserve_request(self._provider_name, self._model) if hosted_auth_enabled() else None
        try:
            result = self._provider.complete_json(prompt)
        except Exception:
            if usage_id is not None:
                _finish_request(usage_id, "failed")
            raise
        if usage_id is not None:
            _finish_request(usage_id, "succeeded")
        return result
