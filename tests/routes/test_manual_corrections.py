from contextlib import contextmanager
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.database import get_data_revision
from backend.db.models import Base, ImportBatch, ImportedRow, MerchantAlias, Transaction
from backend.main import app


def test_merchant_category_rule_can_be_created_listed_and_disabled():
    from unittest.mock import patch
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with patch("backend.routes.transactions.get_session", session_scope):
        client = TestClient(app)
        created = client.post("/category-rules", json={"merchant": "Trader Joe's", "category": "groceries"})
        assert created.status_code == 200
        assert created.json()["enabled"] is True
        assert client.get("/category-rules").json()[0]["category"] == "groceries"
        changed = client.patch(f"/category-rules/{created.json()['id']}", json={"enabled": False})
        assert changed.status_code == 200 and changed.json()["enabled"] is False
        assert client.post("/category-rules", json={"merchant": "  ", "category": "groceries"}).status_code == 422
    engine.dispose()


def test_transaction_provenance_reports_import_and_manual_category():
    from unittest.mock import patch
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with session_scope() as session:
        session.add(Transaction(id="tx", source="chase", date=date(2026, 1, 1), description="STORE", amount=12, category="groceries", manual_category=True))
        session.add(ImportBatch(id="batch", bank="chase", filename="statement.csv", checksum="digest", status="imported"))
        session.add(ImportedRow(batch_id="batch", transaction_id="tx", row_number=4, row_hash="hash", status="accepted"))
    with patch("backend.routes.transactions.get_session", session_scope):
        client = TestClient(app)
        result = client.get("/transactions/tx/provenance")
        assert result.status_code == 200
        assert result.json()["manual_category"] is True
        assert result.json()["imports"][0]["filename"] == "statement.csv"
        assert result.json()["imports"][0]["row_number"] == 4
        assert client.get("/transactions/missing/provenance").status_code == 404
    engine.dispose()


def test_bulk_category_changes_are_atomic_and_marked_manual():
    from unittest.mock import patch
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with session_scope() as session:
        session.add_all([Transaction(id=key, source="chase", date=date(2026, 1, 1), description=key, amount=12, category="other") for key in ("a", "b")])
    with patch("backend.routes.transactions.get_session", session_scope), patch("backend.routes.search._embed_all"):
        client = TestClient(app)
        assert client.patch("/transactions/bulk/category", json={"ids": ["a", "missing"], "category": "groceries"}).status_code == 404
        with session_scope() as session:
            assert session.get(Transaction, "a").category == "other"
        response = client.patch("/transactions/bulk/category", json={"ids": ["a", "b"], "category": "groceries"})
        assert response.status_code == 200
        assert response.json()["updated"] == 2
    with session_scope() as session:
        assert all(session.get(Transaction, key).category == "groceries" and session.get(Transaction, key).manual_category for key in ("a", "b"))
        assert get_data_revision(session) == 1
    engine.dispose()


def test_manual_field_and_category_edits_are_marked_and_revisioned():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with session_scope() as session:
        session.add(Transaction(id="tx", source="chase", date=date(2026, 1, 1),
            description="RAW STORE", amount=12, category="other",
            raw_enrichment='{"merchant_name":"Model Store"}'))

    from unittest.mock import patch
    with patch("backend.routes.transactions.get_session", session_scope), \
         patch("backend.routes.search.embed_texts", side_effect=lambda texts: __import__("numpy").zeros((len(texts), 384))):
        client = TestClient(app)
        fields = client.patch("/transactions/tx", json={"merchant_name": "User Store", "city": "Oakland"})
        assert fields.status_code == 200
        category = client.patch("/transactions/tx/category", json={"category": "shopping"})
        assert category.status_code == 200
        invalid = client.patch("/transactions/tx/category", json={"category": "not-a-category"})
        assert invalid.status_code == 422

    with session_scope() as session:
        tx = session.get(Transaction, "tx")
        assert tx.manual_fields == '["city", "merchant_name"]'
        assert tx.manual_category is True
        assert tx.raw_enrichment == '{"merchant_name":"Model Store"}'
        assert get_data_revision(session) == 2
    engine.dispose()


def test_alias_acceptance_and_disable_are_reversible_without_mutating_source_name():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with session_scope() as session:
        session.add(Transaction(id="tx", source="chase", date=date(2026, 1, 1),
            description="RAW", amount=12, merchant_name="Store #14"))

    from unittest.mock import patch
    with patch("backend.routes.transactions.get_session", session_scope), \
         patch("backend.routes.search.embed_texts", side_effect=lambda texts: __import__("numpy").zeros((len(texts), 384))):
        client = TestClient(app)
        accepted = client.post("/merchants/aliases", json={"alias": "Store #14", "canonical": "Store"})
        assert accepted.status_code == 200
        alias_id = accepted.json()["id"]
        disabled = client.patch(f"/merchants/aliases/{alias_id}", json={"enabled": False})
        assert disabled.status_code == 200 and disabled.json()["enabled"] is False

    with session_scope() as session:
        assert session.get(Transaction, "tx").merchant_name == "Store #14"
        alias = session.get(MerchantAlias, alias_id)
        assert alias.enabled is False and alias.canonical == "Store"
    engine.dispose()
