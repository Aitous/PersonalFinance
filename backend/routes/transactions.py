from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, extract
from backend.db.database import get_session
from backend.db.models import Subscription, Transaction

router = APIRouter()

class CategoryUpdate(BaseModel):
    category: str

@router.get("/transactions")
def list_transactions(
    category: Optional[str] = None,
    source: Optional[str] = None,
    month: Optional[str] = None,  # format: YYYY-MM
    merchant: Optional[str] = None,
):
    with get_session() as session:
        q = select(Transaction).order_by(Transaction.date.desc())
        if category:
            q = q.where(Transaction.category == category)
        if source:
            q = q.where(Transaction.source == source)
        if merchant:
            q = q.where(Transaction.merchant_name == merchant)
        if month:
            year, mon = int(month[:4]), int(month[5:7])
            q = q.where(
                extract("year", Transaction.date) == year,
                extract("month", Transaction.date) == mon,
            )
        txs = session.execute(q).scalars().all()
        return [
            {
                "id": tx.id,
                "source": tx.source,
                "date": tx.date.isoformat(),
                "description": tx.description,
                "amount": tx.amount,
                "category": tx.category,
                "is_subscription": tx.is_subscription,
                "merchant_name": tx.merchant_name,
                "city": tx.city,
                "is_online": tx.is_online,
                "merchant_type": tx.merchant_type,
            }
            for tx in txs
        ]

@router.patch("/transactions/{tx_id}/category")
def update_category(tx_id: str, body: CategoryUpdate):
    with get_session() as session:
        tx = session.get(Transaction, tx_id)
        if not tx:
            raise HTTPException(status_code=404, detail="not found")
        tx.category = body.category
        return {"id": tx_id, "category": tx.category}

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
            }
            for sub in subs
        ]

@router.patch("/subscriptions/{sub_id}")
def update_subscription(sub_id: str, body: dict):
    with get_session() as session:
        sub = session.get(Subscription, sub_id)
        if not sub:
            raise HTTPException(status_code=404, detail="not found")
        if "active" in body:
            sub.active = body["active"]
        return {"id": sub_id, "active": sub.active}
