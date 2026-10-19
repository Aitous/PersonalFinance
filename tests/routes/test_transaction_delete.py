from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.database import get_data_revision
from backend.db.models import Base, ImportedRow, Transaction
from backend.main import app


def test_delete_removes_transaction_but_preserves_import_audit_and_revises_data():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with session_scope() as session:
        session.add(Transaction(id="tx-1", source="chase", date=date(2026, 1, 5),
            description="COFFEE SHOP", amount=8.25, category="dining"))
        session.add(ImportedRow(batch_id="batch-1", transaction_id="tx-1", row_number=2,
            row_hash="source-row-hash", raw_data="01/05/2026,COFFEE SHOP,8.25"))

    with patch("backend.routes.transactions.get_session", session_scope):
        client = TestClient(app)
        response = client.delete("/transactions/tx-1")
        missing = client.delete("/transactions/tx-1")

    assert response.status_code == 200
    assert response.json() == {"deleted": "tx-1"}
    assert missing.status_code == 404
    with session_scope() as session:
        assert session.get(Transaction, "tx-1") is None
        audit = session.execute(select(ImportedRow).where(ImportedRow.batch_id == "batch-1")).scalar_one()
        assert audit.transaction_id is None
        assert audit.status == "deleted"
        assert audit.reason == "Transaction deleted by user"
        assert get_data_revision(session) == 1

    engine.dispose()
