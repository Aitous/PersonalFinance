"""Durable enrichment job creation and execution."""
from __future__ import annotations

import hashlib
import json
import uuid
import threading
from datetime import datetime, timezone

from sqlalchemy import select, update

from backend.db.database import get_session, invalidate_derived_data
from backend.db.models import CategoryRule, EnrichmentJob, EnrichmentJobItem, Transaction
from backend.analysis.merchant_normalizer import active_aliases, canonical_merchant
from backend.analysis.transaction_semantics import is_payment, purchase_amount

_runner_lock = threading.RLock()


def _input_hash(tx: Transaction) -> str:
    payload = [tx.id, tx.description, str(tx.amount), tx.date.isoformat(), tx.source]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def create_job(mode: str = "enrich", new_only: bool = False) -> tuple[str, bool]:
    """Create or return the active durable job for the requested mode."""
    if mode not in {"enrich", "recategorize"}:
        raise ValueError("unsupported enrichment mode")
    with get_session() as session:
        active = session.execute(select(EnrichmentJob).where(
            EnrichmentJob.mode == mode,
            EnrichmentJob.status.in_(["pending", "running"]),
        ).order_by(EnrichmentJob.created_at.desc())).scalars().first()
        if active:
            return active.id, False

        txs = session.execute(select(Transaction).order_by(Transaction.date, Transaction.id)).scalars().all()
        candidates = [tx for tx in txs if purchase_amount(tx) > 0 and not is_payment(tx)]
        if mode == "enrich":
            candidates = [tx for tx in candidates if tx.enrichment_status != "complete" and (
                tx.enrichment_status == "fallback" or tx.merchant_name is None or
                tx.merchant_type in (None, "unknown") or tx.category is None
            )]
            if new_only:
                queued_ids = set(session.execute(select(EnrichmentJobItem.transaction_id).join(
                    EnrichmentJob, EnrichmentJob.id == EnrichmentJobItem.job_id
                ).where(EnrichmentJob.mode == "enrich", EnrichmentJobItem.status.in_(["pending", "running", "failed"]))).scalars())
                candidates = [tx for tx in candidates if tx.id in queued_ids and tx.enrichment_status is None and not tx.raw_enrichment]
        job_id = str(uuid.uuid4())
        job = EnrichmentJob(id=job_id, mode=mode, status="pending", total=len(candidates), done=0)
        session.add(job)
        for tx in candidates:
            session.add(EnrichmentJobItem(job_id=job_id, transaction_id=tx.id,
                status="pending", attempts=0, input_hash=_input_hash(tx)))
        return job_id, True


def enqueue_transactions(session, transaction_ids: list[str], mode: str = "enrich") -> str | None:
    """Attach newly imported eligible rows to a durable job in the import transaction."""
    ids = list(dict.fromkeys(transaction_ids))
    candidates = []
    for tx_id in ids:
        tx = session.get(Transaction, tx_id)
        if not tx or purchase_amount(tx) <= 0 or is_payment(tx):
            continue
        if mode == "enrich" and tx.enrichment_status == "complete":
            continue
        candidates.append(tx)
    if not candidates:
        return None
    job = session.execute(select(EnrichmentJob).where(
        EnrichmentJob.mode == mode,
        EnrichmentJob.status == "pending",
    ).order_by(EnrichmentJob.created_at.desc())).scalars().first()
    if job is None:
        job = EnrichmentJob(id=str(uuid.uuid4()), mode=mode, status="pending", total=0, done=0)
        session.add(job)
        session.flush()
    existing_ids = set(session.execute(select(EnrichmentJobItem.transaction_id).where(
        EnrichmentJobItem.job_id == job.id
    )).scalars().all())
    added = 0
    for tx in candidates:
        if tx.id in existing_ids:
            continue
        session.add(EnrichmentJobItem(job_id=job.id, transaction_id=tx.id,
            status="pending", attempts=0, input_hash=_input_hash(tx)))
        added += 1
    job.total += added
    job.updated_at = datetime.now(timezone.utc)
    return job.id if added else None


def job_payload(session, job: EnrichmentJob) -> dict:
    items = session.execute(select(EnrichmentJobItem).where(
        EnrichmentJobItem.job_id == job.id
    )).scalars().all()
    counts = {state: sum(i.status == state for i in items) for state in ("pending", "running", "success", "fallback", "failed", "other")}
    return {"id": job.id, "mode": job.mode, "status": job.status, "total": job.total,
        "done": job.done, "remaining": max(job.total - job.done, 0), "error": job.error,
        "outcomes": counts, "created_at": job.created_at, "updated_at": job.updated_at}


def run_job(job_id: str, llm=None) -> None:
    """Serialize provider work across modes so a row cannot be enriched twice at once."""
    with _runner_lock:
        _run_job(job_id, llm)


def _run_job(job_id: str, llm=None) -> None:
    """Run pending rows and persist every row outcome so interrupted work resumes."""
    from backend.analysis.categorizer import BATCH_SIZE, Categorizer
    from backend.llm.factory import get_llm_provider

    try:
        # Claim in a short transaction so duplicate callbacks do not start a
        # second provider request for the same durable job.
        with get_session() as session:
            job = session.get(EnrichmentJob, job_id)
            job_mode = job.mode if job else "enrich"
            claimed = session.execute(update(EnrichmentJob).where(
                EnrichmentJob.id == job_id,
                EnrichmentJob.status == "pending",
            ).values(status="running", error=None, updated_at=datetime.now(timezone.utc)))
            if claimed.rowcount != 1:
                return
            running_items = session.execute(select(EnrichmentJobItem).where(
                EnrichmentJobItem.job_id == job_id,
                EnrichmentJobItem.status == "running",
            )).scalars().all()
            for item in running_items:
                item.status = "pending"
            pending_ids = session.execute(select(EnrichmentJobItem.transaction_id).where(
                EnrichmentJobItem.job_id == job_id,
                EnrichmentJobItem.status == "pending",
            ).order_by(EnrichmentJobItem.id)).scalars().all()
            if not pending_ids:
                job = session.get(EnrichmentJob, job_id)
                job.status = "done"
                items = session.execute(select(EnrichmentJobItem).where(
                    EnrichmentJobItem.job_id == job_id
                )).scalars().all()
                job.done = sum(item.status in {"success", "fallback", "failed", "other"} for item in items)
                job.updated_at = datetime.now(timezone.utc)
                return

        # Provider construction and network work happen with no DB session open.
        provider = llm if llm is not None else get_llm_provider()
        model = (getattr(provider, "model_name", None) or getattr(provider, "MODEL", None)
                 or getattr(getattr(provider, "_model", None), "model_name", None)
                 or type(provider).__name__)
        categorizer = Categorizer(provider)
        for start in range(0, len(pending_ids), BATCH_SIZE):
            batch_ids = pending_ids[start:start + BATCH_SIZE]
            with get_session() as session:
                batch_data = []
                for tx_id in batch_ids:
                    tx = session.get(Transaction, tx_id)
                    item = session.execute(select(EnrichmentJobItem).where(
                        EnrichmentJobItem.job_id == job_id,
                        EnrichmentJobItem.transaction_id == tx_id,
                    )).scalar_one()
                    if tx is None:
                        item.status, item.error = "failed", "Transaction no longer exists"
                        continue
                    item.status = "running"
                    item.attempts += 1
                    item.model = str(model) if model else None
                    item.input_hash = _input_hash(tx)
                    batch_data.append((tx.id, tx.source, tx.date, tx.description, tx.amount))
            # Construct detached, minimal snapshots; the provider can run for
            # minutes without holding a SQLite write transaction open.
            snapshots = [Transaction(id=row[0], source=row[1], date=row[2],
                         description=row[3], amount=row[4]) for row in batch_data]
            try:
                enrichments = categorizer._enrich_batch(snapshots)
            except Exception as exc:
                with get_session() as session:
                    for tx_id in batch_ids:
                        item = session.execute(select(EnrichmentJobItem).where(
                            EnrichmentJobItem.job_id == job_id,
                            EnrichmentJobItem.transaction_id == tx_id,
                        )).scalar_one()
                        if item.status == "running":
                            item.status, item.error = "failed", str(exc)
                            item.updated_at = datetime.now(timezone.utc)
                continue

            with get_session() as session:
                changed = False
                rules = {rule.merchant_key: rule.category for rule in session.execute(select(CategoryRule).where(CategoryRule.enabled.is_(True))).scalars().all()}
                aliases = active_aliases(session)
                for tx_id, *_ in batch_data:
                    tx = session.get(Transaction, tx_id)
                    item = session.execute(select(EnrichmentJobItem).where(
                        EnrichmentJobItem.job_id == job_id,
                        EnrichmentJobItem.transaction_id == tx_id,
                    )).scalar_one()
                    if tx is None:
                        item.status, item.error = "failed", "Transaction no longer exists"
                        continue
                    enrichment = enrichments.get(tx.id)
                    if enrichment is None:
                        item.status, item.error = "failed", "No row result returned"
                        continue
                    if enrichment.outcome == "fallback":
                        item.status = "fallback"
                        tx.enrichment_status = "fallback"
                        # Preserve valid fields and manual overlays on transient failure.
                        if tx.category is None:
                            tx.category = "other"
                            changed = True
                    else:
                        item.status = "other" if enrichment.category == "other" else "success"
                        tx.enrichment_status = "complete"
                        raw = enrichment.model_dump(exclude={"outcome"})
                        tx.raw_enrichment = json.dumps(raw, ensure_ascii=False)
                        manual = set(json.loads(tx.manual_fields or "[]"))
                        if job_mode == "recategorize" and not tx.manual_category:
                            tx.category = enrichment.category
                        elif not tx.manual_category and (not tx.category or tx.category == "other"):
                            tx.category = enrichment.category
                        for field in ("merchant_name", "city", "is_online", "merchant_type"):
                            if field in manual:
                                continue
                            value = getattr(enrichment, field)
                            # Null/unknown values from enrichment do not erase useful values.
                            if value is not None and value != "unknown":
                                setattr(tx, field, value)
                        changed = True
                    merchant = canonical_merchant(tx.merchant_name, aliases)
                    key = " ".join((merchant or "").split()).casefold()
                    if not tx.manual_category and key in rules and tx.category != rules[key]:
                        tx.category = rules[key]
                        changed = True
                    if item.status in {"success", "other"}:
                        item.status = "other" if tx.category == "other" else "success"
                    item.updated_at = datetime.now(timezone.utc)
                job = session.get(EnrichmentJob, job_id)
                all_items = session.execute(select(EnrichmentJobItem).where(EnrichmentJobItem.job_id == job_id)).scalars().all()
                job.done = sum(i.status in {"success", "fallback", "failed", "other"} for i in all_items)
                job.updated_at = datetime.now(timezone.utc)
                if changed:
                    invalidate_derived_data(session)

        with get_session() as session:
            job = session.get(EnrichmentJob, job_id)
            items = session.execute(select(EnrichmentJobItem).where(EnrichmentJobItem.job_id == job_id)).scalars().all()
            pending = any(i.status in {"pending", "running"} for i in items)
            failed = any(i.status == "failed" for i in items)
            job.status = "error" if failed else ("pending" if pending else "done")
            job.done = sum(i.status in {"success", "fallback", "failed", "other"} for i in items)
            job.updated_at = datetime.now(timezone.utc)
            if job.status in {"done", "error"} and items:
                from backend.analysis.recurring import reconcile_subscriptions
                all_transactions = session.execute(select(Transaction)).scalars().all()
                reconcile_subscriptions(session, all_transactions)
                invalidate_derived_data(session)
    except Exception as exc:
        with get_session() as session:
            job = session.get(EnrichmentJob, job_id)
            if job:
                job.status, job.error = "error", str(exc)
                job.updated_at = datetime.now(timezone.utc)
                for item in session.execute(select(EnrichmentJobItem).where(
                    EnrichmentJobItem.job_id == job_id,
                    EnrichmentJobItem.status == "running",
                )).scalars().all():
                    item.status, item.error = "failed", str(exc)
                    item.updated_at = datetime.now(timezone.utc)


def resume_interrupted_jobs() -> list[str]:
    """Mark durable in-flight work pending; caller decides when to schedule it."""
    with get_session() as session:
        jobs = session.execute(select(EnrichmentJob).where(
            EnrichmentJob.status.in_(["pending", "running"])
        )).scalars().all()
        ids = [job.id for job in jobs]
        for job in jobs:
            job.status = "pending"
            job.updated_at = datetime.now(timezone.utc)
        for item in session.execute(select(EnrichmentJobItem).where(
            EnrichmentJobItem.job_id.in_(ids) if ids else EnrichmentJobItem.job_id == ""
        )).scalars().all():
            if item.status == "running":
                item.status = "pending"
        return ids
