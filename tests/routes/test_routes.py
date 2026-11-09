import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from backend.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _stub_ask_catalog(monkeypatch):
    # Ask-route tests use lightweight session doubles; catalog behavior has its
    # own tests against a real SQLAlchemy session.
    monkeypatch.setattr("backend.analysis.data_catalog.build_catalog", lambda session: {})

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_cors_allows_local_frontend_origins(origin):
    response = client.options("/transactions", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin

def test_get_transactions_empty():
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    with patch("backend.routes.transactions.get_session", return_value=mock_session):
        response = client.get("/transactions")
        assert response.status_code == 200
        assert response.json() == []

def test_get_subscriptions_empty():
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    with patch("backend.routes.transactions.get_session", return_value=mock_session):
        response = client.get("/subscriptions")
        assert response.status_code == 200

def test_get_subscriptions_includes_only_linked_transaction_evidence():
    from datetime import date
    import json
    from types import SimpleNamespace
    from contextlib import contextmanager

    subscription = SimpleNamespace(
        id="sub-1", description="Google One", amount=1.99, frequency="monthly",
        last_charged=date(2026, 10, 1), active=True, origin="detected", dismissed=False,
        supporting_transaction_ids=json.dumps(["tx-1"]),
    )
    transaction = SimpleNamespace(
        id="tx-1", date=date(2026, 10, 1), description="GOOGLE*ONE",
        amount=1.99, source="Chase", merchant_name="Google One",
    )

    class Result:
        def __init__(self, rows): self.rows = rows
        def scalars(self): return self
        def all(self): return self.rows

    class Session:
        def __init__(self): self.calls = 0
        def execute(self, query):
            self.calls += 1
            return Result([subscription] if self.calls == 1 else [transaction])

    @contextmanager
    def fake_session():
        yield Session()

    with patch("backend.routes.transactions.get_session", fake_session):
        response = client.get("/subscriptions")

    assert response.status_code == 200
    item = response.json()[0]
    assert item["origin"] == "detected"
    assert item["supporting_transactions"] == [{
        "id": "tx-1", "date": "2026-10-01", "description": "GOOGLE*ONE",
        "amount": 1.99, "source": "Chase", "merchant_name": "Google One",
    }]

def test_transaction_question_returns_grounded_matches_and_summary():
    from contextlib import contextmanager
    from datetime import date
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(id="tx-a", date=date(2026, 8, 1), amount=15.0, amount_minor=1500,
            description="ANTHROPIC", merchant_name="Anthropic", city="San Francisco",
            category="subscriptions", source="Chase", kind=None),
        SimpleNamespace(id="tx-b", date=date(2026, 9, 1), amount=20.0, amount_minor=2000,
            description="ANTHROPIC", merchant_name="Anthropic", city="San Francisco",
            category="subscriptions", source="Amex", kind=None),
        SimpleNamespace(id="tx-c", date=date(2026, 9, 2), amount=12.0, amount_minor=1200,
            description="COFFEE", merchant_name="Cafe", city="Oakland",
            category="dining", source="Chase", kind=None),
    ]

    class Result:
        def scalars(self): return self
        def all(self): return rows

    class Session:
        def execute(self, query): return Result()

    class Provider:
        def complete_json(self, prompt):
            if prompt.startswith("Return valid JSON only"):
                return '{"answer":"You had two Anthropic charges totaling $35.00."}'
            return '{"merchant":"Anthropic","transaction_type":"spending"}'

    @contextmanager
    def fake_session():
        yield Session()

    with patch("backend.routes.analysis.get_session", fake_session), \
         patch("backend.llm.factory.get_llm_provider", return_value=Provider()):
        response = client.post("/analysis/ask", json={"question": "How much did I spend at Anthropic?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["match_count"] == 2
    assert payload["gross_purchases"] == 35.0
    assert [tx["id"] for tx in payload["transactions"]] == ["tx-b", "tx-a"]
    assert payload["answer"] == "You had two Anthropic charges totaling $35.00."

def test_transaction_question_snapshots_rows_before_session_closes():
    from contextlib import contextmanager
    from datetime import date

    class TransactionRow:
        def __init__(self):
            self.expired = False
            self.id = "tx-a"
            self.date = date(2026, 8, 1)
            self.amount = 15.0
            self.amount_minor = 1500
            self.description = "ANTHROPIC"
            self.merchant_name = "Anthropic"
            self.city = "San Francisco"
            self.category = "subscriptions"
            self.source = "Chase"
            self.kind = None

        def __getattribute__(self, name):
            if name not in {"expired", "__dict__", "__class__", "__getattribute__"} and object.__getattribute__(self, "expired"):
                raise RuntimeError("transaction row expired when session closed")
            return object.__getattribute__(self, name)

    row = TransactionRow()

    class Result:
        def scalars(self): return self
        def all(self): return [row]

    class Session:
        def execute(self, query): return Result()
        def __enter__(self): return self
        def __exit__(self, *args): row.expired = True

    class Provider:
        def complete_json(self, prompt):
            if prompt.startswith("Return valid JSON only"):
                return '{"answer":"One matching transaction."}'
            return '{"merchant":"Anthropic"}'

    @contextmanager
    def fake_session():
        with Session() as session:
            yield session

    with patch("backend.routes.analysis.get_session", fake_session), \
         patch("backend.llm.factory.get_llm_provider", return_value=Provider()):
        response = TestClient(app, raise_server_exceptions=False).post(
            "/analysis/ask", json={"question": "Show Anthropic"})
    assert response.status_code == 200
    assert response.json()["match_count"] == 1

def test_transaction_question_uses_prior_turn_context_for_followups():
    from contextlib import contextmanager
    from datetime import date
    from types import SimpleNamespace

    rows = [SimpleNamespace(
        id="tx-a", date=date(2026, 8, 1), amount=15.0, amount_minor=1500,
        description="ANTHROPIC", merchant_name="Anthropic", city="Oakland",
        category="subscriptions", source="Chase", kind=None,
    )]

    class Result:
        def scalars(self): return self
        def all(self): return rows

    class Session:
        def execute(self, query): return Result()

    class Provider:
        prompts = []
        def complete_json(self, prompt):
            self.prompts.append(prompt)
            if prompt.startswith("Return valid JSON only"):
                return '{"answer":"One of those charges was in Oakland."}'
            return '{"merchant":"Anthropic","city":"Oakland","transaction_type":"spending"}'

    provider = Provider()

    @contextmanager
    def fake_session():
        yield Session()

    history = [{
        "question": "Show all Anthropic charges",
        "answer": "You had three Anthropic charges.",
        "criteria": {"merchant": "Anthropic", "city": None},
        "match_count": 3,
        "gross_purchases": 55.0,
        "refunds": 0.0,
    }]
    with patch("backend.routes.analysis.get_session", fake_session), \
         patch("backend.llm.factory.get_llm_provider", return_value=provider):
        response = client.post("/analysis/ask", json={
            "question": "How many of those were in Oakland?", "history": history,
        })

    assert response.status_code == 200
    assert response.json()["match_count"] == 1
    assert "Show all Anthropic charges" in provider.prompts[0]
    assert "Anthropic" in provider.prompts[1]


def test_transaction_question_compares_two_explicit_merchant_groups():
    from contextlib import contextmanager
    from datetime import date
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(id="a", date=date(2026, 8, 1), amount=25.0, amount_minor=2500,
            description="ANTHROPIC", merchant_name="Anthropic", city="Oakland",
            category="software", source="Chase", kind=None),
        SimpleNamespace(id="b", date=date(2026, 8, 2), amount=15.0, amount_minor=1500,
            description="OPENAI", merchant_name="OpenAI", city="Oakland",
            category="software", source="Chase", kind=None),
    ]

    class Result:
        def scalars(self): return self
        def all(self): return rows

    class Session:
        def execute(self, query): return Result()

    class Provider:
        def complete_json(self, prompt):
            if prompt.startswith("Return valid JSON only"):
                return '{"answer":"Anthropic was $25 and OpenAI was $15."}'
            return '{"merchant":"Anthropic","transaction_type":"spending","comparison_filters":{"merchant":"OpenAI","transaction_type":"spending"}}'

    @contextmanager
    def fake_session():
        yield Session()

    with patch("backend.routes.analysis.get_session", fake_session), \
         patch("backend.llm.factory.get_llm_provider", return_value=Provider()):
        response = client.post("/analysis/ask", json={"question": "Compare Anthropic with OpenAI"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["match_count"] == 1
    assert payload["gross_purchases"] == 25.0
    assert payload["comparison"]["match_count"] == 1
    assert payload["comparison"]["gross_purchases"] == 15.0
    assert payload["comparison"]["criteria"]["merchant"] == "OpenAI"
    assert [row["id"] for row in payload["transactions"]] == ["a"]
    assert [row["id"] for row in payload["comparison"]["transactions"]] == ["b"]
    assert payload["comparison"]["displayed_count"] == 1
    assert payload["comparison"]["truncated"] is False


def test_transaction_agent_runs_bounded_search_then_month_aggregation():
    from contextlib import contextmanager
    from datetime import date
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(id="jan", date=date(2026, 1, 5), amount=20.0, amount_minor=2000,
            description="ANTHROPIC", merchant_name="Anthropic", city="Oakland",
            category="software", source="Chase", kind=None),
        SimpleNamespace(id="feb", date=date(2026, 2, 5), amount=30.0, amount_minor=3000,
            description="ANTHROPIC", merchant_name="Anthropic", city="Oakland",
            category="software", source="Chase", kind=None),
    ]

    class Result:
        def scalars(self): return self
        def all(self): return rows

    class Session:
        def execute(self, query): return Result()

    class Provider:
        def __init__(self): self.calls = 0
        def complete_json(self, prompt):
            self.calls += 1
            if self.calls == 1:
                return '{"action":"search_transactions","arguments":{"criteria":{"merchant":"Anthropic","date_from":"2026-01-01","date_to":"2026-02-28","transaction_type":"spending"}}}'
            if self.calls == 2:
                return '{"action":"aggregate_results","arguments":{"dataset_id":"result_1","group_by":"month"}}'
            if self.calls == 3:
                return '{"action":"final","answer":"January was $20 and February was $30.","primary_dataset_id":"result_1"}'
            raise AssertionError("agent exceeded the planned step count")

    provider = Provider()

    @contextmanager
    def fake_session():
        yield Session()

    with patch("backend.routes.analysis.get_session", fake_session), \
         patch("backend.llm.factory.get_llm_provider", return_value=provider):
        response = client.post("/analysis/ask", json={"question": "Show Anthropic's monthly trend from January through February 2026"})

    assert response.status_code == 200
    assert response.json()["tool_steps"] == ["search_transactions", "aggregate_results"]
    assert response.json()["match_count"] == 2


def test_transaction_agent_searches_both_sides_before_comparing():
    from contextlib import contextmanager
    from datetime import date
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(id="a", date=date(2026, 1, 5), amount=25.0, amount_minor=2500,
            description="ANTHROPIC", merchant_name="Anthropic", city="Oakland",
            category="software", source="Chase", kind=None),
        SimpleNamespace(id="b", date=date(2026, 1, 6), amount=15.0, amount_minor=1500,
            description="OPENAI", merchant_name="OpenAI", city="Oakland",
            category="software", source="Chase", kind=None),
    ]

    class Result:
        def scalars(self): return self
        def all(self): return rows

    class Session:
        def execute(self, query): return Result()

    class Provider:
        def __init__(self): self.calls = 0
        def complete_json(self, prompt):
            self.calls += 1
            if self.calls == 1:
                return '{"action":"search_transactions","arguments":{"criteria":{"merchant":"Anthropic","transaction_type":"spending"}}}'
            if self.calls == 2:
                return '{"action":"search_transactions","arguments":{"criteria":{"merchant":"OpenAI","transaction_type":"spending"}}}'
            if self.calls == 3:
                return '{"action":"compare_results","arguments":{"left_dataset_id":"result_1","right_dataset_id":"result_2"}}'
            if self.calls == 4:
                return '{"action":"final","answer":"OpenAI spending was $10 lower than Anthropic.","primary_dataset_id":"result_2"}'
            raise AssertionError("agent exceeded its tool budget")

    provider = Provider()

    @contextmanager
    def fake_session():
        yield Session()

    with patch("backend.routes.analysis.get_session", fake_session), \
         patch("backend.llm.factory.get_llm_provider", return_value=provider):
        response = client.post("/analysis/ask", json={"question": "Compare Anthropic versus OpenAI"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_steps"] == ["search_transactions", "search_transactions", "compare_results"]
    assert payload["comparison"]["net_spending_delta_right_minus_left"] == -10.0
    assert payload["comparison"]["match_count"] == 1
    assert payload["criteria"]["merchant"] == "Anthropic"
    assert [row["id"] for row in payload["transactions"]] == ["a"]
    assert [row["id"] for row in payload["comparison"]["transactions"]] == ["b"]
    assert payload["comparison"]["displayed_count"] == 1
    assert payload["comparison"]["truncated"] is False


def test_transaction_agent_accepts_grounded_grouped_sql_as_comparison_evidence():
    from contextlib import contextmanager
    from datetime import date
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(id="tx-a", date=date(2026, 1, 1), amount=15.0, amount_minor=1500,
            description="A", merchant_name="A", city="Oakland", category="food", source="bank", kind=None,
            metadata_=None, currency="USD", account_id="acct-1"),
        SimpleNamespace(id="tx-b", date=date(2026, 1, 2), amount=25.0, amount_minor=2500,
            description="B", merchant_name="B", city="Oakland", category="food", source="bank", kind=None,
            metadata_=None, currency="USD", account_id="acct-1"),
    ]

    class Result:
        def scalars(self): return self
        def all(self): return rows
    class Session:
        def execute(self, query): return Result()
    class Provider:
        def __init__(self): self.calls = 0
        def complete_json(self, prompt):
            self.calls += 1
            if self.calls == 1:
                return '{"action":"sql_query","arguments":{"sql":"SELECT merchant_name AS group_name, SUM(net_spending) AS net FROM transactions GROUP BY merchant_name ORDER BY group_name"}}'
            return '{"action":"final","answer":"A is $15 and B is $25."}'
    @contextmanager
    def fake_session(): yield Session()

    with patch("backend.routes.analysis.get_session", fake_session), \
         patch("backend.llm.factory.get_llm_provider", return_value=Provider()):
        response = client.post("/analysis/ask", json={"question": "Compare spending at A versus B"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_mode"] == "sql"
    assert payload["tool_steps"] == ["sql_query"]
    assert payload["comparison"]["source"] == "sql"
    assert payload["comparison"]["rows"] == [
        {"group_name": "A", "net": 15.0}, {"group_name": "B", "net": 25.0},
    ]


def test_transaction_agent_requires_search_or_explicit_coverage_tool():
    from contextlib import contextmanager
    from datetime import date
    from types import SimpleNamespace

    rows = [SimpleNamespace(id="a", date=date(2026, 1, 1), amount=5.0, amount_minor=500,
        description="UNKNOWN CITY", merchant_name="Shop", city=None, category="other",
        source="Chase", kind=None)]

    class Result:
        def scalars(self): return self
        def all(self): return rows

    class Session:
        def execute(self, query): return Result()

    class Provider:
        def __init__(self, responses): self.responses = iter(responses)
        def complete_json(self, prompt): return next(self.responses)

    @contextmanager
    def fake_session():
        yield Session()

    no_tool = Provider(['{"action":"final","answer":"There were no transactions."}'])
    with patch("backend.routes.analysis.get_session", fake_session), \
         patch("backend.llm.factory.get_llm_provider", return_value=no_tool):
        rejected = client.post("/analysis/ask", json={"question": "How much did I spend?"})
    assert rejected.status_code == 422

    coverage = Provider([
        '{"action":"coverage_summary","arguments":{}}',
        '{"action":"final","answer":"Coverage is observed only; one transaction has no city."}',
    ])
    with patch("backend.routes.analysis.get_session", fake_session), \
         patch("backend.llm.factory.get_llm_provider", return_value=coverage):
        response = client.post("/analysis/ask", json={"question": "What is the transaction coverage?"})
    assert response.status_code == 200
    facts = response.json()["tool_results"][0]["result"]
    assert facts["transactions_missing_city_in_full_dataset"] == 1
    assert facts["complete_city_coverage"] is False
