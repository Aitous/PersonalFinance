import shutil
import hashlib
import hmac
import os
import stat
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from sqlalchemy import case, select, or_
from backend.db.database import get_session
from backend.db.models import Transaction, Account, ImportBatch, ImportedRow
from backend.parsers.csv_parser import parse_csv_detailed, BANK_SCHEMAS
from backend.sync_service import SyncService
from backend.ingestion import reconcile_account_overlaps, reconcile_legacy_csv_ids, reconcile_unassigned_description_overlaps, namespace_transaction_ids
from backend.auth import hosted_auth_enabled

router = APIRouter()

TRANSACTIONS_DIR = Path(__file__).parent.parent.parent / "transactions"
INBOX_DIR = TRANSACTIONS_DIR / "inbox"
PROCESSED_DIR = TRANSACTIONS_DIR / "processed"
MAX_INBOX_FILE_BYTES = 25 * 1024 * 1024

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


class InboxFileRequest(BaseModel):
    filename: str
    bank: Optional[str] = None
    account_id: Optional[str] = None


class InboxConfirmRequest(InboxFileRequest):
    checksum: str


def _inbox_file(filename: str) -> Path:
    if (not filename or filename in {".", ".."} or Path(filename).name != filename
            or "/" in filename or "\\" in filename or Path(filename).suffix.casefold() != ".csv"):
        raise HTTPException(status_code=422, detail="Choose a CSV file directly inside the import inbox.")
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if INBOX_DIR.is_symlink():
        raise HTTPException(status_code=422, detail="The import inbox cannot be a symbolic link.")
    path = INBOX_DIR / filename
    if path.is_symlink() or not path.is_file():
        raise HTTPException(status_code=404, detail="That CSV is no longer in the import inbox.")
    try:
        resolved = path.resolve(strict=True)
        if resolved.parent != INBOX_DIR.resolve(strict=True):
            raise HTTPException(status_code=422, detail="Inbox files must be stored directly in the import inbox.")
        if path.stat().st_size > MAX_INBOX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="CSV files in the import inbox must be 25 MiB or smaller.")
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Could not read that CSV from the import inbox.") from exc
    return path


def _read_inbox_file(filename: str) -> tuple[Path, bytes, str]:
    path = _inbox_file(filename)
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            file_stat = os.fstat(stream.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise HTTPException(status_code=422, detail="Inbox entries must be regular CSV files.")
            if file_stat.st_size > MAX_INBOX_FILE_BYTES:
                raise HTTPException(status_code=413, detail="CSV files in the import inbox must be 25 MiB or smaller.")
            content = stream.read(MAX_INBOX_FILE_BYTES + 1)
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Could not read that CSV from the import inbox.") from exc
    if len(content) > MAX_INBOX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="CSV files in the import inbox must be 25 MiB or smaller.")
    return path, content, hashlib.sha256(content).hexdigest()


def _archive_snapshot(source_name: str, checksum: str, content: bytes) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    base = Path(source_name).name
    stem = Path(base).stem or "statement"
    suffix = Path(base).suffix.casefold() or ".csv"
    candidates = [base, f"{stem}_{checksum[:8]}{suffix}"]
    candidates.extend(f"{stem}_{uuid.uuid4().hex[:10]}{suffix}" for _ in range(5))
    for name in candidates:
        target = PROCESSED_DIR / name
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                target.unlink()
            except OSError:
                pass
            raise
        return target
    raise OSError("Could not reserve a unique archive filename.")


def _commit_import(background_tasks: BackgroundTasks, bank: str, account_id: Optional[str], filename: str,
                   parsed, summary: dict, ambiguous_ids: set, archive_path: Path,
                   archive_content: bytes, retain_source: bool):
    if not parsed.transactions:
        raise HTTPException(status_code=422, detail="No valid transactions were found in this CSV.")
    archived_path = _archive_snapshot(archive_path.name, parsed.checksum, archive_content) if retain_source else None
    batch_id = str(uuid.uuid4())
    enrichment_job_id = None
    try:
        with get_session() as session:
            namespace_transaction_ids(parsed.transactions)
            duplicate_ids = {tx.id for tx in parsed.transactions if session.get(Transaction, tx.id) is not None}
            service = SyncService(session=session, llm=None)
            result = service.import_transactions(parsed.transactions, run_enrichment=False, commit=False)
            if result["new_transaction_ids"]:
                from backend.jobs.enrichment import enqueue_transactions
                enrichment_job_id = enqueue_transactions(session, result["new_transaction_ids"])
            batch = ImportBatch(
                id=batch_id, bank=bank, account_id=account_id, filename=filename,
                checksum=parsed.checksum, status="partial" if parsed.errors else "imported", input_count=parsed.input_rows,
                parsed_count=parsed.parsed_rows, rejected_count=len(parsed.errors),
                duplicate_count=result.get("duplicate_count", 0), new_count=result["tx_count"],
                from_date=min(t.date for t in parsed.transactions), to_date=max(t.date for t in parsed.transactions),
            )
            session.add(batch)
            for tx in parsed.transactions:
                duplicate = tx.id in duplicate_ids
                session.add(ImportedRow(batch_id=batch_id, transaction_id=tx.id,
                    row_number=getattr(tx, "_import_row_number", 0),
                    row_hash=hashlib.sha256((tx.raw_csv_row or "").encode()).hexdigest(), raw_data=tx.raw_csv_row,
                    reason="duplicate" if duplicate else ("possible ambiguous legacy account match" if tx.id in ambiguous_ids else None),
                    status="duplicate" if duplicate else "accepted"))
            for error in parsed.errors:
                session.add(ImportedRow(batch_id=batch_id, transaction_id=None, row_number=error["row_number"],
                    row_hash=hashlib.sha256(error.get("raw_data", "").encode()).hexdigest(),
                    raw_data=error.get("raw_data"), status="rejected", reason=error["reason"]))
    except Exception:
        for path in (archived_path, None if retain_source else archive_path):
            if path is not None:
                try:
                    path.unlink()
                except OSError:
                    pass
        raise

    if not retain_source:
        try:
            archive_path.unlink()
        except OSError:
            pass
    if enrichment_job_id:
        from backend.jobs.enrichment import run_job
        background_tasks.add_task(run_job, enrichment_job_id)
    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return {**summary, "tx_count": result["tx_count"], "total_parsed": parsed.parsed_rows,
            "new_transactions": result["tx_count"], "duplicate_rows": result.get("duplicate_count", 0),
            "batch_id": batch_id, "enrichment_job_id": enrichment_job_id}


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
def list_import_batches(limit: int = Query(10, ge=1, le=50)):
    with get_session() as session:
        batches = session.execute(
            select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(limit)
        ).scalars().all()
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
        reconcile_unassigned_description_overlaps(session, parsed.transactions)
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


@router.get("/import/inbox")
def list_import_inbox():
    if hosted_auth_enabled():
        raise HTTPException(status_code=404, detail="The local filesystem inbox is unavailable in hosted accounts; upload a file directly")
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if INBOX_DIR.is_symlink():
        raise HTTPException(status_code=422, detail="The import inbox cannot be a symbolic link.")
    with get_session() as session:
        imported_checksums = set(session.execute(select(ImportBatch.checksum)).scalars().all())
    files = []
    for path in sorted(INBOX_DIR.iterdir(), key=lambda item: item.name.casefold()):
        if path.suffix.casefold() != ".csv" or path.is_symlink() or not path.is_file():
            continue
        try:
            file_stat = path.stat()
        except OSError:
            continue
        checksum = None
        if file_stat.st_size <= MAX_INBOX_FILE_BYTES:
            try:
                _, _, checksum = _read_inbox_file(path.name)
            except HTTPException:
                continue
        files.append({
            "filename": path.name,
            "bank_guess": _detect_bank(path.name),
            "size_bytes": file_stat.st_size,
            "modified_at": datetime.fromtimestamp(file_stat.st_mtime, timezone.utc).isoformat(),
            "too_large": file_stat.st_size > MAX_INBOX_FILE_BYTES,
            "already_imported": checksum in imported_checksums if checksum else False,
        })
    return {"folder": "transactions/inbox", "files": files}


@router.post("/import/inbox/preview")
def preview_import_inbox_file(payload: InboxFileRequest):
    if hosted_auth_enabled():
        raise HTTPException(status_code=404, detail="The local filesystem inbox is unavailable in hosted accounts; upload a file directly")
    path, content, checksum = _read_inbox_file(payload.filename)
    bank = (payload.bank or _detect_bank(path.name) or "").casefold().strip()
    if bank not in BANK_SCHEMAS:
        raise HTTPException(status_code=422, detail="Choose Chase, Amex, or Discover for this file.")
    try:
        parsed, summary, _ = _preview_payload(bank, payload.account_id, path.name, content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not preview this CSV: {exc}") from exc
    return {
        **summary,
        "filename": path.name,
        "checksum": checksum,
        "sample_transactions": [
            {"date": tx.date.isoformat(), "description": tx.description, "amount": tx.amount,
             "category": tx.category or "other"}
            for tx in parsed.transactions[:8]
        ],
    }


@router.post("/import/inbox/confirm")
def confirm_import_inbox_file(payload: InboxConfirmRequest, background_tasks: BackgroundTasks):
    if hosted_auth_enabled():
        raise HTTPException(status_code=404, detail="The local filesystem inbox is unavailable in hosted accounts; upload a file directly")
    path, content, checksum = _read_inbox_file(payload.filename)
    if not hmac.compare_digest(checksum, payload.checksum):
        raise HTTPException(status_code=409, detail="This file changed after preview. Review the updated file before importing.")
    bank = (payload.bank or _detect_bank(path.name) or "").casefold().strip()
    if bank not in BANK_SCHEMAS:
        raise HTTPException(status_code=422, detail="Choose Chase, Amex, or Discover for this file.")
    try:
        parsed, summary, ambiguous_ids = _preview_payload(bank, payload.account_id, path.name, content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not import this CSV: {exc}") from exc
    if summary["new_transactions"] <= 0:
        raise HTTPException(status_code=409, detail="This file contains no new transactions to import.")
    return _commit_import(background_tasks, bank, payload.account_id, path.name,
                          parsed, summary, ambiguous_ids, path, content, retain_source=True)


@router.post("/import/folder", response_model=FolderImportResult)
def import_from_folder(background_tasks: BackgroundTasks):
    """Scan the transactions/ folder, parse all CSVs, and import into the database."""
    if hosted_auth_enabled():
        raise HTTPException(status_code=404, detail="Server-folder import is available only in local mode")
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
    return _commit_import(background_tasks, bank, account_id, file.filename or "upload.csv",
                          parsed, summary, ambiguous_ids, dest, content, retain_source=False)


import logging as _logging
import threading as _threading

_enrich_lock = _threading.Lock()
_enrich_logger = _logging.getLogger(__name__)


@router.get("/import/enrich/status")
def enrich_status(mode: Optional[str] = Query(default=None, pattern="^(enrich|recategorize)$")):
    from backend.db.models import EnrichmentJob
    from backend.jobs.enrichment import job_payload
    with get_session() as session:
        query = select(EnrichmentJob)
        if mode:
            query = query.where(EnrichmentJob.mode == mode)
        if mode:
            query = query.order_by(case((EnrichmentJob.status.in_(["pending", "running"]), 0), else_=1))
        job = session.execute(query.order_by(EnrichmentJob.created_at.desc())).scalars().first()
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


@router.post("/import/enrich/jobs/{job_id}/resume")
def resume_enrichment_job(job_id: str, background_tasks: BackgroundTasks):
    from backend.jobs.enrichment import resume_stalled_job, run_job
    if not resume_stalled_job(job_id):
        raise HTTPException(status_code=409, detail="This job is not stalled or is no longer available.")
    background_tasks.add_task(run_job, job_id)
    return {"id": job_id, "status": "pending"}


@router.post("/import/enrich")
def enrich_existing(background_tasks: BackgroundTasks, new_only: bool = False):
    """Queue an explicit, durable retry of missing and fallback enrichment."""
    from backend.jobs.enrichment import create_job, run_job
    job_id, created = create_job("enrich", new_only=new_only)
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
