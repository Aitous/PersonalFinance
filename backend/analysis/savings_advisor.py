from typing import Dict, List, Optional
from backend.llm.base import LLMProvider

SAVINGS_PROMPT = """You are a personal finance advisor. Based on the spending summary below,
provide 3-5 specific, actionable saving tips. Be concrete — reference actual numbers.

Period: {period}

Spending by category (USD):
{categories}

Active recurring subscriptions ({sub_count} total, ${sub_monthly:.2f}/mo):
{subscriptions}

Return a numbered list only. No preamble or closing remarks."""

class SavingsAdvisor:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def get_tips(self, category_summary: Dict, period: str, subscriptions: Optional[List[dict]] = None) -> List[str]:
        categories_text = "\n".join(
            f"- {cat}: ${data['total']:.0f} total" + (f", ${data['avg_monthly']:.0f}/mo avg" if "avg_monthly" in data else "")
            for cat, data in category_summary.items()
        )

        subs = subscriptions or []
        sub_monthly = sum(
            s["monthly_amount"] if "monthly_amount" in s else
            (s["amount"] / 12 if s["frequency"] == "annual" else s["amount"])
            for s in subs
        )
        subs_text = "\n".join(
            (f"- {s['name']}: ${s['monthly_amount']:.2f}/mo estimated (billed {s['frequency']})"
             if "monthly_amount" in s else f"- {s['name']}: ${s['amount']:.2f}/{s['frequency']}")
            for s in sorted(subs, key=lambda x: -x.get("monthly_amount", x.get("amount", 0)))
        ) or "None detected"

        prompt = SAVINGS_PROMPT.format(
            period=period,
            categories=categories_text,
            sub_count=len(subs),
            sub_monthly=sub_monthly,
            subscriptions=subs_text,
        )
        response = self._llm.complete(prompt)

        tips = []
        for line in response.strip().splitlines():
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                cleaned = line.lstrip("0123456789.-) ").strip()
                if cleaned:
                    tips.append(cleaned)
        return tips
