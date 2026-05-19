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

ENRICH_PROMPT = """You are a transaction enrichment engine. For each transaction below, extract the following fields and return them as a JSON array.

Valid categories (pick the best fit):
- dining: restaurants, cafes, bars, fast food, food delivery
- groceries: supermarkets, grocery stores, food markets (Trader Joe's, Whole Foods, Costco food)
- transport: gas stations, Uber, Lyft, Zipcar, parking, public transit, tolls, auto services
- shopping: retail stores, Amazon, clothing, electronics, home goods, sporting goods
- entertainment: movies, streaming services (Netflix, Spotify, Hulu), concerts, games, sports
- subscriptions: recurring software/app charges (Google One, Strava, iCloud, Adobe), membership fees
- health: pharmacies, doctors, gyms, medical, dental, fitness, supplements
- travel: flights, hotels, Airbnb, vacation rentals, travel agencies (only if clearly travel-related)
- utilities: internet, phone, electricity, water, cable, insurance (GEICO, State Farm, Progressive, Allstate, etc.)
- other: anything that doesn't clearly fit above

Fields to extract per transaction:
- id: the transaction id (as given)
- category: one of the valid categories above
- merchant_name: canonical brand name (e.g. "Costco", "Trader Joe's", "Netflix") — not the raw description
- city: the city name if it appears in the description, otherwise null (null for online merchants)
- is_online: true if the merchant is an online-only service, false otherwise
- merchant_type: short phrase describing what the merchant does (e.g. "warehouse store", "streaming service", "gas station", "restaurant")

Return ONLY a JSON array of objects with these 6 fields. No markdown, no explanation, no extra text.

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


class Categorizer:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def categorize(self, transactions: list[Transaction]) -> dict[str, TransactionEnrichment]:
        if not transactions:
            return {}

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

        # Fill in fallbacks for any input transactions missing from the LLM response
        for tx in transactions:
            if tx.id not in result:
                logger.warning("LLM response missing enrichment for transaction id=%s; using fallback", tx.id)
                result[tx.id] = _fallback_enrichment(tx)

        return result
