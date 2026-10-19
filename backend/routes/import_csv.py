import shutil
import hashlib
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from sqlalchemy import select, or_
from backend.db.database import get_session
from backend.db.models import Transaction, Account, ImportBatch, ImportedRow
from backend.parsers.csv_parser import parse_csv_detailed, BANK_SCHEMAS
from backend.sync_service import SyncService
from backend.ingestion import reconcile_account_overlaps, reconcile_legacy_csv_ids

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


@router.get("/accounts")
def list_accounts():
    with get_session() as session:
        accounts = session.execute(select(Account).order_by(Account.bank, Account.name)).scalars().all()
        return [{"id": a.id, "bank": a.bank, "name": a.name, "last4": a.last4} for a in accounts]


class AccountCreate(BaseModel):
    bank: str
    name: str
    last4: Optional[str] = None
    external_id: Optional[str] = None


@router.post("/accounts")
def create_account(payload: AccountCreate):
    bank = payload.bank.casefold().strip()
    name = payload.name.strip()
    last4 = payload.last4.strip() if payload.last4 else None
    if bank not in BANK_SCHEMAS:
        raise HTTPException(status_code=422, detail=f"Unknown bank '{bank}'")
    if not name:
        raise HTTPException(status_code=422, detail="Account name is required")
    if last4 and (len(last4) != 4 or not last4.isdigit()):
        raise HTTPException(status_code=422, detail="last4 must be four digits")
    account = Account(id=str(uuid.uuid4()), bank=bank, name=name, last4=last4, external_id=payload.external_id.strip() if payload.external_id else None)
    with get_session() as session:
        session.add(account)
        session.flush()
        return {"id": account.id, "bank": account.bank, "name": account.name, "last4": account.last4}


@router.get("/import/batches")
def list_import_batches():
    with get_session() as session:
        batches = session.execute(select(ImportBatch).order_by(ImportBatch.created_at.desc())).scalars().all()
        return [{"id": b.id, "bank": b.bank, "account_id": b.account_id, "filename": b.filename,
            "checksum": b.checksum, "status": b.status, "input_rows": b.input_count,
            "parsed_rows": b.parsed_count, "rejected_rows": b.rejected_count,
            "duplicate_rows": b.duplicate_count, "new_transactions": b.new_count,
            "from_date": b.from_date, "to_date": b.to_date, "created_at": b.created_at}
            for b in batches]


def _preview_payload(bank: str, account_id: Optional[str], filename: str, content: bytes):
    if bank not in BANK_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Unknown bank '{bank}'. Valid: {list(BANK_SCHEMAS.keys())}")
    with get_session() as session:
        account = session.get(Account, account_id) if account_id else None
        if account_id and (not account or account.bank != bank):
            raise HTTPException(status_code=422, detail="Account does not exist or belongs to a different bank")
        with tempfile.NamedTemporaryFile(suffix=".csv") as temp:
            temp.write(content)
            temp.flush()
            parsed = parse_csv_detailed(Path(temp.name), bank, account_id)
        reconcile_account_overlaps(session, parsed.transactions)
        reconcile_legacy_csv_ids(session, parsed.transactions)
        duplicates = sum(1 for tx in parsed.transactions if session.get(Transaction, tx.id) is not None)
        ambiguous_ids = set()
        if account_id:
            for tx in parsed.transactions:
                legacy_match = session.execute(select(Transaction.id).where(
                    Transaction.source == bank, Transaction.account_id.is_(None),
                    Transaction.date == tx.date, Transaction.description == tx.description,
                    or_(Transaction.amount == tx.amount, Transaction.amount == -tx.amount),
                ).limit(1)).scalar_one_or_none()
                if legacy_match:
                    ambiguous_ids.add(tx.id)
        warnings = list(parsed.warnings)
        if ambiguous_ids:
            warnings.append(f"{len(ambiguous_ids)} row(s) resemble legacy transactions with unknown accounts; they were kept separate.")
        result = {
            "bank": bank, "account_id": account_id, "input_rows": parsed.input_rows,
            "parsed_rows": parsed.parsed_rows, "rejected_rows": len(parsed.errors),
            "duplicate_rows": duplicates, "new_transactions": parsed.parsed_rows - duplicates,
            "errors": parsed.errors, "warnings": warnings,
        }
        return parsed, result, ambiguous_ids


@router.post("/import/preview")
async def preview_csv(bank: str = Form(...), account_id: Optional[str] = Form(None), file: UploadFile = File(...)):
    try:
        _, result, _ = _preview_payload(bank, account_id, file.filename or "upload.csv", await file.read())
        return {**result, "tx_count": result["new_transactions"], "total_parsed": result["parsed_rows"]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/import/folder", response_model=FolderImportResult)
def import_from_folder(background_tasks: BackgroundTasks):
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

    for csv_path in csv_files:
        bank = _detect_bank(csv_path.name)
        if not bank:
            files_skipped += 1
            details.append({"file": csv_path.name, "status": "skipped", "reason": "could not detect bank from filename"})
            continue

        try:
            parsed, summary, ambiguous_ids = _preview_payload(bank, None, csv_path.name, csv_path.read_bytes())
            enrichment_job_id = None
            with get_session() as session:
                duplicate_ids = {tx.id for tx in parsed.transactions if session.get(Transaction, tx.id) is not None}
                service = SyncService(session=session, llm=None)
                result = service.import_transactions(parsed.transactions, run_enrichment=False, commit=False)
                if result["new_transaction_ids"]:
                    from backend.jobs.enrichment import enqueue_transactions
                    enrichment_job_id = enqueue_transactions(session, result["new_transaction_ids"])
                batch_id = str(uuid.uuid4())
                session.add(ImportBatch(id=batch_id, bank=bank, account_id=None, filename=csv_path.name,
                    checksum=parsed.checksum, input_count=parsed.input_rows, parsed_count=parsed.parsed_rows,
                    rejected_count=len(parsed.errors), duplicate_count=result.get("duplicate_count", 0),
                    new_count=result["tx_count"], status="partial" if parsed.errors else "imported",
                    from_date=min(t.date for t in parsed.transactions), to_date=max(t.date for t in parsed.transactions)))
                for tx in parsed.transactions:
                    duplicate = tx.id in duplicate_ids
                    session.add(ImportedRow(batch_id=batch_id, transaction_id=tx.id,
                        row_number=getattr(tx, "_import_row_number", 0), row_hash=hashlib.sha256((tx.raw_csv_row or "").encode()).hexdigest(),
                        raw_data=tx.raw_csv_row, reason="duplicate" if duplicate else ("possible ambiguous legacy account match" if tx.id in ambiguous_ids else None),
                        status="duplicate" if duplicate else "accepted"))
                for error in parsed.errors:
                    session.add(ImportedRow(batch_id=batch_id, transaction_id=None, row_number=error["row_number"],
                        row_hash=hashlib.sha256(error.get("raw_data", "").encode()).hexdigest(), raw_data=error.get("raw_data"),
                        status="rejected", reason=error["reason"]))
            total_new += result["tx_count"]
            files_processed += 1
            details.append({
                "file": csv_path.name,
                "bank": bank,
                "status": "imported",
                "new_transactions": result["tx_count"],
                "total_parsed": result["total_parsed"],
                "rejected_rows": len(parsed.errors),
                "duplicate_rows": result.get("duplicate_count", 0),
                "input_rows": parsed.input_rows,
                "errors": parsed.errors,
                "warnings": summary["warnings"],
                "batch_id": batch_id,
                "enrichment_job_id": enrichment_job_id,
            })
            if enrichment_job_id:
                from backend.jobs.enrichment import run_job
                background_tasks.add_task(run_job, enrichment_job_id)
            shutil.move(str(csv_path), str(PROCESSED_DIR / csv_path.name))
        except Exception as e:
            files_skipped += 1
            details.append({"file": csv_path.name, "status": "error", "reason": str(e)})

    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return FolderImportResult(
        files_processed=files_processed,
        files_skipped=files_skipped,
        total_new_transactions=total_new,
        details=details,
    )


@router.post("/import/upload")
async def upload_csv(background_tasks: BackgroundTasks, bank: str = Form(...), account_id: Optional[str] = Form(None), file: UploadFile = File(...)):
    """Upload a single CSV file for a specific bank."""
    if bank not in BANK_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Unknown bank '{bank}'. Valid: {list(BANK_SCHEMAS.keys())}")

    content = await file.read()
    try:
        parsed, summary, ambiguous_ids = _preview_payload(bank, account_id, file.filename or "upload.csv", content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    TRANSACTIONS_DIR.mkdir(exist_ok=True)
    dest = TRANSACTIONS_DIR / f"{bank}_{uuid.uuid4().hex}.csv"
    dest.write_bytes(content)
    batch_id = str(uuid.uuid4())
    enrichment_job_id = None
    with get_session() as session:
        duplicate_ids = {tx.id for tx in parsed.transactions if session.get(Transaction, tx.id) is not None}
        service = SyncService(session=session, llm=None)
        result = service.import_transactions(parsed.transactions, run_enrichment=False, commit=False)
        if result["new_transaction_ids"]:
            from backend.jobs.enrichment import enqueue_transactions
            enrichment_job_id = enqueue_transactions(session, result["new_transaction_ids"])
        batch = ImportBatch(
            id=batch_id, bank=bank, account_id=account_id, filename=file.filename or "upload.csv",
            checksum=parsed.checksum, status="partial" if parsed.errors else "imported", input_count=parsed.input_rows,
            parsed_count=parsed.parsed_rows, rejected_count=len(parsed.errors),
            duplicate_count=result.get("duplicate_count", 0), new_count=result["tx_count"],
            from_date=min(t.date for t in parsed.transactions), to_date=max(t.date for t in parsed.transactions),
        )
        session.add(batch)
        for tx in parsed.transactions:
            duplicate = tx.id in duplicate_ids
            session.add(ImportedRow(batch_id=batch_id, transaction_id=tx.id, row_number=getattr(tx, "_import_row_number", 0),
                row_hash=hashlib.sha256((tx.raw_csv_row or "").encode()).hexdigest(),
                raw_data=tx.raw_csv_row,
                reason="duplicate" if duplicate else ("possible ambiguous legacy account match" if tx.id in ambiguous_ids else None),
                status="duplicate" if duplicate else "accepted"))
        for error in parsed.errors:
            session.add(ImportedRow(batch_id=batch_id, transaction_id=None, row_number=error["row_number"],
                row_hash=hashlib.sha256(error.get("raw_data", "").encode()).hexdigest(),
                raw_data=error.get("raw_data"), status="rejected", reason=error["reason"]))

    PROCESSED_DIR.mkdir(exist_ok=True)
    shutil.move(str(dest), str(PROCESSED_DIR / dest.name))
    if enrichment_job_id:
        from backend.jobs.enrichment import run_job
        background_tasks.add_task(run_job, enrichment_job_id)
    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return {**summary, "tx_count": result["tx_count"], "total_parsed": parsed.parsed_rows,
            "new_transactions": result["tx_count"], "duplicate_rows": result.get("duplicate_count", 0),
            "batch_id": batch_id, "enrichment_job_id": enrichment_job_id}


import logging as _logging
import threading as _threading

_enrich_lock = _threading.Lock()
_enrich_logger = _logging.getLogger(__name__)


@router.get("/import/enrich/status")
def enrich_status():
    from backend.db.models import EnrichmentJob
    from backend.jobs.enrichment import job_payload
    with get_session() as session:
        job = session.execute(select(EnrichmentJob).order_by(EnrichmentJob.created_at.desc())).scalars().first()
        if not job:
            return {"status": "idle", "total": 0, "done": 0, "remaining": 0, "error": None}
        payload = job_payload(session, job)
        return {**payload, "total": payload["total"], "done": payload["done"], "remaining": payload["remaining"]}


@router.get("/import/enrich/jobs/{job_id}")
def enrich_job_status(job_id: str):
    from backend.db.models import EnrichmentJob
    from backend.jobs.enrichment import job_payload
    with get_session() as session:
        job = session.get(EnrichmentJob, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="enrichment job not found")
        return job_payload(session, job)


@router.post("/import/enrich")
def enrich_existing(background_tasks: BackgroundTasks):
    """Queue an explicit, durable retry of missing and fallback enrichment."""
    from backend.jobs.enrichment import create_job, run_job
    job_id, created = create_job("enrich")
    if created:
        background_tasks.add_task(run_job, job_id)
        from backend.routes.search import _embed_all
        background_tasks.add_task(_embed_all, get_session)
    return {"id": job_id, "status": "pending", "message": "Enrichment queued"}


@router.post("/import/recategorize")
def recategorize_all(background_tasks: BackgroundTasks):
    """Queue explicit full recategorization while preserving manual categories."""
    from backend.jobs.enrichment import create_job, run_job
    job_id, created = create_job("recategorize")
    if created:
        background_tasks.add_task(run_job, job_id)
        from backend.routes.search import _embed_all
        background_tasks.add_task(_embed_all, get_session)
    return {"id": job_id, "status": "pending", "message": "Recategorization queued"}


@router.post("/import/normalize-merchants")
def normalize_merchant_names():
    """Return unaccepted alias proposals; only explicit mappings are applied."""
    from backend.analysis.merchant_normalizer import normalize_merchants
    result = normalize_merchants()
    return result
