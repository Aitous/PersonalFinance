"""Shared transaction selection for the table, search, and CSV export."""
from datetime import date
from typing import Literal, Optional

from fastapi import HTTPException, Query
from sqlalchemy import extract, func, or_, select

from backend.db.models import MerchantAlias, Transaction
from backend.analysis.transaction_semantics import PAYMENT_KEYWORDS


def transaction_query(
    category: Optional[str] = None,
    source: Optional[str] = None,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    merchant: Optional[str] = None,
    tx_type: Literal['spending', 'refunds', 'all'] = 'spending',
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    ids: Optional[str] = None,
    description: Optional[str] = None,
    merchant_contains: Optional[str] = None,
    city: Optional[str] = None,
    merchant_type: Optional[str] = None,
    min_amount: Optional[float] = Query(None, ge=0, allow_inf_nan=False),
    max_amount: Optional[float] = Query(None, ge=0, allow_inf_nan=False),
    is_online: Optional[bool] = None,
    is_subscription: Optional[bool] = None,
):
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise HTTPException(422, 'Minimum amount must not exceed maximum amount')
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, 'From date must not be after to date')
    q = select(Transaction).order_by(Transaction.date.desc(), Transaction.id)
    if ids:
        q = q.where(Transaction.id.in_([i.strip() for i in ids.split(',') if i.strip()]))
    if tx_type != 'all':
        payment_desc = or_(*[Transaction.description.ilike(f'%{kw}%') for kw in PAYMENT_KEYWORDS])
        non_spend_kind = Transaction.kind.in_(["payment", "transfer"])
        q = q.where(~payment_desc, or_(Transaction.kind.is_(None), ~non_spend_kind))
        if tx_type == 'spending':
            q = q.where(or_(Transaction.kind == "purchase", (Transaction.kind.is_(None) & (Transaction.amount > 0))))
        else:
            q = q.where(or_(Transaction.kind == "refund", (Transaction.kind.is_(None) & (Transaction.amount < 0))))
    for column, value in [(Transaction.category, category), (Transaction.source, source),
                          (Transaction.is_online, is_online),
                          (Transaction.is_subscription, is_subscription)]:
        if value is not None:
            q = q.where(column == value)
    if merchant is not None:
        # An accepted canonical name matches both its own rows and explicitly
        # mapped source names, while the stored merchant remains untouched.
        alias_names = select(MerchantAlias.alias).where(
            MerchantAlias.enabled.is_(True), MerchantAlias.canonical == merchant
        )
        q = q.where(Transaction.merchant_name.in_(alias_names) | (Transaction.merchant_name == merchant))
    for column, value in [(Transaction.description, description), (Transaction.city, city),
                          (Transaction.merchant_type, merchant_type)]:
        if value and value.strip():
            q = q.where(column.icontains(value.strip(), autoescape=True))
    if merchant_contains and merchant_contains.strip():
        needle = merchant_contains.strip()
        canonical_match = select(MerchantAlias.alias).where(
            MerchantAlias.enabled.is_(True), MerchantAlias.canonical.icontains(needle, autoescape=True)
        )
        q = q.where(Transaction.merchant_name.icontains(needle, autoescape=True)
                    | Transaction.merchant_name.in_(canonical_match))
    if date_from:
        q = q.where(Transaction.date >= date_from)
    if date_to:
        q = q.where(Transaction.date <= date_to)
    if month:
        year, mon = map(int, month.split('-'))
        q = q.where(extract('year', Transaction.date) == year, extract('month', Transaction.date) == mon)
    if min_amount is not None:
        q = q.where(func.abs(Transaction.amount) >= min_amount)
    if max_amount is not None:
        q = q.where(func.abs(Transaction.amount) <= max_amount)
    return q
