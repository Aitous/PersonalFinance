from datetime import date

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from backend.credentials import credentials_store
from backend.db.database import get_session
from backend.sync_service import SyncService
from backend.auth import hosted_auth_enabled

router = APIRouter()


class SyncRequest(BaseModel):
    bank: str
    since: date


@router.post("/sync")
def trigger_sync(req: SyncRequest, background_tasks: BackgroundTasks):
    if hosted_auth_enabled():
        raise HTTPException(status_code=404, detail="Use a linked Plaid account in hosted mode")
    username = credentials_store.get_bank_credential(req.bank, "username")
    password = credentials_store.get_bank_credential(req.bank, "password")
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail=f"No credentials found for {req.bank}. Add them in Settings.",
        )

    with get_session() as session:
        service = SyncService(session=session, llm=None)
        result = service.sync_bank(req.bank, since=req.since, username=username, password=password)
        if result.get("new_transaction_ids"):
            from backend.jobs.enrichment import enqueue_transactions
            result["enrichment_job_id"] = enqueue_transactions(session, result["new_transaction_ids"])
    if result.get("enrichment_job_id"):
        from backend.jobs.enrichment import run_job
        background_tasks.add_task(run_job, result["enrichment_job_id"])
    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return result
