from datetime import date
from fastapi import APIRouter
from pydantic import BaseModel
from backend.credentials import credentials_store
from backend.db.database import get_session
from backend.llm.factory import get_llm_provider
from backend.sync_service import SyncService

router = APIRouter()

class SyncRequest(BaseModel):
    bank: str
    since: date

@router.post("/sync")
async def trigger_sync(req: SyncRequest):
    username = credentials_store.get_bank_credential(req.bank, "username")
    password = credentials_store.get_bank_credential(req.bank, "password")
    if not username or not password:
        return {"error": f"No credentials found for {req.bank}. Add them in Settings."}

    with get_session() as session:
        service = SyncService(session=session, llm=get_llm_provider())
        result = await service.sync_bank(req.bank, since=req.since, username=username, password=password)
    return result
