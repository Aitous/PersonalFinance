from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace


def test_data_quality_contract_and_no_coverage_claim(monkeypatch):
    from backend.routes import analysis

    rows = [
        SimpleNamespace(source="Chase", date=date(2026, 1, 2), city=None, merchant_name="Cafe", account_id="a", category="dining", enrichment_status="complete"),
        SimpleNamespace(source="Chase", date=date(2026, 2, 3), city="Oakland", merchant_name=None, account_id=None, category=None, enrichment_status="fallback"),
    ]

    class Result:
        def scalars(self):
            return self

        def all(self):
            return rows

    class Session:
        def execute(self, _query):
            return Result()

    @contextmanager
    def fake_session():
        yield Session()

    monkeypatch.setattr(analysis, "get_session", fake_session)
    result = analysis.get_data_quality()
    assert result["sources"] == [{
        "source": "Chase", "transaction_count": 2,
        "first_date": "2026-01-02", "last_date": "2026-02-03",
    }]
    assert result["total_transactions"] == 2
    assert result["missing_city"] == 1
    assert result["missing_merchant"] == 1
    assert result["unassigned_account"] == 1
    assert result["missing_category"] == 1
    assert result["enrichment_fallback"] == 1
    assert "do not establish complete account coverage" in result["coverage_note"]


def test_import_history_is_bounded_to_the_requested_recent_count(monkeypatch):
    from types import SimpleNamespace
    from backend.routes import import_csv

    batches = [SimpleNamespace(
        id=str(i), bank="chase", account_id=None, filename=f"batch-{i}.csv", checksum="hash",
        status="imported", input_count=10, parsed_count=10, rejected_count=0,
        duplicate_count=0, new_count=10, from_date=date(2026, 1, 1),
        to_date=date(2026, 1, 31), created_at=None,
    ) for i in range(5)]

    class Result:
        def __init__(self, query):
            self.query = query

        def scalars(self):
            return self

        def all(self):
            return batches[:self.query._limit_clause.value]

    class Session:
        def execute(self, query):
            return Result(query)

    @contextmanager
    def fake_session():
        yield Session()

    monkeypatch.setattr(import_csv, "get_session", fake_session)
    assert len(import_csv.list_import_batches(limit=2)) == 2


def test_search_index_status_counts_stale_rows_without_loading_model():
    from backend.routes.search import _index_status

    rows = [
        SimpleNamespace(embedding=None, embedding_input_hash=None, embedding_model_version=None),
        SimpleNamespace(embedding="[]", embedding_input_hash="wrong", embedding_model_version="old"),
    ]
    result = _index_status(rows)
    assert result == {
        "embedded_count": 0,
        "stale_embedding_count": 2,
        "total_transactions": 2,
        "index_status": "stale",
    }


def test_kind_based_spending_and_refund_selection_includes_legacy_signed_rows():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.db.models import Base, Transaction
    from backend.transaction_filters import transaction_query

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Transaction(id="purchase", source="test", date=date(2026, 1, 1), description="Shop", amount=10, kind="purchase"),
            Transaction(id="refund", source="test", date=date(2026, 1, 2), description="Return", amount=10, kind="refund"),
            Transaction(id="legacy-refund", source="test", date=date(2026, 1, 3), description="Return old", amount=-5),
            Transaction(id="payment", source="test", date=date(2026, 1, 4), description="Bank transfer", amount=100, kind="transfer"),
        ])
        session.commit()
        spending = session.execute(transaction_query(tx_type="spending", month=None, min_amount=None, max_amount=None)).scalars().all()
        refunds = session.execute(transaction_query(tx_type="refunds", month=None, min_amount=None, max_amount=None)).scalars().all()
        assert {tx.id for tx in spending} == {"purchase"}
        assert {tx.id for tx in refunds} == {"refund", "legacy-refund"}
    engine.dispose()


def test_narrative_returns_conflict_if_data_revision_changes_during_llm_call(monkeypatch):
    from contextlib import contextmanager
    import sys
    from types import SimpleNamespace

    import pytest
    from fastapi import HTTPException
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from backend.db.database import invalidate_derived_data
    from backend.db.models import Base, MonthlyReportCache
    from backend.routes import analysis

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        session = Session(engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    with session_scope() as session:
        invalidate_derived_data(session)

    monkeypatch.setattr(analysis, "get_session", session_scope)

    class MutatingLLM:
        def complete(self, _prompt):
            with session_scope() as session:
                invalidate_derived_data(session)
            return "Narrative from the old revision."

    fake_factory = SimpleNamespace(get_llm_provider=lambda **_kwargs: MutatingLLM())
    monkeypatch.setitem(sys.modules, "backend.llm.factory", fake_factory)

    try:
        with pytest.raises(HTTPException) as exc_info:
            analysis.generate_monthly_narrative(year=2026, month=1)
        assert exc_info.value.status_code == 409
        assert "Retry" in exc_info.value.detail
        with session_scope() as session:
            assert session.execute(select(MonthlyReportCache)).scalars().all() == []
    finally:
        engine.dispose()
