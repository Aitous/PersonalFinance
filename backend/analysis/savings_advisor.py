import json
from typing import Dict, List
from backend.llm.base import LLMProvider

SAVINGS_PROMPT = """You are a personal finance advisor. Based on the spending summary below,
provide 3-5 specific, actionable saving tips. Be concrete — reference actual numbers.

Period: {period}

Spending by category (USD):
{categories}

Return a numbered list only. No preamble or closing remarks."""

class SavingsAdvisor:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def get_tips(self, category_summary: Dict, period: str) -> List[str]:
        categories_text = "\n".join(
            f"- {cat}: ${data['total']:.0f} total"
            + (f", ${data['avg_monthly']:.0f}/mo avg" if "avg_monthly" in data else "")
            + (f", {data['count']} services" if "count" in data else "")
            for cat, data in category_summary.items()
        )
        prompt = SAVINGS_PROMPT.format(period=period, categories=categories_text)
        response = self._llm.complete(prompt)

        tips = []
        for line in response.strip().splitlines():
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                cleaned = line.lstrip("0123456789.-) ").strip()
                if cleaned:
                    tips.append(cleaned)
        return tips
