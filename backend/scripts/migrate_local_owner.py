"""Copy the local SQLite ledger into an empty Supabase PostgreSQL project.

Run once after inviting the owner and initializing the hosted API schema:
  DATABASE_URL=... .venv/bin/python -m backend.scripts.migrate_local_owner --owner-id <auth-user-uuid>
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3

from sqlalchemy import create_engine, inspect, select, text

from backend.db.database import DB_PATH, initialize_schema
from backend.db.models import Base, OwnerScoped

SKIP_TABLES = {"monthly_report_cache", "monthly_category_explanation_cache", "plaid_items",
               "plaid_transaction_identities", "llm_platform_usage"}
AUTOINCREMENT_IDS = {"imported_rows", "enrichment_job_items", "merchant_aliases",
                     "category_rules", "syncs", "data_revision"}


def migrate(owner_id: str, source_path: Path, target_url: str) -> dict:
    if not target_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError("DATABASE_URL must point to hosted PostgreSQL")
    if not owner_id.strip():
        raise ValueError("owner_id is required")
    if target_url.startswith("postgres://"):
        target_url = "postgresql+psycopg://" + target_url.removeprefix("postgres://")
    elif target_url.startswith("postgresql://"):
        target_url = "postgresql+psycopg://" + target_url.removeprefix("postgresql://")
    backup_path = source_path.with_name(f"{source_path.name}.pre-hosted-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.bak")
    with sqlite3.connect(source_path) as source_db, sqlite3.connect(backup_path) as backup_db:
        source_db.backup(backup_db)

    source = create_engine(f"sqlite:///{source_path}")
    target = create_engine(target_url, pool_pre_ping=True)
    initialize_schema(source)
    initialize_schema(target)
    tables = {mapper.local_table.name for mapper in Base.registry.mappers if issubclass(mapper.class_, OwnerScoped)}
    counts = {}
    with source.connect() as source_conn, target.begin() as target_conn:
        target_conn.execute(text("SELECT set_config('app.user_id', :owner, true)"), {"owner": owner_id})
        for table_name in sorted(tables - SKIP_TABLES):
            table = Base.metadata.tables[table_name]
            existing = target_conn.execute(select(table.c.owner_id).where(table.c.owner_id == owner_id).limit(1)).first()
            if existing:
                raise RuntimeError(f"Target already has rows for this owner (table {table_name}); refusing to mix migrations")

        source_tables = set(inspect(source_conn).get_table_names())
        transaction_ids: dict[str, str] = {}
        if "transactions" in source_tables:
            transaction_table = Base.metadata.tables["transactions"]
            for row in source_conn.execute(select(transaction_table)).mappings():
                old_id = str(row["id"])
                transaction_ids[old_id] = old_id if old_id.startswith(owner_id + ":") else f"{owner_id}:{old_id}"

        for table_name in sorted(tables - SKIP_TABLES):
            if table_name not in source_tables:
                continue
            table = Base.metadata.tables[table_name]
            source_columns = {col["name"] for col in inspect(source_conn).get_columns(table_name)}
            rows = source_conn.execute(select(table)).mappings().all()
            inserted = 0
            for source_row in rows:
                value = {key: source_row[key] for key in source_columns.intersection(table.c.keys())}
                value["owner_id"] = owner_id
                if table_name == "transactions":
                    value["id"] = transaction_ids[str(value["id"])]
                elif table_name == "subscriptions" and value.get("id"):
                    value["id"] = f"{owner_id}:{value['id']}"
                    try:
                        old_ids = json.loads(value.get("supporting_transaction_ids") or "[]")
                        value["supporting_transaction_ids"] = json.dumps([transaction_ids.get(str(tx_id), f"{owner_id}:{tx_id}") for tx_id in old_ids])
                    except (TypeError, json.JSONDecodeError):
                        value["supporting_transaction_ids"] = "[]"
                if "transaction_id" in value and value["transaction_id"]:
                    value["transaction_id"] = transaction_ids.get(str(value["transaction_id"]), f"{owner_id}:{value['transaction_id']}")
                if table_name in AUTOINCREMENT_IDS:
                    value.pop("id", None)
                target_conn.execute(table.insert().values(**value))
                inserted += 1
            counts[table_name] = inserted
    target.dispose()
    source.dispose()
    return {"backup": str(backup_path), "rows_copied": counts,
            "plaid": "Plaid Items and access tokens were intentionally omitted; reconnect banks in the hosted app."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", required=True, help="Supabase Auth user UUID for the invited owner")
    parser.add_argument("--source", type=Path, default=DB_PATH)
    parser.add_argument("--database-url", default=None, help="Defaults to DATABASE_URL")
    args = parser.parse_args()
    import os
    url = args.database_url or os.getenv("DATABASE_URL")
    if not url:
        parser.error("set DATABASE_URL or pass --database-url")
    print(json.dumps(migrate(args.owner_id, args.source, url), indent=2))


if __name__ == "__main__":
    main()
