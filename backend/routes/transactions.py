from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from math import isfinite
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from backend.db.database import get_session, invalidate_derived_data
from backend.db.models import MerchantAlias, Subscription, Transaction
from backend.transaction_filters import transaction_query
from backend.analysis.merchant_normalizer import active_aliases, canonical_merchant

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

@router.patch("/transactions/{tx_id}/category")
def update_category(tx_id: str, body: CategoryUpdate, background_tasks: BackgroundTasks):
    with get_session() as session:
        tx = session.get(Transaction, tx_id)
        if not tx:
            raise HTTPException(status_code=404, detail="not found")
        tx.category = body.category
        tx.manual_category = True
        invalidate_derived_data(session)
        result = {"id": tx_id, "category": tx.category}
    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return result

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
        invalidate_derived_data(session)
        result = {"id": tx_id, **{field: getattr(tx, field) for field in fields}}
    from backend.routes.search import _embed_all
    background_tasks.add_task(_embed_all, get_session)
    return result

@router.get("/subscriptions")
def list_subscriptions():
    with get_session() as session:
        subs = session.execute(select(Subscription)).scalars().all()
        return [
            {
                "id": sub.id,
                "description": sub.description,
                "amount": sub.amount,
                "frequency": sub.frequency,
                "last_charged": sub.last_charged.isoformat() if sub.last_charged else None,
                "active": sub.active,
                "origin": sub.origin,
                "dismissed": sub.dismissed,
            }
            for sub in subs
        ]

@router.post("/subscriptions/redetect")
def redetect_subscriptions():
    from backend.analysis.recurring import reconcile_subscriptions
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
    from datetime import date as _date
    with get_session() as session:
        sub = Subscription(
            id=str(uuid.uuid4()),
            description=body.description,
            amount=body.amount,
            frequency=body.frequency,
            last_charged=_date.today(),
            active=True,
            origin="manual",
        )
        session.add(sub)
        invalidate_derived_data(session)
        session.commit()
        return {"id": sub.id, "description": sub.description, "amount": sub.amount, "frequency": sub.frequency, "active": sub.active}

@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: str):
    with get_session() as session:
        sub = session.get(Subscription, sub_id)
        if not sub:
            raise HTTPException(status_code=404, detail="not found")
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
