from __future__ import annotations

import json
import logging
from typing import Optional
from pydantic import BaseModel, ValidationError, field_validator
from backend.db.models import Transaction
from backend.llm.base import LLMProvider

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {
    "dining", "groceries", "transport", "shopping",
    "entertainment", "subscriptions", "health", "travel",
    "utilities", "other",
}

ENRICH_PROMPT = """You are a transaction enrichment engine. For each bank transaction below, return a JSON array of enriched objects.

Valid categories:
- dining: restaurants, cafes, bars, fast food, food delivery
- groceries: supermarkets, grocery stores, food markets
- transport: gas stations, rideshare, parking, public transit, tolls, auto services
- shopping: retail stores, online shopping, clothing, electronics, home goods
- entertainment: movies, streaming services, concerts, games, sports
- subscriptions: recurring software/app charges, membership fees
- health: pharmacies, doctors, gyms, medical, dental, fitness
- travel: flights, hotels, vacation rentals, travel agencies
- utilities: internet, phone, electricity, water, cable, insurance
- other: anything else

Fields per transaction:
- id: transaction id (copy exactly as given)
- category: one of the valid categories above
- merchant_name: the canonical merchant or brand name only when it is directly supported by the cleaned transaction description; strip store numbers, location codes, reference codes, and payment-terminal prefixes (SQ*, TST*, SAMPAY, etc.). Do not infer from external knowledge. If cleanup leaves only location text or another non-merchant descriptor, return null instead of guessing.
- city: city name if present in the description, otherwise null
- is_online: true if the merchant is purely online, false otherwise
- merchant_type: short phrase describing what the merchant does (e.g. "grocery store", "streaming service", "gas station")

Return ONLY a valid JSON array. No markdown, no explanation.

Transactions:
{transactions}"""


class TransactionEnrichment(BaseModel):
    id: str
    category: str
    merchant_name: str
    city: Optional[str] = None
    is_online: bool
    merchant_type: str

    @field_validator("category")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            return "other"
        return v


def _fallback_enrichment(tx: Transaction) -> TransactionEnrichment:
    return TransactionEnrichment(
        id=tx.id,
        category="other",
        merchant_name=tx.description,
        city=None,
        is_online=False,
        merchant_type="unknown",
    )


BATCH_SIZE = 50


class Categorizer:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def _enrich_batch(self, transactions: list[Transaction]) -> dict[str, TransactionEnrichment]:
        tx_lines = "\n".join(
            f"{tx.id}: {tx.description} ${abs(tx.amount):.2f}"
            for tx in transactions
        )
        prompt = ENRICH_PROMPT.format(transactions=tx_lines)

        try:
            response = self._llm.complete_json(prompt)
            data = json.loads(response)
            enrichments = [TransactionEnrichment(**item) for item in data]
            result = {e.id: e for e in enrichments}
        except (json.JSONDecodeError, KeyError, ValidationError) as exc:
            logger.warning("LLM response parsing failed (%s: %s); falling back to defaults", type(exc).__name__, exc)
            return {tx.id: _fallback_enrichment(tx) for tx in transactions}

        for tx in transactions:
            if tx.id not in result:
                logger.warning("LLM response missing enrichment for id=%s; using fallback", tx.id)
                result[tx.id] = _fallback_enrichment(tx)

        return result

    def categorize(self, transactions: list[Transaction]) -> dict[str, TransactionEnrichment]:
        if not transactions:
            return {}

        result: dict[str, TransactionEnrichment] = {}
        for i in range(0, len(transactions), BATCH_SIZE):
            batch = transactions[i:i + BATCH_SIZE]
            result.update(self._enrich_batch(batch))
            logger.info("Enriched %d/%d transactions", min(i + BATCH_SIZE, len(transactions)), len(transactions))

        return result
