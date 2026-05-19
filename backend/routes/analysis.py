from collections import defaultdict
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from backend.db.database import get_session
from backend.db.models import Transaction
from backend.llm.factory import get_llm_provider
from backend.analysis.savings_advisor import SavingsAdvisor

router = APIRouter()

# Patterns that identify credit card payments / refunds — not real spending
_PAYMENT_KEYWORDS = (
    "automatic payment", "directpay", "direct pay", "online payment",
    "payment thank you", "payment received", "payment - thank",
    "thank you - your payment", "epay", "autopay",
)

def _is_payment(tx: Transaction) -> bool:
    desc = (tx.description or "").lower()
    return any(kw in desc for kw in _PAYMENT_KEYWORDS)

def _spending_amount(tx: Transaction) -> float:
    """All amounts are now normalized to positive for spending. Skip negative (credits/refunds)."""
    return tx.amount

@router.get("/analysis/overview")
def get_overview():
    with get_session() as session:
        txs = session.execute(select(Transaction)).scalars().all()

        by_month: dict = defaultdict(lambda: defaultdict(float))
        for tx in txs:
            if _is_payment(tx) or tx.amount <= 0:
                continue
            month_key = tx.date.strftime("%Y-%m")
            amount = _spending_amount(tx)
            by_month[month_key]["total"] += amount
            by_month[month_key][tx.category or "other"] += amount

        return {"monthly": {k: dict(v) for k, v in by_month.items()}}

@router.get("/analysis/category-summary")
def get_category_summary(days: int = 90):
    days = max(7, min(days, 730))
    since = date.today() - timedelta(days=days)
    months = days / 30
    with get_session() as session:
        txs = session.execute(
            select(Transaction).where(Transaction.date >= since)
        ).scalars().all()

        totals: dict = defaultdict(float)
        counts: dict = defaultdict(int)
        for tx in txs:
            if _is_payment(tx) or tx.amount <= 0:
                continue
            cat = tx.category or "other"
            totals[cat] += _spending_amount(tx)
            counts[cat] += 1

        return {
            cat: {"total": round(totals[cat], 2), "avg_monthly": round(totals[cat] / months, 2), "count": counts[cat]}
            for cat in totals
        }

@router.get("/analysis/insights")
def get_insights(merchant_days: int = 90):
    from backend.analysis.insights import (
        get_spending_anomalies, get_duplicate_charges, get_price_increases,
        get_merchant_breakdown, get_day_of_week, get_year_over_year,
    )
    merchant_days = max(7, min(merchant_days, 730))
    since = date.today() - timedelta(days=merchant_days)

    with get_session() as session:
        all_txs = session.execute(select(Transaction)).scalars().all()
        spending_txs = [tx for tx in all_txs if not _is_payment(tx) and tx.amount > 0]
        merchant_txs = [tx for tx in spending_txs if tx.date >= since]
        session.expunge_all()

    return {
        "alerts": {
            "anomalies": get_spending_anomalies(spending_txs),
            "duplicates": get_duplicate_charges(spending_txs),
            "price_increases": get_price_increases(spending_txs),
        },
        "merchants": get_merchant_breakdown(merchant_txs),
        "day_of_week": get_day_of_week(spending_txs),
        "year_over_year": get_year_over_year(spending_txs),
    }


class SavingsTipsRequest(BaseModel):
    provider: Optional[str] = None

@router.post("/analysis/savings-tips")
def get_savings_tips(body: SavingsTipsRequest = SavingsTipsRequest()):
    summary = get_category_summary()
    period_start = (date.today() - timedelta(days=90)).strftime("%b %Y")
    period_end = date.today().strftime("%b %Y")
    period = f"{period_start}–{period_end}"

    with get_session() as session:
        from backend.db.models import Subscription
        subs = session.execute(select(Subscription).where(Subscription.active == True)).scalars().all()
        subscriptions = [{"name": s.description, "amount": s.amount, "frequency": s.frequency} for s in subs]

    llm = get_llm_provider(provider_override=body.provider, use_pro=True)
    advisor = SavingsAdvisor(llm=llm)
    tips = advisor.get_tips(summary, period=period, subscriptions=subscriptions)
    return {"tips": tips, "period": period}
