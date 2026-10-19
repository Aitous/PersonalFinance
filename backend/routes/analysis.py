from collections import defaultdict
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from backend.db.database import get_session, get_data_revision
from backend.db.models import Transaction
from backend.analysis.transaction_semantics import is_payment, purchase_amount, refund_amount, amount_components
from backend.analysis.merchant_normalizer import active_aliases

router = APIRouter()

# Backwards-compatible wrappers for existing route code.
def _is_payment(tx: Transaction) -> bool:
    return is_payment(tx)

def _spending_amount(tx: Transaction) -> float:
    return tx.amount

@router.get("/analysis/overview")
def get_overview():
    with get_session() as session:
        txs = session.execute(select(Transaction)).scalars().all()

        by_month: dict = defaultdict(lambda: defaultdict(float))
        totals: dict = defaultdict(lambda: defaultdict(float))
        for tx in txs:
            month_key = tx.date.strftime("%Y-%m")
            gross = float(purchase_amount(tx))
            refund = float(refund_amount(tx))
            if gross:
                by_month[month_key]["total"] += gross
                by_month[month_key][tx.category or "other"] += gross
            totals[month_key]["gross_purchases"] += gross
            totals[month_key]["refunds"] += refund
            totals[month_key]["net_spending"] += gross - refund

        return {"monthly": {k: dict(v) for k, v in by_month.items()},
                "monthly_totals": {k: {name: round(value, 2) for name, value in v.items()}
                                   for k, v in totals.items()}}

@router.get("/analysis/data-quality")
def get_data_quality():
    with get_session() as session:
        txs = session.execute(select(Transaction)).scalars().all()
        sources = defaultdict(list)
        for tx in txs:
            sources[tx.source].append(tx)
        return {
            "sources": [
                {"source": source, "transaction_count": len(rows),
                 "first_date": min(tx.date for tx in rows).isoformat(),
                 "last_date": max(tx.date for tx in rows).isoformat()}
                for source, rows in sorted(sources.items())
            ],
            "total_transactions": len(txs),
            "missing_city": sum(not (tx.city or "").strip() for tx in txs),
            "missing_merchant": sum(not (tx.merchant_name or "").strip() for tx in txs),
            "unassigned_account": sum(not tx.account_id for tx in txs),
            "coverage_note": "Transaction dates show observed activity only. Imported statement-period coverage is not available, so date ranges do not establish complete account coverage.",
        }


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
        refunds: dict = defaultdict(float)
        for tx in txs:
            if _is_payment(tx):
                continue
            cat = tx.category or "other"
            purchase = float(purchase_amount(tx))
            refund = float(refund_amount(tx))
            if purchase:
                totals[cat] += purchase
                counts[cat] += 1
            refunds[cat] += refund

        return {
            cat: {"total": round(totals[cat], 2), "gross_purchases": round(totals[cat], 2),
                  "refunds": round(refunds[cat], 2), "net_spending": round(totals[cat] - refunds[cat], 2),
                  "avg_monthly": round(totals[cat] / months, 2), "average_basis": "rolling_days_divided_by_30",
                  "count": counts[cat]}
            for cat in (set(totals) | set(refunds))
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
        aliases = active_aliases(session)
        spending_txs = [tx for tx in all_txs if purchase_amount(tx) > 0]
        merchant_txs = [tx for tx in spending_txs if tx.date >= since]
        session.expunge_all()

    return {
        "alerts": {
            "anomalies": get_spending_anomalies(spending_txs),
            "duplicates": get_duplicate_charges(spending_txs),
            "price_increases": get_price_increases(spending_txs),
        },
        "merchants": get_merchant_breakdown(merchant_txs, merchant_aliases=aliases),
        "day_of_week": get_day_of_week(spending_txs),
        "year_over_year": get_year_over_year(spending_txs),
    }


class SavingsTipsRequest(BaseModel):
    provider: Optional[str] = None
    days: int = 90

@router.post("/analysis/savings-tips")
def get_savings_tips(body: SavingsTipsRequest = SavingsTipsRequest()):
    from backend.llm.factory import get_llm_provider
    from backend.analysis.savings_advisor import SavingsAdvisor
    days = max(7, min(body.days, 730))
    summary = get_category_summary(days=days)
    period_start = (date.today() - timedelta(days=days)).strftime("%b %Y")
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


@router.get("/analysis/monthly-report")
def get_monthly_report(year: int, month: int):
    if not (1 <= month <= 12):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="month must be 1–12")
    if not (1 <= year <= 9999):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="year must be between 1 and 9999")

    import calendar
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    with get_session() as session:
        from backend.db.models import MonthlyReportCache, Subscription
        from backend.analysis.monthly_report import get_monthly_report_data, get_subscriptions_due

        all_txs = session.execute(select(Transaction)).scalars().all()
        aliases = active_aliases(session)
        spending_txs = [tx for tx in all_txs if not _is_payment(tx)]

        subs = session.execute(
            select(Subscription).where(Subscription.active == True)
        ).scalars().all()

        cached = session.execute(
            select(MonthlyReportCache).where(
                MonthlyReportCache.year == year,
                MonthlyReportCache.month == month,
            )
        ).scalar_one_or_none()

        report = get_monthly_report_data(spending_txs, year=year, month=month, merchant_aliases=aliases)
        report.update(amount_components([tx for tx in all_txs if tx.date.year == year and tx.date.month == month]))
        report["subscriptions_due"] = get_subscriptions_due(subs, report_month_end=month_end)
        revision = get_data_revision(session)
        report["data_revision"] = revision
        report["narrative"] = cached.narrative if cached and getattr(cached, "data_revision", None) == revision else None

    return report


@router.post("/analysis/monthly-report/narrative")
def generate_monthly_narrative(year: int, month: int):
    if not (1 <= month <= 12):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="month must be 1–12")
    if not (1 <= year <= 9999):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="year must be between 1 and 9999")
    import calendar
    month_end = date(year, month, calendar.monthrange(year, month)[1])

    with get_session() as session:
        from backend.db.models import MonthlyReportCache, Subscription
        from backend.analysis.monthly_report import get_monthly_report_data, get_subscriptions_due

        revision = get_data_revision(session)
        cached = session.execute(
            select(MonthlyReportCache).where(
                MonthlyReportCache.year == year,
                MonthlyReportCache.month == month,
            )
        ).scalar_one_or_none()
        if cached and getattr(cached, "data_revision", None) == revision:
            return {"narrative": cached.narrative, "data_revision": revision}

        all_txs = session.execute(select(Transaction)).scalars().all()
        aliases = active_aliases(session)
        spending_txs = [tx for tx in all_txs if not _is_payment(tx)]
        subs = session.execute(
            select(Subscription).where(Subscription.active == True)
        ).scalars().all()

        report_txs = [tx for tx in all_txs if tx.date.year == year and tx.date.month == month]
        report = get_monthly_report_data(spending_txs, year=year, month=month, merchant_aliases=aliases)
        report.update(amount_components(report_txs))
        due = get_subscriptions_due(subs, report_month_end=month_end)

        month_name = calendar.month_name[month]
        top3 = report["categories"][:3]
        cat_lines = "\n".join(
            f"- {c['name']}: ${c['current']:.0f} (prior month: ${c['prior']:.0f})"
            for c in top3
        )
        pct_change = ""
        if report["prev_total"] > 0:
            delta = (report["total"] - report["prev_total"]) / report["prev_total"] * 100
            pct_change = f", {abs(delta):.1f}% {'more' if delta > 0 else 'less'} than last month"
        due_text = f"{len(due)} subscription(s) renew before the end of next month." if due else "No subscriptions renewing soon."
        prompt = (
            f"Write a 2-4 sentence plain English summary of gross purchases and refunds in {month_name} {year}. "
            f"Gross purchases were ${report['gross_purchases']:.0f}, refunds were ${report['refunds']:.0f}, "
            f"and net spending was ${report['net_spending']:.0f}{pct_change}. "
            f"Top categories:\n{cat_lines}\n{due_text} "
            f"Be specific about amounts. No preamble, no sign-off."
        )

    from backend.llm.factory import get_llm_provider
    from datetime import datetime, timezone
    llm = get_llm_provider(use_pro=True)
    narrative = llm.complete(prompt).strip()

    entry = MonthlyReportCache(
        year=year,
        month=month,
        narrative=narrative,
        created_at=datetime.now(timezone.utc),
        data_revision=revision,
    )
    with get_session() as session:
        if get_data_revision(session) != revision:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail="Transaction data changed while the narrative was being generated. Retry to generate a current summary.",
            )
        session.merge(entry)

    return {"narrative": narrative, "data_revision": revision}


@router.get("/analysis/monthly-averages")
def get_monthly_averages_endpoint(
    months: int = 3,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    from backend.analysis.insights import get_monthly_averages
    from fastapi import HTTPException

    today = date.today()

    if date_from and date_to:
        try:
            from_date = date.fromisoformat(date_from)
            to_date = date.fromisoformat(date_to)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")
        if from_date > to_date:
            raise HTTPException(status_code=422, detail="date_from must be before date_to.")
    else:
        months = max(1, min(months, 60))
        year = today.year
        month = today.month - months
        while month <= 0:
            month += 12
            year -= 1
        from_date = date(year, month, 1)
        to_date = today

    with get_session() as session:
        all_txs = session.execute(select(Transaction)).scalars().all()
        spending_txs = [tx for tx in all_txs if not _is_payment(tx)]
        session.expunge_all()

    return get_monthly_averages(spending_txs, date_from=from_date, date_to=to_date)
