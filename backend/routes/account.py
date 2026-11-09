"""Authenticated account usage, export, and self-service deletion."""
from datetime import datetime, timedelta, timezone
import os

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from backend.auth import current_owner_id
from backend.db.database import get_session
from backend.db.models import (
    AIConsent, Account, AccountDeletion, CategoryRule, EnrichmentJob, EnrichmentJobItem, ImportBatch,
    ImportedRow, LLMUsage, DataRevision, MerchantAlias, MonthlyCategoryExplanationCache,
    MonthlyReportCache, PlaidItem, PlaidTransactionIdentity, Subscription,
    Sync, Transaction,
)

router = APIRouter(prefix="/account", tags=["account"])

class AIConsentRequest(BaseModel):
    accepted: bool


@router.get("/usage")
def account_usage():
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with get_session() as session:
        used = session.scalar(select(func.count(LLMUsage.id)).where(LLMUsage.created_at >= month_start)) or 0
    return {"ai_requests_used": used, "ai_requests_limit": int(os.getenv("LLM_MONTHLY_REQUEST_LIMIT", "100")),
            "resets_at": (month_start.replace(day=28) + timedelta(days=4)).replace(day=1).isoformat()}


@router.get("/deletion-status")
def account_deletion_status():
    from sqlalchemy import text
    with get_session() as session:
        status = session.execute(text("SELECT status FROM account_deletions WHERE owner_id = :owner_id"),
                                 {"owner_id": current_owner_id()}).scalar_one_or_none()
    return {"status": status or "active"}


@router.get("/ai-consent")
def get_ai_consent():
    with get_session() as session:
        consent = session.get(AIConsent, current_owner_id())
        return {"accepted": bool(consent and consent.accepted and consent.policy_version >= 1), "policy_version": consent.policy_version if consent else None}


@router.post("/ai-consent")
def save_ai_consent(body: AIConsentRequest):
    if not body.accepted:
        raise HTTPException(status_code=422, detail="AI consent must be accepted to enable AI features")
    with get_session() as session:
        consent = session.get(AIConsent, current_owner_id())
        if consent is None:
            session.add(AIConsent(owner_id=current_owner_id(), policy_version=1, accepted=True, accepted_at=datetime.now(timezone.utc)))
        else:
            consent.policy_version = 1
            consent.accepted = True
            consent.accepted_at = datetime.now(timezone.utc)
            consent.revoked_at = None
    return {"accepted": True, "policy_version": 1}


@router.delete("/ai-consent")
def revoke_ai_consent():
    with get_session() as session:
        consent = session.get(AIConsent, current_owner_id())
        if consent is not None:
            consent.accepted = False
            consent.revoked_at = datetime.now(timezone.utc)
    return {"accepted": False}


@router.get("/export")
def export_account_data():
    """Return the user's ledger and related personal records as JSON."""
    models = {
        "transactions": Transaction, "accounts": Account, "subscriptions": Subscription,
        "imports": ImportBatch, "import_rows": ImportedRow, "category_rules": CategoryRule,
        "merchant_aliases": MerchantAlias, "plaid_items": PlaidItem, "sync_history": Sync,
        "ai_usage": LLMUsage, "ai_privacy_consent": AIConsent,
    }
    with get_session() as session:
        data = {}
        for name, model in models.items():
            rows = session.scalars(select(model)).all()
            serialized = []
            for row in rows:
                record = {}
                for column in model.__table__.columns:
                    if column.name in {"owner_id", "cursor", "access_token_encrypted"}:
                        continue
                    attr_name = "metadata_" if model is Transaction and column.name == "metadata" else column.name
                    record[column.name] = getattr(row, attr_name)
                serialized.append(record)
            data[name] = serialized
    return {"exported_at": datetime.now(timezone.utc).isoformat(), "format_version": 1, "data": data}


@router.delete("")
def delete_account():
    """Delete tenant data and the Supabase identity after provider revocation."""
    project_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not project_url or not service_key:
        raise HTTPException(status_code=503, detail="Account deletion is not configured")
    owner_id = current_owner_id()
    with get_session() as session:
        active_jobs = session.scalars(select(EnrichmentJob).where(EnrichmentJob.status.in_(["pending", "running"]))).all()
        if active_jobs:
            raise HTTPException(status_code=409, detail="Wait for active AI processing to finish before deleting your account")
        items = session.scalars(select(PlaidItem)).all()
        if items:
            # Do not report a successful deletion until Plaid connections have
            # been explicitly disconnected through the normal provider flow.
            raise HTTPException(status_code=409, detail="Disconnect all linked bank accounts before deleting your account")
        deletion = session.get(AccountDeletion, owner_id)
        if deletion is None:
            session.add(AccountDeletion(owner_id=owner_id, status="deleting"))
        for model in (
            EnrichmentJobItem, EnrichmentJob, ImportedRow, ImportBatch,
            PlaidTransactionIdentity, PlaidItem, Subscription, Transaction,
            AIConsent, Account, CategoryRule, MerchantAlias, Sync, DataRevision, MonthlyCategoryExplanationCache,
            MonthlyReportCache, LLMUsage,
        ):
            for row in session.scalars(select(model)).all():
                session.delete(row)
    # The service key is only used server-side. The API still verifies the
    # user's access token before reaching this route.
    response = requests.delete(
        f"{project_url}/auth/v1/admin/users/{owner_id}",
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"}, timeout=15,
    )
    if response.status_code not in (200, 204):
        raise HTTPException(status_code=502, detail="Your finance data was removed, but account closure did not finish. Contact support to complete deletion.")
    with get_session() as session:
        deletion = session.get(AccountDeletion, owner_id)
        if deletion is not None:
            deletion.status = "deleted"
    return {"status": "deleted"}
