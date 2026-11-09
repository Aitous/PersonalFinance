from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from backend.routes import search


def test_hybrid_search_uses_keyword_fallback_when_local_embeddings_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_LOCAL_EMBEDDINGS", "false")
    tx = SimpleNamespace(
        id="tx-1",
        source="chase",
        date=date(2026, 10, 1),
        description="COFFEE SHOP OAKLAND",
        amount=8.5,
        category="dining",
        merchant_name="Coffee Shop",
        merchant_type="cafe",
        city="Oakland",
        is_online=False,
        is_subscription=False,
        embedding="[0.1, 0.2]",
        embedding_model_version="test-model",
        embedding_input_hash="test-hash",
        metadata_=None,
    )

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [tx]

    class Session:
        def execute(self, _query):
            return Result()

    @contextmanager
    def fake_session():
        yield Session()

    with patch.object(search, "get_session", fake_session), \
         patch.object(search, "active_aliases", return_value={}), \
         patch.object(search, "embedding_is_current", return_value=True), \
         patch.object(search, "embed_query", side_effect=AssertionError("embedding model must not load")):
        response = search.search_transactions(
            q="coffee shop", mode="hybrid", limit=50, offset=0, query=object()
        )

    assert response["mode"] == "keyword"
    assert response["semantic_search_available"] is False
    assert [row["id"] for row in response["results"]] == ["tx-1"]
