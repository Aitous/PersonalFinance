"""Suggest and apply reversible merchant aliases without rewriting source values."""
from __future__ import annotations
from collections import defaultdict
from difflib import SequenceMatcher

from sqlalchemy import select

from backend.db.database import get_session
from backend.db.models import MerchantAlias, Transaction

SIMILARITY_THRESHOLD = 0.88


def _clean(value: str) -> str:
    return "".join(c.lower() for c in value if c.isalnum() or c.isspace()).strip()


def _are_same_merchant(a: str, b: str) -> bool:
    ca, cb = _clean(a), _clean(b)
    return ca == cb or SequenceMatcher(None, ca, cb).ratio() >= SIMILARITY_THRESHOLD


def build_canonical_map(merchant_counts: dict[str, int]) -> dict[str, str]:
    names = list(merchant_counts)
    parent = {name: name for name in names}

    def find(name):
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if _are_same_merchant(a, b):
                ra, rb = find(a), find(b)
                if ra != rb:
                    if merchant_counts.get(ra, 0) >= merchant_counts.get(rb, 0):
                        parent[rb] = ra
                    else:
                        parent[ra] = rb
    clusters = defaultdict(list)
    for name in names:
        clusters[find(name)].append(name)
    result = {}
    for members in clusters.values():
        canonical = max(members, key=lambda name: merchant_counts.get(name, 0))
        result.update({name: canonical for name in members if name != canonical})
    return result


def active_aliases(session=None) -> dict[str, str]:
    if session is not None:
        aliases = {row.alias: row.canonical for row in session.execute(
            select(MerchantAlias).where(MerchantAlias.enabled.is_(True))
        ).scalars().all()}
        return {alias: canonical_merchant(alias, aliases) for alias in aliases}
    with get_session() as owned:
        return active_aliases(owned)


def canonical_merchant(name: str | None, aliases: dict[str, str]) -> str | None:
    """Resolve a display alias without changing the extracted transaction value."""
    seen = set()
    while name in aliases and name not in seen:
        seen.add(name)
        name = aliases[name]
    return name


def normalize_merchants() -> dict:
    """Return fuzzy proposals and count explicit aliases currently applied."""
    with get_session() as session:
        txs = session.execute(select(Transaction).where(Transaction.merchant_name.is_not(None))).scalars().all()
        counts = defaultdict(int)
        for tx in txs:
            counts[tx.merchant_name] += 1
        proposals = build_canonical_map(dict(counts))
        accepted = active_aliases(session)
        groups = [{"from": alias, "to": canonical, "count": counts[alias],
                   "accepted": accepted.get(alias) == canonical}
                  for alias, canonical in proposals.items()]
        merged = sum(count for alias, count in counts.items()
                     if canonical_merchant(alias, accepted) != alias)
        return {"merged": merged, "groups": groups}
