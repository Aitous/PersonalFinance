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

ENRICH_PROMPT = """You are a transaction enrichment engine. For each transaction, return a JSON array of enriched objects.

Valid categories:
- dining: restaurants, cafes, bars, fast food, food delivery
- groceries: supermarkets, grocery stores, food markets (Trader Joe's, Whole Foods, Costco food)
- transport: gas stations, Uber, Lyft, Zipcar, parking, public transit, tolls, auto services
- shopping: retail stores, Amazon, clothing, electronics, home goods, sporting goods
- entertainment: movies, streaming services (Netflix, Spotify, Hulu), concerts, games, sports
- subscriptions: recurring software/app charges (Google One, Strava, iCloud, Adobe), membership fees
- health: pharmacies, doctors, gyms, medical, dental, fitness, supplements
- travel: flights, hotels, Airbnb, vacation rentals, travel agencies
- utilities: internet, phone, electricity, water, cable, insurance (GEICO, State Farm, Progressive, Allstate)
- other: anything else

Rules for merchant_name:
- Extract the BRAND NAME only — strip store numbers, location codes, booking IDs, and terminal prefixes
- "AIRBNB * HMD4SM3882" → "Airbnb"
- "AIRBNB * HM3AH3J5J5" → "Airbnb"
- "COSTCO WHSE #0147" → "Costco"
- "COSTCO GAS #0131" → "Costco"
- "TRADER JOE'S #232 SAN FRANCISCO CA" → "Trader Joe's"
- "TST* BLUE BOTTLE COFFEE" → "Blue Bottle Coffee"
- "SQ *SWEET MAPLE SF" → "Sweet Maple"
- "AMAZON.COM*AB12CD34" → "Amazon"
- "NETFLIX.COM" → "Netflix"
- "UBER* TRIP" → "Uber"

Rules for city:
- Extract city only if clearly present in the description (e.g. "SAN FRANCISCO", "NEW YORK")
- null for online merchants or when city is absent

Rules for is_online:
- true only for purely online services (Netflix, Amazon, Spotify, etc.)
- false for physical stores even if they also have an online presence

Return ONLY a JSON array with these 6 fields per object: id, category, merchant_name, city, is_online, merchant_type.
No markdown, no explanation, no extra text.

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
