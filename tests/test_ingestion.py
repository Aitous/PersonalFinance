import json
import asyncio
from contextlib import contextmanager
from datetime import date
from io import BytesIO

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import Session

from backend.db.database import initialize_schema, get_data_revision, invalidate_derived_data
from backend.db.models import Account, Base, ImportBatch, ImportedRow, Transaction
from backend.ingestion import reconcile_account_overlaps, reconcile_legacy_csv_ids, reconcile_unassigned_description_overlaps
from backend.parsers.csv_parser import parse_csv, parse_csv_detailed, _make_id


def _write_csv(tmp_path, contents):
    path = tmp_path / "sample.csv"
    path.write_text(contents)
    return path


def test_csv_validation_reports_bad_rows_and_rejects_wholly_invalid(tmp_path):
    path = _write_csv(tmp_path, "Transaction Date,Description,Category,Type,Amount,Memo\n"
        "05/14/2025,STORE,Shopping,Sale,-12.00,\n"
        "bad-date,STORE,Shopping,Sale,-12.00,\n")
    result = parse_csv_detailed(path, "chase")
    assert result.input_rows == 2
    assert result.parsed_rows == 1
    assert result.errors[0]["row_number"] == 3
    assert "raw_data" in result.errors[0]
    invalid = _write_csv(tmp_path, "Transaction Date,Description,Category,Type,Amount,Memo\n"
        "not-a-date,STORE,Shopping,Sale,nope,\n")
    with pytest.raises(ValueError, match="no valid transaction"):
        parse_csv(invalid, "chase")
    wrong_bank = _write_csv(tmp_path, "Date,Description,Amount\n05/14/2025,STORE,12\n")
    with pytest.raises(ValueError, match="Invalid chase CSV headers"):
        parse_csv(wrong_bank, "chase")


def test_same_day_repeats_and_accounts_get_distinct_stable_ids(tmp_path):
    path = _write_csv(tmp_path, "Transaction Date,Description,Category,Type,Amount,Memo\n"
        "05/14/2025,STORE,Shopping,Sale,-12.00,\n"
        "05/14/2025,STORE,Shopping,Sale,-12.00,\n")
    first = parse_csv(path, "chase", "card-a")
    repeated_parse = parse_csv(path, "chase", "card-a")
    other_card = parse_csv(path, "chase", "card-b")
    assert len({t.id for t in first}) == 2
    assert [t.id for t in first] == [t.id for t in repeated_parse]
    assert {t.id for t in first}.isdisjoint({t.id for t in other_card})
    assert all(t.amount == 12 and t.original_amount == -12 for t in first)


def test_csv_bank_signs_and_credit_kind_are_preserved(tmp_path):
    discover = _write_csv(tmp_path, "Trans. Date,Description,Amount,Category\n"
        "05/14/2025,STORE,12.00,Restaurants\n05/14/2025,STORE REFUND,-2.00,Refund\n")
    txs = parse_csv(discover, "discover")
    assert (txs[0].amount, txs[0].original_amount, txs[0].kind) == (12, 12, "purchase")
    assert (txs[1].amount, txs[1].original_amount, txs[1].kind) == (-2, -2, "refund")


def test_account_overlap_reconciles_occurrences_without_guessing_legacy_rows():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Transaction(id="existing-1", source="chase", date=date(2025, 1, 1), description="STORE", amount=12, account_id="card-a"),
            Transaction(id="legacy", source="chase", date=date(2025, 1, 1), description="STORE", amount=12),
        ])
        session.flush()
        incoming = [
            Transaction(id="csv-row-1", source="chase", date=date(2025, 1, 1), description="store", amount=12, account_id="card-a"),
            Transaction(id="csv-row-2", source="chase", date=date(2025, 1, 1), description="STORE", amount=12, account_id="card-a"),
        ]
        remapped = reconcile_account_overlaps(session, incoming)
        assert incoming[0].id == "existing-1"
        assert incoming[1].id == "csv-row-2"
        assert remapped == {"csv-row-1": "existing-1"}
    engine.dispose()


def test_unassigned_overlap_matches_truncated_bank_descriptions_once():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Transaction(id="old", source="discover", date=date(2026, 5, 16),
            description="GOOGLE *GOOGLE ONE G.CO/HELPPAY#CAP1LCZNLG", amount=1.99))
        session.flush()
        incoming = [
            Transaction(id="new-1", source="discover", date=date(2026, 5, 16),
                description="GOOGLE *GOOGLE ONE", amount=1.99),
            Transaction(id="new-2", source="discover", date=date(2026, 5, 16),
                description="GOOGLE *GOOGLE ONE", amount=1.99),
        ]

        remapped = reconcile_unassigned_description_overlaps(session, incoming)

        assert remapped == {"new-1": "old"}
        assert [tx.id for tx in incoming] == ["old", "new-2"]
    engine.dispose()


def test_overlap_does_not_collapse_distinct_fitids_and_reserves_exact_ids_first():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Transaction(id="fit-a", source="chase", date=date(2025, 1, 1), description="STORE", amount=10,
            account_id="card-a", bank_fitid="A"))
        session.flush()
        incoming = [
            Transaction(id="fit-b", source="chase", date=date(2025, 1, 1), description="STORE", amount=10,
                account_id="card-a", bank_fitid="B"),
            Transaction(id="fit-a", source="chase", date=date(2025, 1, 1), description="STORE", amount=10,
                account_id="card-a", bank_fitid="A"),
        ]
        assert reconcile_account_overlaps(session, incoming) == {}
        assert [t.id for t in incoming] == ["fit-b", "fit-a"]
    engine.dispose()


def test_csv_overlap_matches_ofx_fitid_occurrence_without_collapsing_additional_charge():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Transaction(id="ofx-1", source="chase", date=date(2025, 1, 1), description="STORE", amount=10,
            account_id="card-a", bank_fitid="A"))
        session.flush()
        incoming = [
            Transaction(id="csv-first", source="chase", date=date(2025, 1, 1), description="STORE", amount=10, account_id="card-a"),
            Transaction(id="csv-second", source="chase", date=date(2025, 1, 1), description="STORE", amount=10, account_id="card-a"),
        ]
        assert reconcile_account_overlaps(session, incoming) == {"csv-first": "ofx-1"}
        assert [t.id for t in incoming] == ["ofx-1", "csv-second"]
    engine.dispose()


def test_additive_migration_is_repeatable_and_preserves_legacy_rows(tmp_path):
    db_path = tmp_path / "legacy.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE transactions (id VARCHAR PRIMARY KEY, source VARCHAR NOT NULL, date DATE NOT NULL, description VARCHAR NOT NULL, amount FLOAT NOT NULL, category VARCHAR, merchant_name VARCHAR, city VARCHAR, is_online BOOLEAN, merchant_type VARCHAR, is_subscription BOOLEAN, metadata TEXT, raw_csv_row TEXT, embedding TEXT)"))
        conn.execute(text("INSERT INTO transactions(id, source, date, description, amount) VALUES ('old-id', 'chase', '2025-01-02', 'STORE', 12.34)"))
        conn.execute(text("CREATE TABLE subscriptions (id VARCHAR PRIMARY KEY, description VARCHAR NOT NULL, amount FLOAT NOT NULL, frequency VARCHAR NOT NULL, last_charged DATE, active BOOLEAN)"))
        conn.execute(text("CREATE TABLE monthly_report_cache (year INTEGER, month INTEGER, narrative TEXT NOT NULL, created_at DATETIME NOT NULL, PRIMARY KEY(year, month))"))
    initialize_schema(engine)
    initialize_schema(engine)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, amount, manual_category FROM transactions")).one()
        assert tuple(row) == ("old-id", 12.34, 0)
        columns = {r[1] for r in conn.execute(text("PRAGMA table_info(transactions)"))}
        assert {"account_id", "kind", "embedding_input_hash", "manual_category"} <= columns
        indexes = {r[1] for r in conn.execute(text("PRAGMA index_list(transactions)"))}
        assert "ix_transactions_account_date" in indexes
    engine.dispose()


def test_data_revision_increments_and_is_readable():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert get_data_revision(session) == 0
        assert invalidate_derived_data(session) == 1
        assert invalidate_derived_data(session) == 2
        session.commit()
    with Session(engine) as session:
        assert get_data_revision(session) == 2
    engine.dispose()


def test_upload_persists_rows_and_provenance_without_llm(tmp_path, monkeypatch):
    from starlette.datastructures import UploadFile
    from backend.routes import import_csv as import_route

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    account_id = "card-a"
    with Session(engine) as session:
        session.add(Account(id=account_id, bank="chase", name="Personal", last4="1234"))
        session.commit()

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    monkeypatch.setattr(import_route, "get_session", session_scope)
    monkeypatch.setattr(import_route, "TRANSACTIONS_DIR", tmp_path / "transactions")
    monkeypatch.setattr(import_route, "PROCESSED_DIR", tmp_path / "processed")
    file = UploadFile(filename="statement.csv", file=BytesIO(
        b"Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
        b"05/14/2025,05/15/2025,STORE,Shopping,Sale,-12.00,\n"))
    result = asyncio.run(import_route.upload_csv(background_tasks=BackgroundTasks(), bank="chase", account_id=account_id, file=file))
    assert result["new_transactions"] == 1
    with Session(engine) as session:
        assert len(session.execute(select(Transaction)).scalars().all()) == 1
        batch = session.execute(select(ImportBatch)).scalar_one()
        imported = session.execute(select(ImportedRow)).scalar_one()
        assert batch.new_count == 1 and batch.checksum
        assert imported.status == "accepted" and "STORE" in imported.raw_data
    engine.dispose()


def test_preview_and_upload_remap_sign_era_legacy_duplicate_and_keep_repeat(tmp_path, monkeypatch):
    from starlette.datastructures import UploadFile
    from backend.routes import import_csv as import_route

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    raw = {
        "Transaction Date": "05/14/2025", "Post Date": "05/15/2025", "Description": "STORE",
        "Category": "Shopping", "Type": "Sale", "Amount": "-12.00", "Memo": "",
    }
    legacy_id = _make_id("chase", date(2025, 5, 14), "STORE", -12.0)
    with Session(engine) as session:
        session.add(Transaction(id=legacy_id, source="chase", date=date(2025, 5, 14),
            description="STORE", amount=12.0, raw_csv_row=json.dumps(raw)))
        session.commit()

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    monkeypatch.setattr(import_route, "get_session", session_scope)
    monkeypatch.setattr(import_route, "TRANSACTIONS_DIR", tmp_path / "transactions")
    monkeypatch.setattr(import_route, "PROCESSED_DIR", tmp_path / "processed")
    content = (
        b"Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
        b"05/14/2025,05/15/2025,STORE,Shopping,Sale,-12.00,\n"
        b"05/14/2025,05/15/2025,STORE,Shopping,Sale,-12.00,\n"
    )
    _, preview, _ = import_route._preview_payload("chase", None, "statement.csv", content)
    assert preview["duplicate_rows"] == 1
    assert preview["new_transactions"] == 1

    file = UploadFile(filename="statement.csv", file=BytesIO(content))
    result = asyncio.run(import_route.upload_csv(background_tasks=BackgroundTasks(), bank="chase", account_id=None, file=file))
    assert result["duplicate_rows"] == 1
    assert result["new_transactions"] == 1
    with Session(engine) as session:
        assert session.get(Transaction, legacy_id) is not None
        assert len(session.execute(select(Transaction)).scalars().all()) == 2
        rows = session.execute(select(ImportedRow).order_by(ImportedRow.row_number)).scalars().all()
        assert len(rows) == 2
        assert rows[0].transaction_id == legacy_id
        assert rows[0].status == "duplicate"
        assert rows[1].status == "accepted"
        assert rows[1].transaction_id != legacy_id
    engine.dispose()


@pytest.mark.parametrize("raw_data", ["not-json", "{bad json"])
def test_legacy_reconciliation_skips_malformed_raw_without_crashing(raw_data):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        incoming = Transaction(id=_make_id("chase", date(2025, 1, 1), "STORE", 12), source="chase", date=date(2025, 1, 1),
            description="STORE", amount=12, raw_csv_row=json.dumps({"Description": "STORE"}))
        session.add(Transaction(id=_make_id("chase", date(2025, 1, 1), "STORE", -12), source="chase",
            date=date(2025, 1, 1), description="STORE", amount=12, raw_csv_row=raw_data))
        session.flush()
        assert reconcile_legacy_csv_ids(session, [incoming]) == {}
        assert incoming.id == _make_id("chase", date(2025, 1, 1), "STORE", 12)
    engine.dispose()


def test_legacy_reconciliation_never_remaps_opposite_sign_refund_or_assigned_account():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        day = date(2025, 1, 1)
        raw = json.dumps({"Description": "STORE", "Amount": "-12"})
        legacy_id = _make_id("chase", day, "STORE", -12)
        session.add(Transaction(id=legacy_id, source="chase", date=day, description="STORE", amount=-12, raw_csv_row=raw))
        session.flush()
        incoming_refund = Transaction(id=_make_id("chase", day, "STORE", 12), source="chase", date=day,
            description="STORE", amount=12, raw_csv_row=raw)
        incoming_assigned = Transaction(id="assigned-row", source="chase", date=day,
            description="STORE", amount=12, account_id="card-a", raw_csv_row=raw)
        assert reconcile_legacy_csv_ids(session, [incoming_refund, incoming_assigned]) == {}
        assert incoming_refund.id != legacy_id
        assert incoming_assigned.id == "assigned-row"
    engine.dispose()
