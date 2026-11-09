import hashlib
import json
import re
from statistics import median
from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
from typing import List, Optional
from backend.db.models import Subscription, Transaction
from backend.analysis.transaction_semantics import is_payment, purchase_amount

AMOUNT_TOLERANCE_PCT = 0.15   # 15% within a stable period
MONTHLY_DAYS_MIN, MONTHLY_DAYS_MAX = 20, 40
ANNUAL_DAYS_MIN, ANNUAL_DAYS_MAX = 340, 390
_BILLING_TYPE_MARKERS = (
    "subscription", "streaming", "software", "cloud storage", "cloud computing",
    "saas", "api service", "internet provider", "cable", "insurance",
    "utility", "electric provider", "water provider", "gas provider",
    "membership", "charity", "tax software",
)
_BILLING_DESCRIPTION_MARKERS = (
    "NETFLIX", "SPOTIFY", "HULU", "AMAZON PRIME", "APPLE.COM/BILL",
    "COMCAST", "XFINITY", "GEICO", "GOOGLE ONE", "GOOGLE COLAB",
    "ANTHROPIC", "CLAUDE.AI", "CURSOR", "XAI LLC", "AIRALO",
    "FREETAXUSA", "FREE TAX USA", "SUBSCRIPTION", "MEMBERSHIP FEE",
)
_IN_PERSON_TYPE_MARKERS = (
    "restaurant", "cafe", "coffee shop", "bar", "fast food", "food truck",
    "grocery", "supermarket", "warehouse club", "retail store", "convenience store",
    "bakery", "ice cream shop", "gas station",
)
_IN_PERSON_CATEGORIES = {"dining", "restaurants", "groceries", "grocery"}

_NOISE = re.compile(r'\s+[A-Z0-9]{8,}$|\s+\d{6,}$|\s+DC\d+[A-Z0-9]*$|\s+[A-Z]{2}\d+[A-Z0-9]+$')
_PHONE = re.compile(r'\b(?:1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}\b')

def _normalize(description: str) -> str:
    s = description.upper().strip()
    if re.match(r"^GOOGLE\s+\*?\s*CLOUD(?:\s|$)", s):
        return "GOOGLE CLOUD"
    if re.match(r"^GOOGLE\s+\*?\s*COLAB(?:\s|$)", s):
        return "GOOGLE COLAB"
    s = re.sub(r'\*[A-Z0-9]{8,}$', '', s).strip()
    s = s.replace("G.CO/HELPPAY#", " ")
    s = _NOISE.sub("", s).strip()
    s = _PHONE.sub(" ", s)
    s = re.sub(r'\s+[A-Z]{2}$', '', s).strip()
    return re.sub(r'\s+', ' ', s).strip()


_IDENTITY_STOPWORDS = {
    "THE", "INC", "LLC", "CORP", "CO", "COM", "WWW", "ONLINE", "PAYMENT",
    "BILL", "SUBSCRIPTION", "SERVICE", "PROVIDER", "USA", "CA", "CALIFORNIA",
}


def _identity_tokens(transactions: List[Transaction]) -> set[str]:
    values = []
    for tx in transactions:
        values.extend((tx.merchant_name or "", _normalize(tx.description or "")))
    return {
        token for value in values for token in re.findall(r"[A-Z]{3,}", value.upper())
        if token not in _IDENTITY_STOPWORDS
    }


def _groups_can_merge(left: List[Transaction], right: List[Transaction]) -> bool:
    """Merge descriptors only when merchant text and billing dates support it."""
    left_tokens, right_tokens = _identity_tokens(left), _identity_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    if len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens)) < 0.5:
        return False

    left_types = [set(re.findall(r"[a-z]+", (tx.merchant_type or "").casefold()))
                  for tx in left if tx.merchant_type]
    right_types = [set(re.findall(r"[a-z]+", (tx.merchant_type or "").casefold()))
                   for tx in right if tx.merchant_type]
    if left_types and right_types and not any(
        a == b or len(a & b) >= 2 for a in left_types for b in right_types
    ):
        return False

    left_by_date = {tx.date: round(float(purchase_amount(tx)), 2) for tx in left}
    right_by_date = {tx.date: round(float(purchase_amount(tx)), 2) for tx in right}
    overlap = set(left_by_date) & set(right_by_date)
    if overlap:
        # A repeated matching charge marks descriptor duplication. Different
        # simultaneous amounts can be separate products from the same company.
        return sum(left_by_date[day] == right_by_date[day] for day in overlap) >= 2

    left_start, left_end = min(left_by_date), max(left_by_date)
    right_start, right_end = min(right_by_date), max(right_by_date)
    if right_start < left_start:
        left_start, left_end, right_start, right_end = right_start, right_end, left_start, left_end
    if right_start <= left_end:
        return False
    observed_gaps = [
        (later - earlier).days
        for rows in (left, right)
        for dates in [sorted(tx.date for tx in rows)]
        for earlier, later in zip(dates, dates[1:])
    ]
    typical_gap = sorted(observed_gaps)[len(observed_gaps) // 2] if observed_gaps else 30
    return (right_start - left_end).days <= max(65, int(typical_gap * 1.75))


def _merge_descriptor_groups(groups: dict) -> dict:
    """Build transaction series from noisy descriptors within each account."""
    partitions: dict[tuple, list[tuple[tuple, list[Transaction]]]] = defaultdict(list)
    for key, txs in groups.items():
        partitions[key[:2]].append((key, txs))
    result = {}
    for partition_key, partition in partitions.items():
        parent = list(range(len(partition)))

        def find(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        for left_index, right_index in combinations(range(len(partition)), 2):
            if _groups_can_merge(partition[left_index][1], partition[right_index][1]):
                left_root, right_root = find(left_index), find(right_index)
                if left_root != right_root:
                    parent[right_root] = left_root

        clusters: dict[int, list] = defaultdict(list)
        for index, item in enumerate(partition):
            clusters[find(index)].append(item)
        for cluster in clusters.values():
            series_key = min(item[0][2] for item in cluster)
            txs = [tx for _, rows in cluster for tx in rows]
            if len(cluster) > 1:
                # The same bill may be imported under two different bank
                # strings; retain one evidence row per date and charge amount.
                unique = {}
                for tx in sorted(txs, key=lambda row: (row.date, row.id)):
                    unique.setdefault((tx.date, round(float(purchase_amount(tx)), 2)), tx)
                txs = list(unique.values())
            result[(*partition_key, series_key)] = txs
    return result


class SubscriptionDetector:
    def detect(self, transactions: List[Transaction]) -> List[Subscription]:
        expenses = [tx for tx in transactions if purchase_amount(tx) > 0 and not is_payment(tx)]

        groups: dict = defaultdict(list)
        for tx in expenses:
            # Enrichment can rename a merchant or omit its name on later rows.
            # A cleaned bank description remains stable across those changes.
            series_key = _normalize(tx.description) or _normalize(tx.merchant_name or "")
            account_id = getattr(tx, "account_id", None)
            # Imported rows without account assignment still need source
            # isolation; otherwise identical descriptors from different banks
            # can combine into a plausible but false cadence.
            source_key = (getattr(tx, "source", "") or "").strip().casefold() if account_id is None else ""
            key = (account_id, source_key, series_key)
            groups[key].append(tx)

        groups = _merge_descriptor_groups(groups)

        subscriptions: List[Subscription] = []
        seen_ids: set = set()

        for (account_id, source_key, series_key), txs in groups.items():
            txs_sorted = sorted(txs, key=lambda t: (t.date, t.id))
            merchant_names = Counter(
                tx.merchant_name.strip() for tx in txs_sorted if tx.merchant_name and tx.merchant_name.strip()
            )
            description = merchant_names.most_common(1)[0][0] if merchant_names else series_key
            if self._has_in_person_signal(description, txs_sorted):
                continue
            if not self._has_billing_signal(description, txs_sorted):
                continue
            frequency = self._detect_frequency(txs_sorted)
            if frequency is not None:
                last_charged = txs_sorted[-1].date
                base_amount = float(purchase_amount(txs_sorted[-1]))
                sub_id = self._series_id(account_id, source_key, series_key)
                days_since = (date.today() - last_charged).days
                active = days_since <= 40 if frequency == "monthly" else days_since <= 400
                subscriptions.append(Subscription(
                    id=sub_id,
                    description=description,
                    amount=base_amount,
                    frequency=frequency,
                    last_charged=last_charged,
                    active=active,
                    origin="detected",
                    supporting_transaction_ids=json.dumps([tx.id for tx in txs_sorted]),
                ))
                seen_ids.add(sub_id)
                continue

            # Usage-based detection: ≥5 charges, avg gap < 20 days, spans ≥2 calendar months
            usage_id = self._series_id(account_id, source_key, series_key, usage=True)
            usage = self._detect_usage_based(description, txs_sorted, usage_id)
            if usage:
                if usage_id not in seen_ids:
                    subscriptions.append(usage)
                    seen_ids.add(usage_id)

        return subscriptions

    @staticmethod
    def _series_id(account_id, source_key: str, series_key: str, usage: bool = False) -> str:
        # A bank descriptor is more stable than enrichment output and keeps
        # distinct products from the same generic merchant label separate.
        identity = json.dumps([
            account_id or "", source_key or "", series_key,
            "usage" if usage else "standard",
        ], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def _has_in_person_signal(description: str, txs: List[Transaction]) -> bool:
        if "COSTCO" in (description or "").upper() or any("COSTCO" in (tx.description or "").upper() for tx in txs):
            return True
        in_person_observations = 0
        for tx in txs:
            merchant_type = (tx.merchant_type or "").strip().casefold()
            category = (tx.category or "").strip().casefold().replace("_", " ")
            if (any(marker in merchant_type for marker in _IN_PERSON_TYPE_MARKERS)
                    or category in _IN_PERSON_CATEGORIES):
                in_person_observations += 1
        # One noisy enrichment/category result should not veto otherwise
        # consistent bill evidence. Exclude the series when in-person evidence
        # represents a majority of its observations.
        return bool(txs) and in_person_observations > len(txs) / 2

    @staticmethod
    def _has_billing_signal(description: str, txs: List[Transaction]) -> bool:
        merchant_types = [
            (tx.merchant_type or "").strip().casefold()
            for tx in txs
        ]
        if any(marker in merchant_type for marker in _BILLING_TYPE_MARKERS
               for merchant_type in merchant_types):
            return True

        descriptor = " ".join(
            [description] + [tx.description or "" for tx in txs]
        ).upper()
        return any(marker in descriptor for marker in _BILLING_DESCRIPTION_MARKERS)

    _USAGE_BASED_TYPES = {
        "software subscription", "saas", "cloud service", "cloud computing",
        "api service", "software", "streaming service", "digital service",
    }

    def _detect_usage_based(self, description: str, txs_sorted: List[Transaction], sub_id: str) -> Optional[Subscription]:
        if len(txs_sorted) < 5:
            return None

        # Only apply to software/cloud merchants — not grocery stores, cafes, etc.
        merchant_types = {tx.merchant_type.lower() for tx in txs_sorted if tx.merchant_type}
        if not any(t in self._USAGE_BASED_TYPES for t in merchant_types):
            return None

        gaps = [(txs_sorted[i+1].date - txs_sorted[i].date).days for i in range(len(txs_sorted)-1)]
        avg_gap = sum(gaps) / len(gaps)
        if avg_gap >= MONTHLY_DAYS_MIN:
            return None  # not usage-based — gaps too long

        months_seen = {tx.date.strftime("%Y-%m") for tx in txs_sorted}
        if len(months_seen) < 2:
            return None  # all in one month — could be a one-off

        # Estimate monthly cost from most recent complete month
        from collections import defaultdict as _dd
        by_month: dict = _dd(float)
        for tx in txs_sorted:
            by_month[tx.date.strftime("%Y-%m")] += float(purchase_amount(tx))
        today = date.today()
        current_month_key = today.strftime("%Y-%m")
        complete_months = {m: v for m, v in by_month.items() if m != current_month_key}
        if not complete_months:
            return None
        avg_monthly = sum(complete_months.values()) / len(complete_months)

        last_charged = txs_sorted[-1].date
        days_since = (today - last_charged).days
        return Subscription(
            id=sub_id,
            description=f"{description} (usage-based)",
            amount=round(avg_monthly, 2),
            frequency="monthly",
            last_charged=last_charged,
            active=days_since <= 40,
            origin="detected",
            supporting_transaction_ids=json.dumps([tx.id for tx in txs_sorted]),
        )

    def _detect_frequency(self, txs: List[Transaction]) -> Optional[str]:
        if len(txs) < 2:
            return None

        txs_sorted = sorted(txs, key=lambda t: t.date)

        # Multiple usage charges can land in one month. Detect the billing
        # cadence from distinct charge months, then let the amount profile
        # classify the series as fixed or variable.
        month_rows: dict[int, list] = defaultdict(list)
        for tx in txs_sorted:
            month_rows[tx.date.year * 12 + tx.date.month].append(tx)
        months = sorted(month_rows)
        consecutive_month_run = 1
        has_monthly_run = False
        for previous, current in zip(months, months[1:]):
            consecutive_month_run = consecutive_month_run + 1 if current - previous == 1 else 1
            if consecutive_month_run >= 3:
                has_monthly_run = True
                break
        if has_monthly_run:
            # Validate the representative cadence as well: three consecutive
            # month labels alone can hide very short and very long gaps.
            representatives = [median([tx.date.toordinal() for tx in month_rows[month]]) for month in months]
            representative_gaps = [right - left for left, right in zip(representatives, representatives[1:])]
            if self._regular_monthly_gaps(representative_gaps[-5:]):
                return "monthly"

        # Check gap regularity
        gaps = [(txs_sorted[i+1].date - txs_sorted[i].date).days for i in range(len(txs_sorted)-1)]
        avg_gap = sum(gaps) / len(gaps)

        if MONTHLY_DAYS_MIN <= avg_gap <= MONTHLY_DAYS_MAX:
            frequency = "monthly"
            # A single interval cannot establish a recurring monthly pattern.
            # Require at least two observed periods before calling it a bill.
            if len(gaps) < 2:
                return None
        elif ANNUAL_DAYS_MIN <= avg_gap <= ANNUAL_DAYS_MAX:
            frequency = "annual"
        else:
            return None

        # An average can hide unrelated purchases (for example, gaps of 10 and
        # 50 days average to a plausible 30-day billing cycle). Check that the
        # recent intervals cluster around their median instead. Annual history
        # may be sparse, so this is meaningful only with multiple intervals.
        if frequency == "monthly" and not self._regular_monthly_gaps(gaps[-5:]):
            return None
        if frequency == "annual":
            recent_gaps = gaps[-5:]
            if len(recent_gaps) > 1:
                typical_gap = median(recent_gaps)
                allowed_deviation = max(5, typical_gap * 0.15)
                if any(abs(gap - typical_gap) > allowed_deviation for gap in recent_gaps):
                    return None

        return frequency

    @staticmethod
    def _regular_monthly_gaps(gaps) -> bool:
        if len(gaps) < 2:
            return False
        typical_gap = median(gaps)
        if not MONTHLY_DAYS_MIN <= typical_gap <= MONTHLY_DAYS_MAX:
            return False
        allowed_deviation = max(5, typical_gap * 0.15)
        return all(abs(gap - typical_gap) <= allowed_deviation for gap in gaps)
