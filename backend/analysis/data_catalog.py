"""On-demand, derived catalog describing available transaction data.

The catalog contains labels, counts, and coverage metadata only. It never exposes
transaction amounts, raw descriptions, import filenames, or checksums.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.database import get_data_revision
from backend.db.models import Account, ImportBatch, Sync, Transaction
from backend.analysis.merchant_normalizer import active_aliases

MAX_MERCHANTS = 200
MAX_CITIES = 100
MAX_COUNTRIES = 100
MAX_CATEGORIES = 100
MAX_ACCOUNTS = 100
MAX_IMPORTS = 50


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _iso(value):
    return value.isoformat() if value is not None else None


def _timestamp(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _country(metadata):
    if not metadata:
        return None
    try:
        parsed = json.loads(metadata)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return _text(parsed.get("Country") or parsed.get("country"))


def build_catalog(session: Session) -> dict:
    """Build a fresh, bounded summary from current database rows."""
    transactions = session.execute(select(Transaction)).scalars().all()
    accounts = session.execute(select(Account)).scalars().all()
    imports = session.execute(select(ImportBatch).order_by(ImportBatch.created_at.desc())).scalars().all()
    syncs = session.execute(select(Sync).order_by(Sync.synced_at.desc())).scalars().all()
    aliases = active_aliases(session)

    merchants = Counter()
    cities = Counter()
    countries = Counter()
    categories = Counter()
    years = defaultdict(Counter)
    sources = Counter()
    account_stats = defaultdict(lambda: {"count": 0, "first": None, "last": None})
    missing_city = missing_merchant = missing_category = missing_currency = 0
    enrichment_fallback = 0

    for tx in transactions:
        merchant = _text(tx.merchant_name)
        if merchant:
            merchants[merchant] += 1
        city = _text(tx.city)
        if city:
            cities[city] += 1
        else:
            missing_city += 1
        country = _country(tx.metadata_)
        if country:
            countries[country] += 1
        category = _text(tx.category)
        if category:
            categories[category] += 1
        else:
            missing_category += 1
        missing_merchant += not bool(merchant)
        missing_currency += not bool(_text(tx.currency))
        enrichment_fallback += tx.enrichment_status == "fallback"
        sources[_text(tx.source) or "Unknown"] += 1
        if tx.date:
            years[tx.date.year][tx.date.month] += 1
        if tx.account_id:
            stats = account_stats[tx.account_id]
            stats["count"] += 1
            stats["first"] = min(stats["first"], tx.date) if stats["first"] else tx.date
            stats["last"] = max(stats["last"], tx.date) if stats["last"] else tx.date

    known_account_ids = {account.id for account in accounts}
    unknown_account_count = sum(not tx.account_id or tx.account_id not in known_account_ids for tx in transactions)

    merchant_groups = defaultdict(list)
    for name in merchants:
        canonical = aliases.get(name, name)
        merchant_groups[canonical].append(name)
    merchant_entries = []
    for canonical, variants in merchant_groups.items():
        variants.sort(key=lambda n: (-merchants[n], n.casefold()))
        for name in variants:
            merchant_entries.append({"name": name, "canonical_name": canonical,
                                     "aliases": [v for v in variants if v != name], "count": merchants[name]})
    merchant_entries.sort(key=lambda item: (-item["count"], item["name"].casefold()))

    account_entries = []
    for account in accounts:
        stats = account_stats.get(account.id, {"count": 0, "first": None, "last": None})
        account_entries.append({"id": account.id, "name": account.name, "bank": account.bank,
                                "last4": account.last4, "transaction_count": stats["count"],
                                "first_date": _iso(stats["first"]), "last_date": _iso(stats["last"])})
    account_entries.sort(key=lambda item: (item["bank"].casefold(), item["name"].casefold(), item["id"]))

    date_values = [tx.date for tx in transactions if tx.date]
    import_entries = [{"account_id": batch.account_id, "from_date": _iso(batch.from_date),
                       "to_date": _iso(batch.to_date), "status": batch.status}
                      for batch in imports[:MAX_IMPORTS]]
    return {
        "revision": get_data_revision(session),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "transaction_count": len(transactions),
        "observed_date_range": {"from": _iso(min(date_values)) if date_values else None,
                                 "through": _iso(max(date_values)) if date_values else None},
        "merchants": merchant_entries[:MAX_MERCHANTS],
        "merchant_count": len(merchant_entries),
        "merchants_truncated": len(merchant_entries) > MAX_MERCHANTS,
        "cities": [{"name": name, "count": count} for name, count in cities.most_common(MAX_CITIES)],
        "city_count": len(cities), "cities_truncated": len(cities) > MAX_CITIES,
        "countries": [{"name": name, "count": count} for name, count in countries.most_common(MAX_COUNTRIES)],
        "categories": [{"name": name, "count": count} for name, count in categories.most_common(MAX_CATEGORIES)],
        "years": [{"year": year, "count": sum(months.values()),
                   "months": [{"month": month, "count": months[month]} for month in sorted(months)]}
                  for year, months in sorted(years.items())],
        "accounts": account_entries[:MAX_ACCOUNTS],
        "account_count": len(account_entries), "accounts_truncated": len(account_entries) > MAX_ACCOUNTS,
        "unknown_account_count": unknown_account_count,
        "data_quality": {
            "missing_city": missing_city, "missing_merchant": missing_merchant,
            "missing_category": missing_category, "missing_currency": missing_currency,
            "unassigned_account": unknown_account_count, "enrichment_fallback": enrichment_fallback,
            "by_source": [{"source": source, "count": count} for source, count in sorted(sources.items())],
        },
        "coverage": {
            "complete_statement_periods": False,
            "imports": import_entries,
            "imports_truncated": len(imports) > MAX_IMPORTS,
            "note": "Observed transaction dates and imported statement bounds do not prove complete account, statement-period, or geographic coverage.",
        },
        "freshness": {
            "latest_transaction_date": _iso(max(date_values)) if date_values else None,
            "latest_import_at": _timestamp(imports[0].created_at) if imports else None,
            "latest_sync_at": _timestamp(syncs[0].synced_at) if syncs else None,
        },
    }


# Alias retained for callers that prefer the longer descriptive name.
build_data_catalog = build_catalog
