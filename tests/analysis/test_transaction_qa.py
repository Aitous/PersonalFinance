from datetime import date
from types import SimpleNamespace


def test_filters_multiple_transactions_with_normalized_criteria():
    from backend.analysis.transaction_qa import filter_transactions

    rows = [
        SimpleNamespace(id="1", date=date(2026, 2, 1), amount=18.25, description="Cafe OAK",
            merchant_name="Cafe Oak", city="Oakland", category="dining", source="Chase", kind=None),
        SimpleNamespace(id="2", date=date(2026, 2, 8), amount=24.00, description="CAFE OAK",
            merchant_name="Cafe Oak", city="Oakland", category="dining", source="Amex", kind=None),
        SimpleNamespace(id="3", date=date(2026, 2, 4), amount=18.25, description="Cafe OAK",
            merchant_name="Cafe Oak", city="Berkeley", category="dining", source="Chase", kind=None),
    ]
    criteria = {
        "merchant": "cafe oak", "city": "OAKLAND", "category": "dining",
        "source": None, "date_from": "2026-02-01", "date_to": "2026-02-28",
        "amount_min": 10, "amount_max": 25, "transaction_type": "spending",
    }

    from backend.analysis.transaction_qa import normalize_criteria
    result = filter_transactions(rows, normalize_criteria(criteria))

    assert [row.city for row in result] == ["Oakland", "Oakland"]


def test_rejects_invalid_filter_values_and_parses_valid_llm_json():
    from backend.analysis.transaction_qa import normalize_criteria

    criteria = normalize_criteria({
        "merchant": "  Anthropic  ", "city": 42, "category": "subscriptions", "source": None,
        "date_from": "not-a-date", "date_to": "2026-04-30", "amount_min": -5,
        "amount_max": "bad", "transaction_type": "everything",
    })

    assert criteria == {
        "merchant": "Anthropic", "city": None, "category": "subscriptions", "source": None,
        "date_from": None, "date_to": date(2026, 4, 30), "amount_min": None,
        "amount_max": None, "transaction_type": "all",
    }


def test_answer_prompt_uses_aggregates_instead_of_relisting_transactions():
    from backend.analysis.transaction_qa import answer_prompt

    row = SimpleNamespace(
        id="tx-1", date=date(2026, 2, 1), amount=18.25, description="PRIVATE RAW DESCRIPTION",
        merchant_name="Cafe Oak", city="Oakland", category="dining", source="Chase",
    )
    prompt = answer_prompt("How much in Oakland?", {"city": "Oakland"}, [row], 1, 18.25, 0)

    assert "PRIVATE RAW DESCRIPTION" not in prompt
    assert "at most two short sentences" in prompt.lower()
    assert '"answer"' in prompt


def test_parse_answer_removes_markdown_and_bounds_the_summary():
    from backend.analysis.transaction_qa import parse_answer

    assert parse_answer('{"answer":"**Found 11 matches.**\\nThe total is $920.98."}') == (
        "Found 11 matches. The total is $920.98."
    )


def test_summarize_transactions_keeps_refunds_out_of_purchase_breakdowns():
    from backend.analysis.transaction_qa import summarize_transactions

    rows = [
        SimpleNamespace(id="p", date=date(2026, 2, 1), amount=40.0, amount_minor=4000,
            description="SHOP", merchant_name="Shop", city="Oakland", category="shopping", kind=None),
        SimpleNamespace(id="r", date=date(2026, 2, 2), amount=-10.0, amount_minor=-1000,
            description="SHOP REFUND", merchant_name="Shop", city="Oakland", category="shopping", kind="refund"),
    ]

    facts = summarize_transactions(rows)

    assert facts["gross_purchases"] == 40.0
    assert facts["refunds"] == 10.0
    assert facts["net_spending"] == 30.0
    assert facts["merchants"] == [{"name": "Shop", "net_spending": 30.0}]


def test_followup_carries_previous_filters_and_comparison_requires_two_valid_dates():
    from backend.analysis.transaction_qa import carry_forward_criteria, comparison_overrides, comparison_window, normalize_criteria

    history = [{"criteria": {"merchant": "Anthropic", "date_from": "2026-01-01",
                              "date_to": "2026-01-31", "transaction_type": "spending"}}]
    current = normalize_criteria({"city": "Oakland"})
    merged = carry_forward_criteria("How many of those were in Oakland?", current, history)

    assert merged["merchant"] == "Anthropic"
    assert merged["city"] == "Oakland"
    assert merged["date_from"] == date(2026, 1, 1)
    assert merged["transaction_type"] == "spending"
    assert comparison_window({"comparison_date_from": "2026-02-01", "comparison_date_to": "2026-02-28"}) == (
        date(2026, 2, 1), date(2026, 2, 28)
    )
    assert comparison_window({"comparison_date_from": "2026-02-28", "comparison_date_to": "2026-02-01"}) is None
    assert comparison_overrides({"comparison_filters": {"city": "Oakland"}}) == {"city": "Oakland"}
    import pytest
    with pytest.raises(ValueError):
        comparison_overrides({"comparison_filters": {"date_from": "2026-03-01", "date_to": "2026-02-01"}})


def test_agent_prompt_anchors_relative_dates_to_today():
    from datetime import date
    from backend.analysis.transaction_qa import agent_step_prompt

    assert date.today().isoformat() in agent_step_prompt("show recent activity")


def test_agent_prompt_includes_catalog_before_planning():
    from backend.analysis.transaction_qa import agent_step_prompt

    prompt = agent_step_prompt("how much by month?", catalog={"categories": [{"name": "Food", "count": 3}]})
    assert "Dataset catalog" in prompt
    assert '"name": "Food"' in prompt
    assert "transactions" in prompt


def test_sql_tool_runs_bounded_read_only_queries_on_curated_snapshot():
    from datetime import date
    from types import SimpleNamespace
    import pytest
    from backend.analysis.transaction_qa import execute_agent_tool

    rows = [SimpleNamespace(id="a", date=date(2026, 1, 2), description="Cafe", amount=12.5,
                            category="Food", merchant_name="Cafe", city="Oakland", country="US",
                            source="bank", kind="purchase", currency="USD", account_id="acct-1")]
    result = execute_agent_tool("sql_query", {"sql": "SELECT city, country, currency, account_id, SUM(gross_purchase) AS total FROM transactions GROUP BY city"}, rows, {})
    assert result["rows"] == [{"city": "Oakland", "country": "US", "currency": "USD", "account_id": "acct-1", "total": 12.5}]
    assert result["evidence_checks"]["grouped"]
    assert result["evidence_checks"]["has_numeric_measure"]
    assert result["evidence"]["sql"].startswith("SELECT")

    for sql in ("DELETE FROM transactions", "ATTACH DATABASE ':memory:' AS other",
                "PRAGMA table_info(transactions)", "SELECT * FROM sqlite_master"):
        with pytest.raises(ValueError):
            execute_agent_tool("sql_query", {"sql": sql}, rows, {})

    catalog = execute_agent_tool("catalog_search", {
        "dimension": "merchant", "query": "Cafe", "offset": 0, "limit": 10,
    }, rows, {})
    assert catalog["matches"][0]["name"] == "Cafe"
    assert catalog["matches"][0]["count"] == 1
    assert catalog["matches"][0]["aliases"] == ["Cafe"]
    assert catalog["total"] == 1


def test_merchant_catalog_search_normalizes_punctuation_and_rejects_similar_names():
    from datetime import date
    from types import SimpleNamespace
    from backend.analysis.transaction_qa import execute_agent_tool

    def tx(id, merchant, description):
        return SimpleNamespace(id=id, date=date(2026, 1, 1), amount=10, description=description,
            merchant_name=merchant, city=None, category=None, source="bank", kind=None)

    rows = [
        tx("a", "TRADER JOE S", "TRADER JOE S #123"),
        tx("b", None, "Trader Joe's #456"),
        tx("c", "Trader Joe's Market", "TRADER JOE'S MARKET #9"),
    ]
    result = execute_agent_tool("catalog_search", {
        "dimension": "merchant", "query": "Trader Joe's", "limit": 20,
    }, rows, {})

    assert result["total"] == 1
    match = result["matches"][0]
    assert match["count"] == 2
    assert match["missing_merchant_name_count"] == 1
    assert "TRADER JOE S #123" in match["descriptions"]
    assert "Trader Joe's #456" in match["descriptions"]
    assert "Trader Joe's Market" not in match["aliases"]


def test_sql_source_values_are_not_silently_truncated():
    from datetime import date
    from types import SimpleNamespace
    import pytest
    from backend.analysis.transaction_qa import execute_agent_tool

    row = SimpleNamespace(id="a", date=date(2026, 1, 2), description="x" * 600, amount=12.5,
        category="Food", merchant_name="Cafe", city="Oakland", country="US", source="bank",
        kind="purchase", currency="USD", account_id="acct-1")
    result = execute_agent_tool("sql_query", {"sql": "SELECT description FROM transactions"}, [row], {})
    assert len(result["rows"][0]["description"]) == 500
    assert result["truncated_cells"] == [{
        "row_index": 0, "column": "description", "original_length": 600, "displayed_length": 500,
    }]

    row.description = "x" * 10_001
    with pytest.raises(ValueError, match="no value was truncated"):
        execute_agent_tool("sql_query", {"sql": "SELECT description FROM transactions"}, [row], {})

    with pytest.raises(ValueError, match="safe isolated execution sandbox is unavailable"):
        execute_agent_tool("python_analysis", {"code": "print(1)"}, [row], {})


def test_followup_can_clear_a_prior_filter_or_reset_all_context():
    from backend.analysis.transaction_qa import carry_forward_criteria, normalize_criteria

    prior = [{"criteria": {"merchant": "Anthropic", "city": "Oakland"}}]
    current = normalize_criteria({})
    cleared = carry_forward_criteria("What about those?", current, prior, clear_filters=["merchant"])
    reset = carry_forward_criteria("What about those?", current, prior, reset=True)

    assert cleared["merchant"] is None
    assert cleared["city"] == "Oakland"
    assert reset["merchant"] is None
    assert reset["city"] is None
