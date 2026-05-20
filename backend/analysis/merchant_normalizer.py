"""
Post-enrichment fuzzy deduplication for merchant names.

Groups merchant names that are likely the same merchant (high string similarity
or one is a prefix/suffix of the other), then unifies all variants to the most
frequently occurring name in the database.
"""
from difflib import SequenceMatcher
from collections import defaultdict
from sqlalchemy import select
from backend.db.database import get_session
from backend.db.models import Transaction

SIMILARITY_THRESHOLD = 0.88  # SequenceMatcher ratio to consider names the same merchant


def _clean(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum() or c.isspace()).strip()


def _are_same_merchant(a: str, b: str) -> bool:
    ca, cb = _clean(a), _clean(b)

    # Exact match after stripping punctuation/case
    if ca == cb:
        return True

    # Pure fuzzy similarity — no substring logic to avoid city-prefix false positives
    return SequenceMatcher(None, ca, cb).ratio() >= SIMILARITY_THRESHOLD


def build_canonical_map(merchant_counts: dict[str, int]) -> dict[str, str]:
    """
    Given {merchant_name: tx_count}, return {variant -> canonical_name}.
    Canonical name = the most frequent name in each cluster.
    """
    names = list(merchant_counts.keys())
    # Union-Find to group similar names
    parent = {n: n for n in names}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        px, py = find(x), find(y)
        if px != py:
            # Merge smaller cluster into larger (by tx count)
            if merchant_counts.get(px, 0) >= merchant_counts.get(py, 0):
                parent[py] = px
            else:
                parent[px] = py

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if _are_same_merchant(a, b):
                union(a, b)

    # For each cluster, pick the most frequent name as canonical
    clusters: dict[str, list[str]] = defaultdict(list)
    for name in names:
        clusters[find(name)].append(name)

    canonical_map: dict[str, str] = {}
    for members in clusters.values():
        canonical = max(members, key=lambda n: merchant_counts.get(n, 0))
        for m in members:
            if m != canonical:
                canonical_map[m] = canonical

    return canonical_map


def normalize_merchants() -> dict:
    """
    Scan all transactions, find merchant name variants, unify them in-place.
    Returns {"merged": int, "groups": list} for reporting.
    """
    with get_session() as session:
        txs = session.execute(
            select(Transaction).where(Transaction.merchant_name.isnot(None))
        ).scalars().all()

        # Count occurrences per merchant name
        counts: dict[str, int] = defaultdict(int)
        for tx in txs:
            counts[tx.merchant_name] += 1

        canonical_map = build_canonical_map(dict(counts))
        if not canonical_map:
            return {"merged": 0, "groups": []}

        merged = 0
        groups = []
        for variant, canonical in canonical_map.items():
            affected = [tx for tx in txs if tx.merchant_name == variant]
            for tx in affected:
                tx.merchant_name = canonical
            merged += len(affected)
            groups.append({"from": variant, "to": canonical, "count": len(affected)})

        session.commit()

    return {"merged": merged, "groups": groups}
