from datetime import date
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, extract, and_, or_
from backend.db.database import get_session
from backend.db.models import Subscription, Transaction

_PAYMENT_KEYWORDS = (
    "automatic payment", "directpay", "direct pay", "online payment",
    "payment thank you", "payment received", "payment - thank",
    "thank you - your payment", "epay", "autopay",
)

router = APIRouter()

class CategoryUpdate(BaseModel):
    category: str

def _payment_filter():
    return or_(*[Transaction.description.ilike(f"%{kw}%") for kw in _PAYMENT_KEYWORDS])

@router.get("/transactions")
def list_transactions(
    category: Optional[str] = None,
    source: Optional[str] = None,
    month: Optional[str] = None,  # format: YYYY-MM
    merchant: Optional[str] = None,
    tx_type: Literal["spending", "refunds", "all"] = "spending",
    date_from: Optional[str] = None,  # YYYY-MM-DD
    date_to: Optional[str] = None,    # YYYY-MM-DD
    ids: Optional[str] = None,        # comma-separated transaction IDs
):
    from datetime import date as _date
    with get_session() as session:
        q = select(Transaction).order_by(Transaction.date.desc())
        if ids:
            id_list = [i.strip() for i in ids.split(",") if i.strip()]
            q = q.where(Transaction.id.in_(id_list))
        else:
            if tx_type == "spending":
                q = q.where(Transaction.amount > 0).where(~_payment_filter())
            elif tx_type == "refunds":
                q = q.where(Transaction.amount < 0).where(~_payment_filter())
            if category:
                q = q.where(Transaction.category == category)
            if source:
                q = q.where(Transaction.source == source)
            if merchant:
                q = q.where(Transaction.merchant_name == merchant)
            if date_from:
                q = q.where(Transaction.date >= _date.fromisoformat(date_from))
            if date_to:
                q = q.where(Transaction.date <= _date.fromisoformat(date_to))
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

@router.get("/transactions/export.csv")
def export_transactions_csv(
    category: Optional[str] = None,
    source: Optional[str] = None,
    month: Optional[str] = None,
    merchant: Optional[str] = None,
    tx_type: Literal["spending", "refunds", "all"] = "spending",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    import csv
    import io
    from fastapi.responses import StreamingResponse
    from datetime import date as _date

    with get_session() as session:
        q = select(Transaction).order_by(Transaction.date.desc())
        if tx_type == "spending":
            q = q.where(Transaction.amount > 0).where(~_payment_filter())
        elif tx_type == "refunds":
            q = q.where(Transaction.amount < 0).where(~_payment_filter())
        if category:
            q = q.where(Transaction.category == category)
        if source:
            q = q.where(Transaction.source == source)
        if merchant:
            q = q.where(Transaction.merchant_name == merchant)
        if date_from:
            q = q.where(Transaction.date >= _date.fromisoformat(date_from))
        if date_to:
            q = q.where(Transaction.date <= _date.fromisoformat(date_to))
        if month:
            year, mon = int(month[:4]), int(month[5:7])
            q = q.where(extract("year", Transaction.date) == year, extract("month", Transaction.date) == mon)
        txs = session.execute(q).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "description", "merchant_name", "category", "amount", "source", "city", "merchant_type"])
    for tx in txs:
        writer.writerow([tx.date.isoformat(), tx.description, tx.merchant_name or "", tx.category or "",
                         tx.amount, tx.source, tx.city or "", tx.merchant_type or ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.read()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=transactions.csv"})

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

@router.post("/subscriptions/redetect")
def redetect_subscriptions():
    from backend.analysis.subscription_detector import SubscriptionDetector
    detector = SubscriptionDetector()
    with get_session() as session:
        all_txs = session.execute(select(Transaction)).scalars().all()
        subs = detector.detect(list(all_txs))
        # Replace all subscriptions with freshly detected ones
        session.execute(select(Subscription).where(True))  # ensure table is loaded
        existing = session.execute(select(Subscription)).scalars().all()
        for s in existing:
            session.delete(s)
        session.flush()
        for sub in subs:
            session.add(sub)
        session.commit()
    return {"detected": len(subs)}


class SubscriptionCreate(BaseModel):
    description: str
    amount: float
    frequency: str  # "monthly" | "annual"

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
        )
        session.add(sub)
        session.commit()
        return {"id": sub.id, "description": sub.description, "amount": sub.amount, "frequency": sub.frequency, "active": sub.active}

@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: str):
    with get_session() as session:
        sub = session.get(Subscription, sub_id)
        if not sub:
            raise HTTPException(status_code=404, detail="not found")
        session.delete(sub)
        session.commit()
        return {"deleted": sub_id}

@router.patch("/subscriptions/{sub_id}")
def update_subscription(sub_id: str, body: dict):
    with get_session() as session:
        sub = session.get(Subscription, sub_id)
        if not sub:
            raise HTTPException(status_code=404, detail="not found")
        if "active" in body:
            sub.active = body["active"]
        return {"id": sub_id, "active": sub.active}
