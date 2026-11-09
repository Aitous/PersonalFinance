from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.analysis.plaid_ingestion import apply_transaction_deltas
from backend.db.models import Account, Base, PlaidTransactionIdentity, Transaction


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def plaid_row(transaction_id="p-1", **updates):
    row = {
        "transaction_id": transaction_id, "account_id": "acct-1", "date": "2026-10-01",
        "amount": 12.5, "name": "TRADER JOE S #123", "merchant_name": "Trader Joe's",
        "pending": False,
    }
    row.update(updates)
    return row


def apply(session, **changes):
    args = {
        "environment": "production", "item_id": "item-1", "institution_name": "Chase",
        "accounts": [{"account_id": "acct-1", "name": "Freedom", "mask": "1234"}],
        "added": [], "modified": [], "removed": [],
    }
    args.update(changes)
    return apply_transaction_deltas(session, **args)


def test_added_transaction_is_imported_once_and_pending_is_ignored():
    engine, session = make_session()
    try:
        result = apply(session, added=[plaid_row(pending=True), plaid_row()])
        session.flush()
        assert result["imported"] == 1
        assert result["new_transaction_ids"] == ["plaid:production:p-1"]
        assert session.get(Transaction, "plaid:production:p-1").amount == 12.5
        assert session.scalars(select(Account)).first().last4 == "1234"
        repeated = apply(session, added=[plaid_row()])
        assert repeated["imported"] == 0
        assert session.query(Transaction).count() == 1
    finally:
        session.close()
        engine.dispose()


def test_unique_csv_overlap_is_mapped_and_removed_without_deleting_csv_row():
    engine, session = make_session()
    try:
        csv_tx = Transaction(id="csv-1", source="chase", date=date(2026, 10, 1),
                             description="TRADER JOE S", amount=12.5, category="groceries")
        session.add(csv_tx)
        session.flush()
        result = apply(session, added=[plaid_row()])
        session.flush()
        identity = session.get(PlaidTransactionIdentity, ("local-owner", "production", "p-1"))
        assert result["duplicates"] == 1
        assert identity.transaction_id == "csv-1" and identity.plaid_owned is False
        removed = apply(session, removed=[{"transaction_id": "p-1"}])
        session.flush()
        assert removed["removed"] == 0
        assert session.get(Transaction, "csv-1") is csv_tx
        assert session.get(PlaidTransactionIdentity, ("local-owner", "production", "p-1")) is None
    finally:
        session.close()
        engine.dispose()


def test_ambiguous_csv_overlap_is_not_silently_dropped():
    engine, session = make_session()
    try:
        for identifier in ("csv-1", "csv-2"):
            session.add(Transaction(id=identifier, source="chase", date=date(2026, 10, 1),
                description="TRADER JOE S", amount=12.5))
        session.flush()
        result = apply(session, added=[plaid_row()])
        session.flush()
        assert result["duplicates"] == 0 and result["imported"] == 1
        assert session.get(Transaction, "plaid:production:p-1") is not None
    finally:
        session.close()
        engine.dispose()


def test_assigned_csv_row_on_different_card_is_not_matched():
    engine, session = make_session()
    try:
        session.add(Account(id="other-card", bank="chase", name="Other card", last4="9999"))
        session.add(Transaction(id="csv-1", source="chase", date=date(2026, 10, 1),
            description="TRADER JOE S", amount=12.5, account_id="other-card"))
        session.flush()
        result = apply(session, added=[plaid_row()])
        session.flush()
        assert result["duplicates"] == 0 and result["imported"] == 1
        assert session.get(Transaction, "csv-1") is not None
        assert session.get(Transaction, "plaid:production:p-1") is not None
    finally:
        session.close()
        engine.dispose()


def test_modification_preserves_manual_fields_and_removal_keeps_edited_row():
    engine, session = make_session()
    try:
        tx = Transaction(id="plaid:production:p-1", source="chase", date=date(2026, 10, 1),
            description="Original", amount=12.5, category="dining", merchant_name="My Merchant",
            manual_category=True, manual_fields='["merchant_name"]')
        session.add(tx)
        session.add(PlaidTransactionIdentity(environment="production", plaid_transaction_id="p-1",
            item_id="item-1", transaction_id=tx.id, plaid_owned=True))
        session.flush()
        result = apply(session, modified=[plaid_row(name="Updated", amount=14.0)],
                       removed=[{"transaction_id": "p-1"}])
        session.flush()
        assert result["modified"] == 1 and result["removed"] == 0
        assert tx.amount == 14 and tx.category == "dining" and tx.merchant_name == "My Merchant"
        assert session.get(Transaction, tx.id) is tx
        assert session.get(PlaidTransactionIdentity, ("local-owner", "production", "p-1")) is None
    finally:
        session.close()
        engine.dispose()
