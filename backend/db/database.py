from pathlib import Path
from contextlib import contextmanager
from sqlalchemy import create_engine, text, update, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker
from backend.db.models import Base, DataRevision

DB_PATH = Path(__file__).parent.parent.parent / "finance.db"
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)

def initialize_schema(target_engine):
    """Create current tables and apply additive SQLite migrations idempotently."""
    Base.metadata.create_all(target_engine)
    # create_all intentionally does not alter existing SQLite tables. Keep this
    # migration additive so an existing finance.db retains every public ID/row.
    with target_engine.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(transactions)"))}
        additions = {
            "account_id": "VARCHAR", "original_amount": "FLOAT", "amount_minor": "INTEGER",
            "currency": "VARCHAR(3)", "bank_fitid": "VARCHAR", "manual_category": "BOOLEAN NOT NULL DEFAULT 0",
            "kind": "VARCHAR",
            "enrichment_status": "VARCHAR", "enrichment_input_hash": "VARCHAR",
            "embedding_input_hash": "VARCHAR", "embedding_model_version": "VARCHAR",
            "manual_fields": "TEXT", "raw_enrichment": "TEXT",
        }
        for name, sql_type in additions.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE transactions ADD COLUMN {name} {sql_type}"))
        sub_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(subscriptions)"))}
        for name, sql_type in {"origin": "VARCHAR NOT NULL DEFAULT 'legacy'", "dismissed": "BOOLEAN NOT NULL DEFAULT 0", "user_active": "BOOLEAN", "supporting_transaction_ids": "TEXT"}.items():
            if name not in sub_columns:
                conn.execute(text(f"ALTER TABLE subscriptions ADD COLUMN {name} {sql_type}"))
        cache_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(monthly_report_cache)"))}
        if "data_revision" not in cache_columns:
            conn.execute(text("ALTER TABLE monthly_report_cache ADD COLUMN data_revision INTEGER NOT NULL DEFAULT -1"))
        for table, additions in {
            "enrichment_jobs": {"mode": "VARCHAR NOT NULL DEFAULT 'enrich'"},
            "accounts": {"external_id": "VARCHAR"},
            "import_batches": {"from_date": "DATE", "to_date": "DATE"},
            "imported_rows": {"raw_data": "TEXT", "status": "VARCHAR NOT NULL DEFAULT 'accepted'"},
        }.items():
            table_columns = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, sql_type in additions.items():
                if name not in table_columns:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_enrichment_job_items_job_status ON enrichment_job_items(job_id, status)"))
        for statement in (
            "CREATE INDEX IF NOT EXISTS ix_transactions_account_date ON transactions(account_id, date)",
            "CREATE INDEX IF NOT EXISTS ix_transactions_source_date ON transactions(source, date)",
            "CREATE INDEX IF NOT EXISTS ix_transactions_category_date ON transactions(category, date)",
            "CREATE INDEX IF NOT EXISTS ix_transactions_bank_fitid ON transactions(bank_fitid)",
        ):
            conn.execute(text(statement))


def init_db():
    initialize_schema(engine)


def invalidate_derived_data(session: Session) -> int:
    """Increment the global data revision after a source or user-data mutation."""
    session.execute(sqlite_insert(DataRevision).values(id=1, revision=0).on_conflict_do_nothing(index_elements=[DataRevision.id]))
    session.execute(update(DataRevision).where(DataRevision.id == 1).values(revision=DataRevision.revision + 1))
    session.expire_all()
    return session.execute(select(DataRevision.revision).where(DataRevision.id == 1)).scalar_one()


def get_data_revision(session: Session) -> int:
    """Return the current global data revision (zero before the first change)."""
    row = session.get(DataRevision, 1)
    return row.revision if row else 0

@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
