from collections import defaultdict
from datetime import date, timedelta
from fastapi import APIRouter
from sqlalchemy import select
from backend.db.database import get_session
from backend.db.models import Transaction
from backend.llm.factory import get_llm_provider
from backend.analysis.savings_advisor import SavingsAdvisor

router = APIRouter()

@router.get("/analysis/overview")
def get_overview():
    with get_session() as session:
        txs = session.execute(
            select(Transaction).where(Transaction.amount < 0)
        ).scalars().all()

        by_month: dict = defaultdict(lambda: defaultdict(float))
        for tx in txs:
            month_key = tx.date.strftime("%Y-%m")
            by_month[month_key]["total"] += abs(tx.amount)
            by_month[month_key][tx.category or "other"] += abs(tx.amount)

        return {"monthly": {k: dict(v) for k, v in by_month.items()}}

@router.get("/analysis/category-summary")
def get_category_summary():
    three_months_ago = date.today() - timedelta(days=90)
    with get_session() as session:
        txs = session.execute(
            select(Transaction).where(
                Transaction.amount < 0,
                Transaction.date >= three_months_ago,
            )
        ).scalars().all()

        totals: dict = defaultdict(float)
        counts: dict = defaultdict(int)
        for tx in txs:
            cat = tx.category or "other"
            totals[cat] += abs(tx.amount)
            counts[cat] += 1

        return {
            cat: {"total": round(totals[cat], 2), "avg_monthly": round(totals[cat] / 3, 2), "count": counts[cat]}
            for cat in totals
        }

@router.post("/analysis/savings-tips")
def get_savings_tips():
    summary = get_category_summary()
    period_start = (date.today() - timedelta(days=90)).strftime("%b %Y")
    period_end = date.today().strftime("%b %Y")
    period = f"{period_start}–{period_end}"

    llm = get_llm_provider()
    advisor = SavingsAdvisor(llm=llm)
    tips = advisor.get_tips(summary, period=period)
    return {"tips": tips, "period": period}
