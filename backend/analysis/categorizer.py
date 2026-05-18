from typing import Dict, List
from backend.db.models import Transaction
from backend.llm.base import LLMProvider

VALID_CATEGORIES = {
    "dining", "groceries", "transport", "shopping",
    "entertainment", "subscriptions", "health", "travel",
    "utilities", "other",
}

CATEGORIZE_PROMPT = """Categorize each transaction below into exactly one of these categories:
dining, groceries, transport, shopping, entertainment, subscriptions, health, travel, utilities, other

Return one line per transaction in the format: <id>: <category>
Only return the lines, nothing else.

Transactions:
{transactions}"""

class Categorizer:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def categorize(self, transactions: List[Transaction]) -> Dict[str, str]:
        if not transactions:
            return {}

        tx_lines = "\n".join(
            f"{tx.id}: {tx.description} ${abs(tx.amount):.2f}"
            for tx in transactions
        )
        prompt = CATEGORIZE_PROMPT.format(transactions=tx_lines)
        response = self._llm.complete(prompt)

        result: Dict[str, str] = {}
        for line in response.strip().splitlines():
            if ":" not in line:
                continue
            tx_id, _, category = line.partition(":")
            category = category.strip().lower()
            result[tx_id.strip()] = category if category in VALID_CATEGORIES else "other"

        return result
