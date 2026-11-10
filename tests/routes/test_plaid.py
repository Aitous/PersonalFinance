import json
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.models import Base, PlaidItem, Transaction
from backend.db.database import initialize_schema
from backend.plaid_client import PlaidAPIError
from backend.main import app
from fastapi.testclient import TestClient


def test_plaid_config_credentials_are_separate_by_environment():
    from backend.routes import plaid

    saved = {}

    class Store:
        def get_bank_credential(self, bank, field):
            return saved.get((bank, field))

        def save_bank_credential(self, bank, field, value):
            saved[(bank, field)] = value

    with patch.object(plaid, "credentials_store", Store()):
        sandbox = plaid.PlaidCredentials(client_id="sandbox-client", secret="sandbox-secret")
        production = plaid.PlaidCredentials(client_id="production-client", secret="production-secret")
        assert plaid.save_config(sandbox, "sandbox")["configured"] is True
        assert plaid.save_config(production, "production")["configured"] is True
        assert plaid.get_config("sandbox")["configured"] is True
        assert plaid.get_config("production")["configured"] is True
        assert saved[("plaid:sandbox", "secret")] == "sandbox-secret"
        assert saved[("plaid:production", "secret")] == "production-secret"


def test_old_plaid_database_gets_additive_import_columns_and_identity_table():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE plaid_items (
            item_id VARCHAR PRIMARY KEY, environment VARCHAR NOT NULL DEFAULT 'sandbox',
            institution_id VARCHAR, institution_name VARCHAR NOT NULL, accounts_json TEXT NOT NULL DEFAULT '[]',
            cursor TEXT, last_sync_at DATETIME, last_sync_status VARCHAR NOT NULL DEFAULT 'not_synced',
            added_count INTEGER NOT NULL DEFAULT 0, modified_count INTEGER NOT NULL DEFAULT 0,
            removed_count INTEGER NOT NULL DEFAULT 0, created_at DATETIME
        )"""))
    initialize_schema(engine)
    with engine.connect() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(plaid_items)"))}
        tables = {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
    assert {"imported_count", "duplicate_count"} <= columns
    assert "plaid_transaction_identities" in tables
    engine.dispose()


def test_item_list_is_filtered_to_requested_environment():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with session_scope() as session:
        session.add_all([
            PlaidItem(item_id="sandbox-item", environment="sandbox", institution_name="Test Bank"),
            PlaidItem(item_id="prod-item", environment="production", institution_name="Live Bank"),
        ])
    with patch("backend.routes.plaid.get_session", session_scope):
        client = TestClient(app)
        assert [row["item_id"] for row in client.get("/plaid/items", params={"environment": "sandbox"}).json()] == ["sandbox-item"]
        assert [row["item_id"] for row in client.get("/plaid/items", params={"environment": "production"}).json()] == ["prod-item"]
        assert client.get("/plaid/items", params={"environment": "invalid"}).status_code == 422
    engine.dispose()


def test_production_sync_imports_posted_rows_and_persists_cursor_atomically():
    from backend.routes import plaid
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with session_scope() as session:
        session.add(PlaidItem(item_id="prod-item", environment="production", institution_name="Chase",
            accounts_json=json.dumps([{"account_id": "acct", "name": "Freedom", "mask": "1234"}]),
            last_sync_status="not_synced"))

    class Client:
        def sync_page(self, access_token, cursor):
            if cursor is None:
                return {"added": [], "modified": [], "removed": [],
                        "next_cursor": "page-one", "has_more": True}
            return {"added": [{"transaction_id": "txn-1", "account_id": "acct", "date": "2026-10-01",
                    "amount": 19.5, "name": "Grocery Store", "merchant_name": "Grocery Store", "pending": False}],
                    "modified": [], "removed": [], "next_cursor": "next-cursor", "has_more": False}

    with patch("backend.routes.plaid.get_session", session_scope), \
         patch.object(plaid, "_client", return_value=Client()), \
         patch.object(plaid.credentials_store, "get_bank_credential", return_value="access"), \
         patch.object(plaid, "reconcile_subscriptions"), \
         patch.object(plaid, "invalidate_derived_data"), \
         patch("backend.jobs.enrichment.enqueue_transactions", return_value="enrich-job"):
        result = plaid.sync_item("prod-item", BackgroundTasks(), "production")
        repeated = plaid.sync_item("prod-item", BackgroundTasks(), "production")

    with Session(engine) as session:
        row = session.get(Transaction, "plaid:production:txn-1")
        item = session.get(PlaidItem, "prod-item")
        assert row is not None and row.source == "chase" and row.amount == 19.5
        assert item.cursor == "next-cursor" and item.imported_count == 1
        assert result["transaction_counts"]["imported"] == 1
        assert result["enrichment_job_id"] == "enrich-job"
        assert repeated["transaction_counts"]["imported"] == 0
        assert repeated["enrichment_job_id"] is None
        assert session.query(Transaction).count() == 1
    engine.dispose()


def test_failed_paginated_sync_rolls_back_partial_transactions_and_cursor():
    from backend.routes import plaid
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    with session_scope() as session:
        session.add(PlaidItem(item_id="prod-item", environment="production", institution_name="Chase",
            cursor="old-cursor", accounts_json=json.dumps([{"account_id": "acct", "name": "Freedom"}])))

    calls = []

    class Client:
        def sync_page(self, access_token, cursor):
            calls.append(cursor)
            if cursor in ("old-cursor", None):
                return {"added": [{"transaction_id": "partial", "account_id": "acct", "date": "2026-10-01",
                        "amount": 19.5, "name": "Grocery Store", "pending": False}],
                        "modified": [], "removed": [], "next_cursor": "page-one", "has_more": True}
            raise PlaidAPIError("TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION")

    with patch("backend.routes.plaid.get_session", session_scope), \
         patch.object(plaid, "_client", return_value=Client()), \
         patch.object(plaid.credentials_store, "get_bank_credential", return_value="access"):
        with pytest.raises(HTTPException) as err:
            plaid.sync_item("prod-item", BackgroundTasks(), "production")
    assert err.value.status_code == 502
    assert calls == ["old-cursor", "page-one", "old-cursor", "page-one", "old-cursor", "page-one"]
    with Session(engine) as session:
        assert session.get(Transaction, "plaid:production:partial") is None
        assert session.get(PlaidItem, "prod-item").cursor == "old-cursor"
    engine.dispose()


def test_production_sync_rejects_sandbox_item():
    from backend.routes import plaid
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with session_scope() as session:
        session.add(PlaidItem(item_id="sandbox-item", environment="sandbox", institution_name="Test Bank"))
    with patch("backend.routes.plaid.get_session", session_scope), patch.object(plaid, "_client"):
        result = TestClient(app).post("/plaid/items/sandbox-item/sync", params={"environment": "production"})
    assert result.status_code == 404
    engine.dispose()


def test_sandbox_sync_still_discards_synthetic_transaction_rows():
    from backend.routes import plaid
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with session_scope() as session:
        session.add(PlaidItem(item_id="sandbox-item", environment="sandbox", institution_name="Test Bank",
            accounts_json=json.dumps([{"account_id": "acct", "name": "Test account"}])))

    class Client:
        def sync_page(self, access_token, cursor):
            return {"added": [{"transaction_id": "synthetic", "account_id": "acct", "date": "2026-10-01",
                    "amount": 42, "name": "Synthetic Purchase"}], "modified": [], "removed": [],
                    "next_cursor": "sandbox-cursor", "has_more": False}

    with patch("backend.routes.plaid.get_session", session_scope), \
         patch.object(plaid, "_client", return_value=Client()), \
         patch.object(plaid.credentials_store, "get_bank_credential", return_value="sandbox-access"):
        response = plaid.sync_item("sandbox-item", BackgroundTasks(), "sandbox")
    with Session(engine) as session:
        assert session.get(Transaction, "synthetic") is None
        assert session.get(PlaidItem, "sandbox-item").cursor == "sandbox-cursor"
    assert response["transaction_counts"]["imported"] == 0
    engine.dispose()
