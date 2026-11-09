from pathlib import Path
from contextlib import contextmanager
import os
from sqlalchemy import create_engine, inspect, text, select
from sqlalchemy.orm import Session, sessionmaker
from backend.db.models import Base, DataRevision, OwnerScoped

DB_PATH = Path(__file__).parent.parent.parent / "finance.db"
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix("postgres://")
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix("postgresql://")
    # Hosted PostgreSQL uses a bounded pool; local SQLite remains the default.
    engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True, pool_size=5, max_overflow=5)
else:
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)

def initialize_schema(target_engine):
    """Create tables and apply additive migrations for SQLite or PostgreSQL."""
    Base.metadata.create_all(target_engine)
    inspector = inspect(target_engine)
    tables = set(inspector.get_table_names())
    tenant_tables = {
        mapper.local_table.name for mapper in Base.registry.mappers
        if issubclass(mapper.class_, OwnerScoped)
    }
    with target_engine.begin() as conn:
        for table in tenant_tables.intersection(tables):
            columns = {col["name"] for col in inspect(conn).get_columns(table)}
            if "owner_id" not in columns:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN owner_id VARCHAR(128)'))
            # Old single-user rows are retained under the local owner. Hosted
            # migration can later remap this owner to the first Supabase user.
            conn.execute(text(f'UPDATE "{table}" SET owner_id = :owner WHERE owner_id IS NULL'), {"owner": "local-owner"})
        if "plaid_items" in tables:
            plaid_columns = {col["name"] for col in inspect(conn).get_columns("plaid_items")}
            if "access_token_encrypted" not in plaid_columns:
                conn.execute(text("ALTER TABLE plaid_items ADD COLUMN access_token_encrypted TEXT"))
    # Derived caches may be discarded when moving from the old global key to
    # account-scoped keys. Preserve the ledger and rebuild only those tables.
    for table_name in ("monthly_report_cache", "monthly_category_explanation_cache"):
        if table_name in tables:
            primary_key = inspect(target_engine).get_pk_constraint(table_name).get("constrained_columns") or []
            if "owner_id" not in primary_key:
                Base.metadata.tables[table_name].drop(target_engine, checkfirst=True)
                Base.metadata.tables[table_name].create(target_engine, checkfirst=True)
    tables = set(inspect(target_engine).get_table_names())
    with target_engine.begin() as conn:
        for table in tenant_tables.intersection(tables):
            conn.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{table}_owner_id ON "{table}" (owner_id)'))
        if target_engine.dialect.name == "postgresql":
            role = conn.execute(text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")).scalar_one()
            if role:
                raise RuntimeError("DATABASE_URL must use a PostgreSQL role with BYPASSRLS disabled")
            for table in tenant_tables.intersection(tables):
                conn.execute(text(f'ALTER TABLE "{table}" ALTER COLUMN owner_id SET NOT NULL'))
                conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
                conn.execute(text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
                policy_name = f"{table}_owner_isolation"
                conn.execute(text(f'DROP POLICY IF EXISTS "{policy_name}" ON "{table}"'))
                conn.execute(text(
                    f'CREATE POLICY "{policy_name}" ON "{table}" '
                    "USING (owner_id = nullif(current_setting('app.user_id', true), '')) "
                    "WITH CHECK (owner_id = nullif(current_setting('app.user_id', true), ''))"
                ))
            if "llm_platform_usage" in tables:
                conn.execute(text("REVOKE ALL ON TABLE llm_platform_usage FROM PUBLIC, anon, authenticated"))
            if "account_deletions" in tables:
                conn.execute(text("REVOKE ALL ON TABLE account_deletions FROM PUBLIC, anon, authenticated"))
    if target_engine.dialect.name != "sqlite":
        return
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
        if "prompt_version" not in cache_columns:
            conn.execute(text("ALTER TABLE monthly_report_cache ADD COLUMN prompt_version INTEGER NOT NULL DEFAULT 1"))
        for table, additions in {
            "enrichment_jobs": {"mode": "VARCHAR NOT NULL DEFAULT 'enrich'"},
            "accounts": {"external_id": "VARCHAR"},
            "plaid_items": {"imported_count": "INTEGER NOT NULL DEFAULT 0", "duplicate_count": "INTEGER NOT NULL DEFAULT 0"},
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
    """Increment the current owner's derived-data revision."""
    row = session.execute(select(DataRevision).order_by(DataRevision.id).limit(1)).scalar_one_or_none()
    if row is None:
        row = DataRevision(revision=0)
        session.add(row)
        session.flush()
    row.revision += 1
    session.flush()
    revision = row.revision
    session.expire_all()
    return revision


def get_data_revision(session: Session) -> int:
    """Return the current owner's data revision (zero before the first change)."""
    row = session.execute(select(DataRevision).order_by(DataRevision.id).limit(1)).scalar_one_or_none()
    return row.revision if row else 0

@contextmanager
def get_session():
    session = SessionLocal()
    try:
        if session.bind and session.bind.dialect.name == "postgresql":
            from backend.auth import current_owner_id
            session.execute(text("SELECT set_config('app.user_id', :owner_id, true)"), {"owner_id": current_owner_id()})
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
