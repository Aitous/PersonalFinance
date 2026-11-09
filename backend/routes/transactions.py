from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from math import isfinite
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from backend.db.database import get_session, invalidate_derived_data
from backend.db.models import CategoryRule, EnrichmentJob, EnrichmentJobItem, ImportBatch, ImportedRow, MerchantAlias, Subscription, Transaction
from backend.transaction_filters import transaction_query
from backend.analysis.merchant_normalizer import active_aliases, canonical_merchant
from backend.analysis.recurring import (
    is_effectively_active, reconcile_subscriptions, subscription_amount_profile,
)

router = APIRouter()

class CategoryUpdate(BaseModel):
    category: str

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        from backend.analysis.categorizer import VALID_CATEGORIES
        if value not in VALID_CATEGORIES:
            raise ValueError("unknown category")
        return value

class BulkCategoryUpdate(CategoryUpdate):
    ids: list[str] = Field(min_length=1, max_length=5000)

    @field_validator("ids")
    @classmethod
    def unique_ids(cls, value):
        if any(not item.strip() for item in value) or len(value) != len(set(value)):
            raise ValueError("transaction IDs must be nonempty and unique")
        return value

class CategoryRuleCreate(CategoryUpdate):
    merchant: str = Field(max_length=200)

    @field_validator("merchant")
    @classmethod
    def valid_merchant(cls, value):
        value = " ".join(value.split())
        if not value:
            raise ValueError("merchant is required")
        return value

class CategoryRuleEnabled(BaseModel):
    enabled: bool


def _rule_payload(rule):
    return {"id": rule.id, "merchant": rule.merchant, "category": rule.category, "enabled": rule.enabled}


@router.get("/category-rules")
def list_category_rules():
    with get_session() as session:
        rules = session.execute(select(CategoryRule).order_by(CategoryRule.merchant)).scalars().all()
        return [_rule_payload(rule) for rule in rules]


@router.post("/category-rules")
def save_category_rule(body: CategoryRuleCreate):
    with get_session() as session:
        merchant = canonical_merchant(body.merchant, active_aliases(session)) or body.merchant
        key = " ".join(merchant.split()).casefold()
        rule = session.execute(select(CategoryRule).where(CategoryRule.merchant_key == key)).scalar_one_or_none()
        if rule is None:
            rule = CategoryRule(merchant_key=key, merchant=merchant, category=body.category, enabled=True)
            session.add(rule)
        else:
            rule.category, rule.merchant, rule.enabled = body.category, merchant, True
        session.flush()
        return _rule_payload(rule)


@router.patch("/category-rules/{rule_id}")
def set_category_rule_enabled(rule_id: int, body: CategoryRuleEnabled):
    with get_session() as session:
        rule = session.get(CategoryRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Category rule not found")
        rule.enabled = body.enabled
        return _rule_payload(rule)

class TransactionCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    merchant_name: Optional[str] = None
    city: Optional[str] = None
    merchant_type: Optional[str] = None
    is_online: Optional[bool] = None

class MerchantAliasCreate(BaseModel):
    alias: str
    canonical: str

class MerchantAliasEnabled(BaseModel):
    enabled: bool

@router.get("/transactions")
def list_transactions(q=Depends(transaction_query)):
    with get_session() as session:
        txs = session.execute(q).scalars().all()
        aliases = active_aliases(session)
        return [
            {
                "id": tx.id,
                "source": tx.source,
                "date": tx.date.isoformat(),
                "description": tx.description,
                "amount": tx.amount,
                "category": tx.category,
                "is_subscription": tx.is_subscription,
                "merchant_name": canonical_merchant(tx.merchant_name, aliases),
                "city": tx.city,
                "is_online": tx.is_online,
                "merchant_type": tx.merchant_type,
            }
            for tx in txs
        ]

@router.get("/transactions/export.csv")
def export_transactions_csv(q=Depends(transaction_query)):
    import csv
    import io
    from fastapi.responses import StreamingResponse

    with get_session() as session:
        txs = session.execute(q).scalars().all()
        aliases = active_aliases(session)

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["date", "description", "merchant_name", "category", "amount", "source", "city", "merchant_type"])
        for tx in txs:
            writer.writerow([tx.date.isoformat(), tx.description, canonical_merchant(tx.merchant_name, aliases) or "", tx.category or "",
                             tx.amount, tx.source, tx.city or "", tx.merchant_type or ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.read()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=transactions.csv"})

@router.patch("/transactions/bulk/category")
def update_categories(body: BulkCategoryUpdate, background_tasks: BackgroundTasks):
    with get_session() as session:
        transactions = session.execute(select(Transaction).where(Transaction.id.in_(body.ids))).scalars().all()
        if len(transactions) != len(body.ids):
            raise HTTPException(status_code=404, detail="Some selected transactions no longer exist. Refresh and try again.")
        for tx in transactions:
            tx.category = body.category
            tx.manual_category = True
        reconcile_subscriptions(session, session.execute(select(Transaction)).scalars().all())
        invalidate_derived_data(session)
    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return {"updated": len(transactions), "category": body.category}

@router.patch("/transactions/{tx_id}/category")
def update_category(tx_id: str, body: CategoryUpdate, background_tasks: BackgroundTasks):
    with get_session() as session:
        tx = session.get(Transaction, tx_id)
        if not tx:
            raise HTTPException(status_code=404, detail="not found")
        tx.category = body.category
        tx.manual_category = True
        reconcile_subscriptions(session, session.execute(select(Transaction)).scalars().all())
        invalidate_derived_data(session)
        result = {"id": tx_id, "category": tx.category}
    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return result


@router.get("/transactions/{tx_id}/provenance")
def transaction_provenance(tx_id: str):
    with get_session() as session:
        tx = session.get(Transaction, tx_id)
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")
        imports = session.execute(select(ImportedRow, ImportBatch).join(
            ImportBatch, ImportedRow.batch_id == ImportBatch.id
        ).where(ImportedRow.transaction_id == tx_id).order_by(ImportBatch.created_at.desc())).all()
        jobs = session.execute(select(EnrichmentJobItem, EnrichmentJob).join(
            EnrichmentJob, EnrichmentJobItem.job_id == EnrichmentJob.id
        ).where(EnrichmentJobItem.transaction_id == tx_id).order_by(EnrichmentJobItem.updated_at.desc()).limit(10)).all()
        return {
            "manual_category": bool(tx.manual_category),
            "enrichment_status": tx.enrichment_status,
            "imports": [{"filename": batch.filename, "bank": batch.bank, "imported_at": batch.created_at,
                         "row_number": row.row_number, "status": row.status} for row, batch in imports],
            "enrichment_history": [{"mode": job.mode, "status": item.status, "model": item.model,
                                    "updated_at": item.updated_at} for item, job in jobs],
            "note": "Imported file records and enrichment attempts shown where available; a complete edit history is not yet recorded.",
        }

@router.patch("/transactions/{tx_id}")
def update_transaction_fields(tx_id: str, body: TransactionCorrection, background_tasks: BackgroundTasks):
    with get_session() as session:
        tx = session.get(Transaction, tx_id)
        if not tx:
            raise HTTPException(status_code=404, detail="not found")
        fields = set(body.model_fields_set)
        if not fields:
            raise HTTPException(status_code=422, detail="At least one field is required")
        manual = set(__import__("json").loads(tx.manual_fields or "[]"))
        for field in fields:
            setattr(tx, field, getattr(body, field))
            manual.add(field)
        tx.manual_fields = __import__("json").dumps(sorted(manual))
        reconcile_subscriptions(session, session.execute(select(Transaction)).scalars().all())
        invalidate_derived_data(session)
        result = {"id": tx_id, **{field: getattr(tx, field) for field in fields}}
    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return result


@router.delete("/transactions/{tx_id}")
def delete_transaction(tx_id: str):
    with get_session() as session:
        tx = session.get(Transaction, tx_id)
        if not tx:
            raise HTTPException(status_code=404, detail="Transaction not found")
        audit_rows = session.execute(select(ImportedRow).where(
            ImportedRow.transaction_id == tx_id
        )).scalars().all()
        for row in audit_rows:
            row.transaction_id = None
            row.status = "deleted"
            row.reason = "Transaction deleted by user"
        session.delete(tx)
        session.flush()
        reconcile_subscriptions(session, session.execute(select(Transaction)).scalars().all())
        invalidate_derived_data(session)
    return {"deleted": tx_id}

@router.get("/subscriptions")
def list_subscriptions():
    import json

    with get_session() as session:
        subs = session.execute(select(Subscription).where(Subscription.dismissed.is_(False))).scalars().all()
        linked_ids = []
        ids_by_subscription = {}
        for sub in subs:
            try:
                ids = json.loads(sub.supporting_transaction_ids or "[]")
                ids = ids if isinstance(ids, list) else []
            except (TypeError, ValueError):
                ids = []
            ids_by_subscription[sub.id] = list(dict.fromkeys(ids))
            linked_ids.extend(ids)
        transactions_by_id = {}
        if linked_ids:
            linked = session.execute(select(Transaction).where(Transaction.id.in_(set(linked_ids)))).scalars().all()
            transactions_by_id = {tx.id: tx for tx in linked}
        results = []
        for sub in subs:
            linked_transactions = [transactions_by_id[tx_id] for tx_id in ids_by_subscription[sub.id]
                                   if tx_id in transactions_by_id]
            results.append({
                "id": sub.id,
                "description": sub.description,
                "amount": sub.amount,
                "frequency": sub.frequency,
                "last_charged": sub.last_charged.isoformat() if sub.last_charged else None,
                "active": is_effectively_active(sub),
                "origin": sub.origin,
                "dismissed": sub.dismissed,
                **subscription_amount_profile(sub, linked_transactions),
                "supporting_transactions": [
                    {
                        "id": tx.id,
                        "date": tx.date.isoformat(),
                        "description": tx.description,
                        "amount": tx.amount,
                        "source": tx.source,
                        "merchant_name": tx.merchant_name,
                    }
                    for tx in linked_transactions
                ],
            })
        return results

@router.post("/subscriptions/redetect")
def redetect_subscriptions():
    with get_session() as session:
        all_txs = session.execute(select(Transaction)).scalars().all()
        subs = reconcile_subscriptions(session, list(all_txs))
        invalidate_derived_data(session)
        session.commit()
    return {"detected": len(subs)}


class SubscriptionCreate(BaseModel):
    description: str
    amount: float
    frequency: Literal["monthly", "annual"]

    @field_validator("description")
    @classmethod
    def nonempty_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("description is required")
        return value

    @field_validator("amount")
    @classmethod
    def positive_finite_amount(cls, value: float) -> float:
        if not isfinite(value) or value <= 0:
            raise ValueError("amount must be a positive finite number")
        return value

@router.post("/subscriptions")
def create_subscription(body: SubscriptionCreate):
    import uuid
    with get_session() as session:
        sub = Subscription(
            id=str(uuid.uuid4()),
            description=body.description,
            amount=body.amount,
            frequency=body.frequency,
            last_charged=None,
            active=True,
            origin="manual",
        )
        session.add(sub)
        session.flush()
        reconcile_subscriptions(session, session.execute(select(Transaction)).scalars().all())
        invalidate_derived_data(session)
        session.commit()
        return {"id": sub.id, "description": sub.description, "amount": sub.amount, "frequency": sub.frequency, "active": sub.active}

@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: str):
    with get_session() as session:
        sub = session.get(Subscription, sub_id)
        if not sub:
            raise HTTPException(status_code=404, detail="not found")
        if sub.dismissed:
            raise HTTPException(status_code=409, detail="This recurring charge has been dismissed.")
        if sub.origin == "detected":
            sub.dismissed = True
            sub.active = False
            from backend.analysis.recurring import reconcile_subscriptions
            all_txs = session.execute(select(Transaction)).scalars().all()
            reconcile_subscriptions(session, all_txs)
            invalidate_derived_data(session)
        else:
            session.delete(sub)
            invalidate_derived_data(session)
        session.commit()
        return {"deleted": sub_id}

@router.patch("/subscriptions/{sub_id}")
def update_subscription(sub_id: str, body: dict):
    with get_session() as session:
        sub = session.get(Subscription, sub_id)
        if not sub:
            raise HTTPException(status_code=404, detail="not found")
        if "active" in body:
            if not isinstance(body["active"], bool):
                raise HTTPException(status_code=422, detail="active must be boolean")
            from backend.analysis.recurring import set_manual_active
            set_manual_active(sub, body["active"])
            invalidate_derived_data(session)
        return {"id": sub_id, "active": sub.active}


@router.get("/merchants/aliases")
def list_merchant_aliases():
    with get_session() as session:
        aliases = session.execute(select(MerchantAlias).order_by(MerchantAlias.alias)).scalars().all()
        return [{"id": row.id, "alias": row.alias, "canonical": row.canonical, "enabled": row.enabled}
                for row in aliases]


@router.post("/merchants/aliases")
def create_merchant_alias(body: MerchantAliasCreate, background_tasks: BackgroundTasks):
    alias, canonical = body.alias.strip(), body.canonical.strip()
    if not alias or not canonical or alias.casefold() == canonical.casefold():
        raise HTTPException(status_code=422, detail="alias and distinct canonical name are required")
    with get_session() as session:
        row = session.execute(select(MerchantAlias).where(MerchantAlias.alias == alias)).scalar_one_or_none()
        if row:
            row.canonical, row.enabled = canonical, True
        else:
            row = MerchantAlias(alias=alias, canonical=canonical, enabled=True)
            session.add(row)
        invalidate_derived_data(session)
        session.flush()
        result = {"id": row.id, "alias": row.alias, "canonical": row.canonical, "enabled": row.enabled}
    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return result


@router.patch("/merchants/aliases/{alias_id}")
def set_merchant_alias(alias_id: int, body: MerchantAliasEnabled, background_tasks: BackgroundTasks):
    with get_session() as session:
        row = session.get(MerchantAlias, alias_id)
        if not row:
            raise HTTPException(status_code=404, detail="merchant alias not found")
        row.enabled = body.enabled
        invalidate_derived_data(session)
        result = {"id": row.id, "alias": row.alias, "canonical": row.canonical, "enabled": row.enabled}
    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return result
