from collections import defaultdict
from datetime import date, timedelta
import json
from typing import Optional
from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from backend.db.database import get_session, get_data_revision
from backend.auth import current_owner_id
from backend.db.models import Transaction
from backend.analysis.transaction_semantics import is_payment, purchase_amount, refund_amount, amount_components
from backend.analysis.merchant_normalizer import active_aliases

router = APIRouter()
MONTHLY_NARRATIVE_PROMPT_VERSION = 3
MONTHLY_CATEGORY_EXPLANATION_PROMPT_VERSION = 2

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
            "missing_category": sum(not (getattr(tx, "category", None) or "").strip() for tx in txs),
            "unassigned_account": sum(not tx.account_id for tx in txs),
            "enrichment_fallback": sum(getattr(tx, "enrichment_status", None) == "fallback" for tx in txs),
            "coverage_note": "Transaction dates show observed activity only. Imported statement-period coverage is not available, so date ranges do not establish complete account coverage.",
        }


class TransactionQuestionTurn(BaseModel):
    question: str = Field(max_length=1000)
    answer: str = Field(max_length=2000)
    criteria: dict = Field(default_factory=dict)
    match_count: int = Field(ge=0, default=0)
    gross_purchases: float = Field(ge=0, default=0)
    refunds: float = Field(ge=0, default=0)


class TransactionQuestion(BaseModel):
    question: str
    history: list[TransactionQuestionTurn] = Field(default_factory=list, max_length=8)

    @field_validator("question")
    @classmethod
    def nonempty_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question is required")
        return value[:1000]


def _question_transaction_rows(rows):
    return [{"id": tx.id, "date": tx.date.isoformat(), "description": tx.description,
             "merchant_name": tx.merchant_name, "city": tx.city, "category": tx.category,
             "amount": float(tx.amount), "kind": tx.kind, "source": tx.source}
            for tx in rows[:200]]


@router.post("/analysis/ask")
def ask_transactions(body: TransactionQuestion):
    import json
    from types import SimpleNamespace
    from backend.analysis.transaction_qa import (
        MAX_AGENT_STEPS, MAX_AGENT_TOOL_CALLS, agent_step_prompt, answer_prompt,
        carry_forward_criteria, comparison_overrides, comparison_window, criteria_prompt,
        execute_agent_tool, filter_transactions, normalize_criteria, parse_agent_action, parse_answer,
    )
    from backend.analysis.transaction_semantics import purchase_amount, refund_amount
    from backend.llm.factory import get_llm_provider

    if any(term in body.question.casefold() for term in (
        "forecast", "predict", "should i", "recommend", "what if", "why did", "why am i",
        "budget plan", "future spending",
    )):
        raise HTTPException(status_code=422, detail="I can search and summarize recorded transactions or compare explicit groups. Forecasts, recommendations, and causal explanations are not supported.")

    history = []
    allowed_criteria = {
        "merchant", "city", "category", "source", "date_from", "date_to",
        "amount_min", "amount_max", "transaction_type",
    }
    for turn in body.history[-5:]:
        history.append({
            "question": turn.question[:300],
            "answer": turn.answer[:500],
            "criteria": {key: str(value)[:120] if value is not None else None
                         for key, value in turn.criteria.items() if key in allowed_criteria},
            "match_count": turn.match_count,
            "gross_purchases": round(turn.gross_purchases, 2),
            "refunds": round(turn.refunds, 2),
        })

    with get_session() as session:
        from backend.analysis.data_catalog import build_catalog
        catalog = build_catalog(session)
        rows = session.execute(select(Transaction)).scalars().all()
        from backend.analysis.data_catalog import _country
        all_transactions = [SimpleNamespace(
            id=tx.id, date=tx.date, amount=tx.amount, amount_minor=tx.amount_minor,
            description=tx.description, merchant_name=tx.merchant_name, city=tx.city,
            category=tx.category, source=tx.source, kind=tx.kind,
            country=_country(getattr(tx, "metadata_", None)),
            currency=getattr(tx, "currency", None), account_id=getattr(tx, "account_id", None),
        ) for tx in rows]

    try:
        llm = get_llm_provider(use_pro=True)
        first_response = llm.complete_json(agent_step_prompt(body.question, history, catalog=catalog))
        first_action = parse_agent_action(first_response)
        parsed = json.loads(first_response) if first_action is None else None
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not interpret the transaction question. Check your AI provider settings and try again.") from exc

    if first_action is not None:
        datasets, trace = {}, []
        action = first_action
        tool_calls = 0
        primary_id = None
        comparison_result = None
        final_answer = None
        has_sql_evidence = False
        sql_comparison_result = None
        sql_monthly_result = None
        for step in range(MAX_AGENT_STEPS):
            if action["action"] == "final":
                q = body.question.casefold()
                sql_comparison_result = next((item["result"] for item in trace
                    if item["tool"] == "sql_query"
                    and item["result"].get("evidence_checks", {}).get("grouped")
                    and item["result"].get("evidence_checks", {}).get("has_text_group_label")
                    and item["result"].get("evidence_checks", {}).get("has_numeric_measure")
                    and item["result"].get("row_count", 0) >= 2), None)
                sql_monthly_result = next((item["result"] for item in trace
                    if item["tool"] == "sql_query"
                    and item["result"].get("evidence_checks", {}).get("month_grouped")
                    and item["result"].get("evidence_checks", {}).get("has_numeric_measure")), None)
                if any(term in q for term in ("compare", "versus", " vs ", "compared with")) and comparison_result is None and sql_comparison_result is None:
                    raise HTTPException(status_code=422, detail="The assistant did not produce two validated result sets for this comparison.")
                if any(term in q for term in ("monthly trend", "by month", "month over month")) and not any(
                    item["tool"] == "aggregate_results" and item["result"].get("group_by") == "month" for item in trace
                ) and sql_monthly_result is None:
                    raise HTTPException(status_code=422, detail="A monthly trend requires a validated monthly aggregation step.")
                final_answer = parse_answer(json.dumps({"answer": action.get("answer", "")}))
                if comparison_result:
                    primary_id = comparison_result["left_dataset_id"]
                elif primary_id is None and not any(item["tool"] == "coverage_summary" for item in trace) and not has_sql_evidence:
                    raise HTTPException(status_code=422, detail="A grounded answer requires an executed transaction search or coverage check.")
                else:
                    candidate_id = action.get("primary_dataset_id")
                    primary_id = candidate_id if isinstance(candidate_id, str) and candidate_id in datasets else primary_id
                break
            if tool_calls >= MAX_AGENT_TOOL_CALLS:
                raise HTTPException(status_code=422, detail="This question needs more analysis steps than the transaction assistant supports.")
            try:
                result = execute_agent_tool(action["action"], action.get("arguments", {}), all_transactions, datasets)
            except (ValueError, TypeError) as exc:
                raise HTTPException(status_code=422, detail=f"The requested analysis could not be completed: {exc}") from exc
            tool_calls += 1
            if action["action"] == "search_transactions":
                primary_id = result["dataset_id"]
            if action["action"] == "compare_results":
                comparison_result = result
                primary_id = result["left_dataset_id"]
            if action["action"] == "sql_query":
                has_sql_evidence = True
            trace.append({"tool": action["action"], "result": result})
            try:
                action = parse_agent_action(llm.complete_json(agent_step_prompt(body.question, history, trace, catalog)))
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=502, detail="The AI provider stopped before completing the transaction analysis.") from exc
            if action is None:
                raise HTTPException(status_code=502, detail="The AI provider returned an invalid transaction analysis step.")
        if final_answer is None:
            raise HTTPException(status_code=422, detail="The transaction analysis reached its step limit before a grounded answer was ready.")
        selected = datasets.get(primary_id) if primary_id else None
        matches = selected["rows"] if selected else []
        gross = float(sum((purchase_amount(tx) for tx in matches), start=0))
        refunds = float(sum((refund_amount(tx) for tx in matches), start=0))
        rendered_criteria = ({key: value.isoformat() if isinstance(value, date) else value
                              for key, value in selected["criteria"].items()} if selected else {})
        comparison = None
        if comparison_result:
            facts = comparison_result["right_facts"]
            comparison_matches = datasets[comparison_result["right_dataset_id"]]["rows"]
            comparison = {
                "criteria": comparison_result["right_criteria"],
                "match_count": facts["matching_transaction_count"],
                "gross_purchases": facts["gross_purchases"], "refunds": facts["refunds"],
                "net_spending": facts["net_spending"],
                "left": comparison_result["left_facts"],
                "net_spending_delta_right_minus_left": comparison_result["net_spending_delta_right_minus_left"],
                "transactions": _question_transaction_rows(comparison_matches),
                "displayed_count": min(len(comparison_matches), 200),
                "truncated": len(comparison_matches) > 200,
            }
        elif sql_comparison_result:
            comparison = {"source": "sql", "evidence": sql_comparison_result["evidence"],
                          "rows": sql_comparison_result["rows"],
                          "columns": sql_comparison_result["columns"]}
        dates = [tx.date for tx in all_transactions]
        return {
            "question": body.question, "answer": final_answer, "criteria": rendered_criteria,
            "analysis_mode": "sql" if has_sql_evidence and not selected else "transactions",
            "match_count": len(matches), "gross_purchases": round(gross, 2),
            "refunds": round(refunds, 2), "net_spending": round(gross - refunds, 2),
            "comparison": comparison, "tool_steps": [item["tool"] for item in trace],
            "tool_results": trace,
            "transactions": _question_transaction_rows(matches),
            "truncated": len(matches) > 200, "displayed_count": min(len(matches), 200),
            "coverage": {
                "observed_from": min(dates).isoformat() if dates else None,
                "observed_through": max(dates).isoformat() if dates else None,
                "complete_statement_periods": False,
                "note": "Observed transaction dates do not establish complete account or statement-period coverage.",
            },
        }

    # Legacy providers that return a plain criteria object continue to use the
    # compatible one-shot filter path below.

    criteria = carry_forward_criteria(
        body.question, normalize_criteria(parsed), history,
        clear_filters=parsed.get("clear_filters") if isinstance(parsed, dict) else None,
        reset=parsed.get("reset_filters") is True if isinstance(parsed, dict) else False,
    )
    compare_bounds = comparison_window(parsed)
    try:
        compare_overrides = comparison_overrides(parsed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if ((criteria["date_from"] and criteria["date_to"] and criteria["date_from"] > criteria["date_to"])
            or (criteria["amount_min"] is not None and criteria["amount_max"] is not None
                and criteria["amount_min"] > criteria["amount_max"])):
        raise HTTPException(status_code=422, detail="The requested date or amount range has its lower bound after its upper bound.")
    asks_compare = any(term in body.question.casefold() for term in ("compare", "versus", " vs ", "compared with"))
    if compare_bounds and (criteria["date_from"] is None or criteria["date_to"] is None):
        raise HTTPException(status_code=422, detail="A date comparison requires explicit start and end dates for both periods.")
    if any(key in compare_overrides for key in ("date_from", "date_to")) and not all(
        key in compare_overrides and compare_overrides[key] is not None for key in ("date_from", "date_to")
    ):
        raise HTTPException(status_code=422, detail="A comparison date range requires both start and end dates.")
    if asks_compare and not compare_bounds:
        group_keys = ("merchant", "city", "category", "source")
        differs = any(compare_overrides.get(key) is not None and criteria.get(key) is not None
                      and compare_overrides[key] != criteria.get(key) for key in group_keys)
        date_differs = (compare_overrides.get("date_from") is not None
                        and criteria.get("date_from") is not None
                        and compare_overrides["date_from"] != criteria["date_from"])
        if not (differs or date_differs):
            raise HTTPException(status_code=422, detail="To compare groups, specify both sides of a merchant, city, category, source, or date comparison.")
    if not any(criteria[key] is not None for key in (
        "merchant", "city", "category", "source", "date_from", "date_to", "amount_min", "amount_max",
    )) and compare_bounds is None and not compare_overrides:
        raise HTTPException(status_code=422, detail="I can search transactions and compare explicit date ranges. I cannot verify statement-period completeness from transaction dates alone.")

    matches = filter_transactions(all_transactions, criteria)
    gross = float(sum((purchase_amount(tx) for tx in matches), start=0))
    refunds = float(sum((refund_amount(tx) for tx in matches), start=0))
    comparison = None
    if compare_bounds or compare_overrides:
        comparison_criteria = dict(criteria)
        comparison_criteria.update({key: value for key, value in compare_overrides.items() if value is not None})
        if compare_bounds:
            comparison_criteria["date_from"], comparison_criteria["date_to"] = compare_bounds
        if ((comparison_criteria["date_from"] and comparison_criteria["date_to"]
             and comparison_criteria["date_from"] > comparison_criteria["date_to"])
                or (comparison_criteria["amount_min"] is not None and comparison_criteria["amount_max"] is not None
                    and comparison_criteria["amount_min"] > comparison_criteria["amount_max"])):
            raise HTTPException(status_code=422, detail="The comparison group's bounds are reversed.")
        comparison_matches = filter_transactions(all_transactions, comparison_criteria)
        comparison_gross = float(sum((purchase_amount(tx) for tx in comparison_matches), start=0))
        comparison_refunds = float(sum((refund_amount(tx) for tx in comparison_matches), start=0))
        comparison = {
            "criteria": {key: value.isoformat() if isinstance(value, date) else value
                         for key, value in comparison_criteria.items()},
            "match_count": len(comparison_matches),
            "gross_purchases": round(comparison_gross, 2),
            "refunds": round(comparison_refunds, 2),
            "net_spending": round(comparison_gross - comparison_refunds, 2),
        }
    rendered_criteria = {key: value.isoformat() if isinstance(value, date) else value for key, value in criteria.items()}
    prompt = answer_prompt(body.question, rendered_criteria, matches, len(matches), gross, refunds, history, comparison)
    try:
        answer = parse_answer(llm.complete_json(prompt))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="The AI provider could not summarize the matching transactions. Please try again.") from exc
    if answer is None:
        answer = (f"I found {len(matches)} matching transaction{'s' if len(matches) != 1 else ''}. "
                  f"Gross purchases total ${gross:.2f}; refunds total ${refunds:.2f}.")

    if comparison is not None:
        comparison.update({"transactions": _question_transaction_rows(comparison_matches),
                           "displayed_count": min(len(comparison_matches), 200),
                           "truncated": len(comparison_matches) > 200})

    return {
        "question": body.question,
        "answer": answer,
        "criteria": rendered_criteria,
        "match_count": len(matches),
        "gross_purchases": round(gross, 2),
        "refunds": round(refunds, 2),
        "net_spending": round(gross - refunds, 2),
        "comparison": comparison,
        "transactions": _question_transaction_rows(matches),
        "truncated": len(matches) > 200,
        "displayed_count": min(len(matches), 200),
        "coverage": {
            "observed_from": min((tx.date for tx in all_transactions), default=None).isoformat()
            if all_transactions else None,
            "observed_through": max((tx.date for tx in all_transactions), default=None).isoformat()
            if all_transactions else None,
            "complete_statement_periods": False,
            "note": "Observed transaction dates do not establish complete account or statement-period coverage.",
        },
    }


@router.get("/analysis/category-summary")
def get_category_summary(days: int = 90, date_from: Optional[date] = None, date_to: Optional[date] = None):
    if bool(date_from) != bool(date_to):
        raise HTTPException(status_code=422, detail="date_from and date_to must be provided together")
    if date_from and date_to:
        if date_from > date_to:
            raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
        since, through = date_from, date_to
        months = max(1, (through - since).days + 1) / 30
    else:
        days = max(7, min(days, 730))
        since, through = date.today() - timedelta(days=days), date.today()
        months = days / 30
    with get_session() as session:
        txs = session.execute(
            select(Transaction).where(Transaction.date >= since, Transaction.date <= through)
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
def get_insights(merchant_days: int = 90, date_from: Optional[date] = None, date_to: Optional[date] = None):
    from backend.analysis.insights import (
        get_spending_anomalies, get_duplicate_charges, get_price_increases,
        get_merchant_breakdown, get_day_of_week, get_year_over_year,
    )
    if bool(date_from) != bool(date_to):
        raise HTTPException(status_code=422, detail="date_from and date_to must be provided together")
    if date_from and date_to:
        if date_from > date_to:
            raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
        since, through = date_from, date_to
    else:
        merchant_days = max(7, min(merchant_days, 730))
        since, through = date.today() - timedelta(days=merchant_days), date.today()

    with get_session() as session:
        all_txs = session.execute(select(Transaction)).scalars().all()
        aliases = active_aliases(session)
        spending_txs = [tx for tx in all_txs if purchase_amount(tx) > 0]
        merchant_txs = [tx for tx in spending_txs if since <= tx.date <= through]
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
    date_from: Optional[date] = None
    date_to: Optional[date] = None

@router.post("/analysis/savings-tips")
def get_savings_tips(body: SavingsTipsRequest = SavingsTipsRequest()):
    from backend.llm.factory import get_llm_provider
    from backend.analysis.savings_advisor import SavingsAdvisor
    if bool(body.date_from) != bool(body.date_to):
        raise HTTPException(status_code=422, detail="date_from and date_to must be provided together")
    if body.date_from and body.date_to:
        if body.date_from > body.date_to:
            raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
        days = (body.date_to - body.date_from).days + 1
        summary = get_category_summary(date_from=body.date_from, date_to=body.date_to)
        period = f"{body.date_from.isoformat()}–{body.date_to.isoformat()}"
    else:
        days = max(7, min(body.days, 730))
        summary = get_category_summary(days=days)
        period_start = (date.today() - timedelta(days=days)).strftime("%b %Y")
        period_end = date.today().strftime("%b %Y")
        period = f"{period_start}–{period_end}"

    with get_session() as session:
        from backend.db.models import Subscription
        from backend.analysis.recurring import is_effectively_active, subscription_amount_profile
        subs = session.execute(select(Subscription).where(Subscription.dismissed.is_(False))).scalars().all()
        active_subs = [sub for sub in subs if is_effectively_active(sub)]
        linked_ids = set()
        ids_by_subscription = {}
        for sub in active_subs:
            try:
                ids = json.loads(sub.supporting_transaction_ids or "[]")
                ids = ids if isinstance(ids, list) else []
            except (TypeError, ValueError):
                ids = []
            ids_by_subscription[sub.id] = [tx_id for tx_id in ids if isinstance(tx_id, str)]
            linked_ids.update(ids_by_subscription[sub.id])
        tx_by_id = {}
        if linked_ids:
            linked_txs = session.execute(select(Transaction).where(Transaction.id.in_(linked_ids))).scalars().all()
            tx_by_id = {tx.id: tx for tx in linked_txs}
        subscriptions = []
        for sub in active_subs:
            evidence = [tx_by_id[tx_id] for tx_id in ids_by_subscription[sub.id] if tx_id in tx_by_id]
            profile = subscription_amount_profile(sub, evidence)
            subscriptions.append({
                "name": sub.description,
                "monthly_amount": profile["average_monthly_amount"],
                "frequency": sub.frequency,
            })

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
            select(Subscription).where(Subscription.dismissed.is_(False))
        ).scalars().all()

        cached = session.execute(
            select(MonthlyReportCache).where(
                MonthlyReportCache.year == year,
                MonthlyReportCache.month == month,
            )
        ).scalar_one_or_none()

        report = get_monthly_report_data(spending_txs, year=year, month=month, merchant_aliases=aliases)
        report.update(amount_components([tx for tx in all_txs if tx.date.year == year and tx.date.month == month]))
        report["subscriptions_due"] = get_subscriptions_due(subs, report_month_end=month_end, transactions=all_txs)
        revision = get_data_revision(session)
        report["data_revision"] = revision
        report["narrative"] = cached.narrative if (
            cached
            and getattr(cached, "data_revision", None) == revision
            and getattr(cached, "prompt_version", 1) == MONTHLY_NARRATIVE_PROMPT_VERSION
        ) else None

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
        if (cached and getattr(cached, "data_revision", None) == revision
                and getattr(cached, "prompt_version", 1) == MONTHLY_NARRATIVE_PROMPT_VERSION):
            return {"narrative": cached.narrative, "data_revision": revision}

        all_txs = session.execute(select(Transaction)).scalars().all()
        aliases = active_aliases(session)
        spending_txs = [tx for tx in all_txs if not _is_payment(tx)]
        subs = session.execute(
            select(Subscription).where(Subscription.dismissed.is_(False))
        ).scalars().all()

        report_txs = [tx for tx in all_txs if tx.date.year == year and tx.date.month == month]
        report = get_monthly_report_data(spending_txs, year=year, month=month, merchant_aliases=aliases)
        report.update(amount_components(report_txs))
        due = get_subscriptions_due(subs, report_month_end=month_end, transactions=all_txs)

        month_name = calendar.month_name[month]
        top3 = report["categories"][:3]
        def category_summary_line(category: dict) -> str:
            average = category["all_data_monthly_average"]
            average_text = f"${average:.0f}" if average is not None else "unavailable"
            return (f"- {category['name']}: ${category['current']:.0f} "
                    f"(prior month: ${category['prior']:.0f}; historical monthly average excluding the selected month: {average_text})")

        cat_lines = "\n".join(category_summary_line(category) for category in top3)
        pct_change = ""
        if report["prev_total"] > 0:
            delta = (report["total"] - report["prev_total"]) / report["prev_total"] * 100
            pct_change = f", {abs(delta):.1f}% {'more' if delta > 0 else 'less'} than last month"
        due_text = f"{len(due)} subscription(s) renew before the end of next month." if due else "No subscriptions renewing soon."
        average_summary = (
            f"Across {report['average_month_count']} available calendar months in the imported data excluding {month_name} ({report['average_period_start']} to {report['average_period_end']}), "
            f"the all-history reference average for monthly gross purchases was ${report['all_data_monthly_average']:.0f}; for older report months, this reference can include later dates. "
            if report["all_data_monthly_average"] is not None
            else "There is not enough spending history to calculate an all-data monthly average. "
        )
        prompt = (
            f"Write a 2-4 sentence plain English summary of gross purchases and refunds in {month_name} {year}. "
            f"Gross purchases were ${report['gross_purchases']:.0f}, refunds were ${report['refunds']:.0f}, "
            f"and net spending was ${report['net_spending']:.0f}{pct_change}. "
            f"{average_summary}"
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
        prompt_version=MONTHLY_NARRATIVE_PROMPT_VERSION,
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


def _validate_category_explanation_request(year: int, month: int, comparison: str):
    if not (1 <= month <= 12):
        raise HTTPException(status_code=422, detail="month must be 1–12")
    if not (1 <= year <= 9999):
        raise HTTPException(status_code=422, detail="year must be between 1 and 9999")
    if comparison not in {"recent3", "prior"}:
        raise HTTPException(status_code=422, detail="comparison must be 'recent3' or 'prior'")


@router.get("/analysis/monthly-report/category-explanations")
def get_monthly_category_explanations(year: int, month: int, comparison: str = "recent3"):
    _validate_category_explanation_request(year, month, comparison)
    import json
    from backend.db.models import MonthlyCategoryExplanationCache

    with get_session() as session:
        revision = get_data_revision(session)
        cached = session.get(MonthlyCategoryExplanationCache, (current_owner_id(), year, month, comparison))
        if (cached and cached.data_revision == revision
                and cached.prompt_version == MONTHLY_CATEGORY_EXPLANATION_PROMPT_VERSION):
            return {**json.loads(cached.payload), "cached": True, "data_revision": revision}
    return {"explanations": None, "cached": False, "data_revision": revision}


@router.post("/analysis/monthly-report/category-explanations")
def generate_monthly_category_explanations(year: int, month: int, comparison: str = "recent3"):
    _validate_category_explanation_request(year, month, comparison)
    import json
    from datetime import datetime, timezone
    from backend.db.models import MonthlyCategoryExplanationCache
    from backend.analysis.monthly_report import get_monthly_report_data
    from backend.analysis.monthly_category_explanations import (
        build_category_evidence, build_explanation_prompt, parse_explanations,
    )

    with get_session() as session:
        revision = get_data_revision(session)
        cached = session.get(MonthlyCategoryExplanationCache, (current_owner_id(), year, month, comparison))
        if (cached and cached.data_revision == revision
                and cached.prompt_version == MONTHLY_CATEGORY_EXPLANATION_PROMPT_VERSION):
            return {**json.loads(cached.payload), "cached": True, "data_revision": revision}

        all_txs = session.execute(select(Transaction)).scalars().all()
        aliases = active_aliases(session)
        spending_txs = [tx for tx in all_txs if not _is_payment(tx)]
        report = get_monthly_report_data(
            spending_txs, year=year, month=month, merchant_aliases=aliases,
        )
        evidence = build_category_evidence(spending_txs, year, month, comparison, aliases)
        if comparison == "recent3" and not report["recent_three_months_all_observed"]:
            evidence = []
        evidence_by_category = {item["category"]: item for item in evidence}
        chart_categories = [
            category for category in report["categories"]
            if (comparison == "prior" or category["recent_three_month_average"] is not None)
            and abs(category["current"] - (category["prior"] if comparison == "prior" else category["recent_three_month_average"])) >= 0.01
        ]
        for category in chart_categories:
            evidence_by_category.setdefault(category["name"], {
                "category": category["name"],
                "current_gross_purchases": category["current"],
                "current_transaction_count": 0,
                "baseline_type": "prior month" if comparison == "prior" else "three immediately preceding calendar months",
                "baseline_month_count": 1 if comparison == "prior" else 3,
                "baseline_observed_month_count": 1 if comparison == "prior" else 3,
                "baseline_months_all_observed": True,
                "baseline_months": [
                    {**item, "category_gross_purchases": 0.0, "category_transaction_count": 0}
                    for item in report["recent_three_months"]
                ] if comparison == "recent3" else [],
                "baseline_gross_purchases": category["prior"] if comparison == "prior" else category["recent_three_month_average"],
                "baseline_category_median": category["prior"] if comparison == "prior" else category["recent_three_month_average"],
                "baseline_category_range": [category["prior"], category["prior"]] if comparison == "prior" else None,
                "change": round(category["current"] - (category["prior"] if comparison == "prior" else category["recent_three_month_average"]), 2),
                "merchant_changes": [],
                "largest_current_transactions": [],
                "largest_baseline_transactions": [],
            })
        chart_category_names = {category["name"] for category in chart_categories}
        evidence = [
            item for item in evidence_by_category.values()
            if item["category"] in chart_category_names and item["change"] is not None and abs(item["change"]) >= 0.01
        ]
        prompt = build_explanation_prompt(year, month, comparison, evidence) if evidence else None

    if evidence:
        from backend.llm.factory import get_llm_provider
        try:
            llm = get_llm_provider(use_pro=True)
            explanations = parse_explanations(llm.complete_json(prompt), evidence)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Could not generate category explanations. Check your AI provider settings and try again.") from exc
    else:
        explanations = {}

    payload = {"explanations": explanations, "evidence": evidence}
    entry = MonthlyCategoryExplanationCache(
        year=year,
        month=month,
        comparison=comparison,
        payload=json.dumps(payload, ensure_ascii=False),
        created_at=datetime.now(timezone.utc),
        data_revision=revision,
        prompt_version=MONTHLY_CATEGORY_EXPLANATION_PROMPT_VERSION,
    )
    with get_session() as session:
        if get_data_revision(session) != revision:
            raise HTTPException(status_code=409, detail="Transaction data changed while explanations were being generated. Retry to generate current explanations.")
        session.merge(entry)

    return {**payload, "cached": False, "data_revision": revision}


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
