import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File
from pydantic import BaseModel

from sqlalchemy import select
from backend.db.database import get_session
from backend.db.models import Transaction
from backend.llm.factory import get_llm_provider
from backend.parsers.csv_parser import parse_csv, BANK_SCHEMAS
from backend.sync_service import SyncService

router = APIRouter()

TRANSACTIONS_DIR = Path(__file__).parent.parent.parent / "transactions"
PROCESSED_DIR = TRANSACTIONS_DIR / "processed"

FILENAME_HINTS = {
    "chase": ["chase"],
    "amex": ["amex", "american_express", "americanexpress"],
    "discover": ["discover", "dfs"],
}


def _detect_bank(filename: str) -> Optional[str]:
    lower = filename.lower()
    for bank, hints in FILENAME_HINTS.items():
        if any(h in lower for h in hints):
            return bank
    return None


class FolderImportResult(BaseModel):
    files_processed: int
    files_skipped: int
    total_new_transactions: int
    details: list[dict]


@router.post("/import/folder", response_model=FolderImportResult)
def import_from_folder():
    """Scan the transactions/ folder, parse all CSVs, and import into the database."""
    if not TRANSACTIONS_DIR.exists():
        raise HTTPException(status_code=404, detail="transactions/ folder not found")

    PROCESSED_DIR.mkdir(exist_ok=True)

    csv_files = list(TRANSACTIONS_DIR.glob("*.csv")) + list(TRANSACTIONS_DIR.glob("*.CSV"))
    if not csv_files:
        raise HTTPException(status_code=404, detail="No CSV files found in transactions/ folder")

    files_processed = 0
    files_skipped = 0
    total_new = 0
    details = []

    llm = get_llm_provider()

    for csv_path in csv_files:
        bank = _detect_bank(csv_path.name)
        if not bank:
            files_skipped += 1
            details.append({"file": csv_path.name, "status": "skipped", "reason": "could not detect bank from filename"})
            continue

        try:
            transactions = parse_csv(csv_path, bank)
            with get_session() as session:
                service = SyncService(session=session, llm=llm)
                result = service.import_transactions(transactions)
            total_new += result["tx_count"]
            files_processed += 1
            details.append({
                "file": csv_path.name,
                "bank": bank,
                "status": "imported",
                "new_transactions": result["tx_count"],
                "total_parsed": result["total_parsed"],
            })
            shutil.move(str(csv_path), str(PROCESSED_DIR / csv_path.name))
        except Exception as e:
            files_skipped += 1
            details.append({"file": csv_path.name, "status": "error", "reason": str(e)})

    return FolderImportResult(
        files_processed=files_processed,
        files_skipped=files_skipped,
        total_new_transactions=total_new,
        details=details,
    )


@router.post("/import/upload")
async def upload_csv(bank: str, file: UploadFile = File(...)):
    """Upload a single CSV file for a specific bank."""
    if bank not in BANK_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Unknown bank '{bank}'. Valid: {list(BANK_SCHEMAS.keys())}")

    TRANSACTIONS_DIR.mkdir(exist_ok=True)
    dest = TRANSACTIONS_DIR / f"{bank}_{file.filename}"
    content = await file.read()
    dest.write_bytes(content)

    try:
        transactions = parse_csv(dest, bank)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(e))

    with get_session() as session:
        service = SyncService(session=session, llm=get_llm_provider())
        result = service.import_transactions(transactions)

    PROCESSED_DIR.mkdir(exist_ok=True)
    shutil.move(str(dest), str(PROCESSED_DIR / dest.name))

    return {"bank": bank, **result}


import logging as _logging
import threading as _threading

_enrich_lock = _threading.Lock()
_enrich_logger = _logging.getLogger(__name__)
_enrich_state: dict = {"running": False, "total": 0, "done": 0, "error": None}


@router.get("/import/enrich/status")
def enrich_status():
    remaining = _enrich_state["total"] - _enrich_state["done"]
    return {
        "running": _enrich_state["running"],
        "total": _enrich_state["total"],
        "done": _enrich_state["done"],
        "remaining": remaining,
        "error": _enrich_state["error"],
    }


@router.post("/import/enrich")
def enrich_existing(background_tasks: BackgroundTasks):
    """Enrich all transactions that are missing merchant_name."""
    from backend.analysis.categorizer import Categorizer

    def _run():
        if not _enrich_lock.acquire(blocking=False):
            _enrich_logger.info("Enrichment already running, skipping duplicate request")
            return
        _enrich_state.update({"running": True, "total": 0, "done": 0, "error": None})
        try:
            llm = get_llm_provider()
            categorizer = Categorizer(llm=llm)
            with get_session() as session:
                txs = session.execute(
                    select(Transaction).where(Transaction.merchant_name.is_(None))
                ).scalars().all()
                session.expunge_all()

            _enrich_state["total"] = len(txs)
            if not txs:
                return

            enrichments = categorizer.categorize(list(txs))

            with get_session() as session:
                for tx_id, enrich in enrichments.items():
                    tx = session.get(Transaction, tx_id)
                    if tx:
                        tx.merchant_name = enrich.merchant_name
                        tx.city = enrich.city
                        tx.is_online = enrich.is_online
                        tx.merchant_type = enrich.merchant_type
                        if not tx.category or tx.category == "other":
                            tx.category = enrich.category
                    _enrich_state["done"] += 1
                session.commit()
            _enrich_logger.info("Enrichment complete: %d transactions processed", len(txs))
        except Exception as exc:
            _enrich_logger.exception("Enrichment background task failed")
            _enrich_state["error"] = str(exc)
        finally:
            _enrich_state["running"] = False
            _enrich_lock.release()

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Enriching transactions in background"}
