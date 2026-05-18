import pytest
from unittest.mock import MagicMock
from backend.analysis.savings_advisor import SavingsAdvisor

def test_generates_tips_from_category_summary():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = (
        "1. Cut dining by cooking at home twice a week.\n"
        "2. Rotate streaming services instead of running all at once."
    )
    advisor = SavingsAdvisor(llm=mock_llm)
    summary = {
        "dining": {"total": 847, "avg_monthly": 282},
        "subscriptions": {"total": 312, "count": 8},
    }
    tips = advisor.get_tips(summary, period="Feb–Apr 2025")
    assert len(tips) == 2
    assert "dining" in tips[0].lower()
    mock_llm.complete.assert_called_once()

def test_prompt_contains_category_data():
    mock_llm = MagicMock()
    mock_llm.complete.return_value = "1. Save more."
    advisor = SavingsAdvisor(llm=mock_llm)
    summary = {"groceries": {"total": 500, "avg_monthly": 166}}
    advisor.get_tips(summary, period="Q1 2025")
    prompt_used = mock_llm.complete.call_args[0][0]
    assert "groceries" in prompt_used
    assert "500" in prompt_used
