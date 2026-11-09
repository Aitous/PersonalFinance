from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.credentials import credentials_store
from backend.db.database import get_session, invalidate_derived_data
from backend.db.models import PlaidItem, Transaction
from backend.auth import current_owner_id, hosted_auth_enabled
from backend.security import decrypt_secret, encrypt_secret
from backend.analysis.plaid_ingestion import apply_transaction_deltas
from backend.analysis.recurring import reconcile_subscriptions
from backend.plaid_client import PlaidAPIError, PlaidClient, PlaidEnvironment


router = APIRouter(prefix="/plaid", tags=["plaid"])
class PlaidCredentials(BaseModel):
    client_id: str = Field(min_length=1, max_length=300)
    secret: str = Field(min_length=1, max_length=500)


class PublicTokenRequest(BaseModel):
    public_token: str = Field(min_length=1, max_length=2000)


def _client(environment: PlaidEnvironment = "sandbox") -> PlaidClient:
    if hosted_auth_enabled():
        prefix = "PLAID_PRODUCTION" if environment == "production" else "PLAID_SANDBOX"
        client_id, secret = os.getenv(f"{prefix}_CLIENT_ID"), os.getenv(f"{prefix}_SECRET")
        if not client_id or not secret:
            raise HTTPException(status_code=503, detail=f"Plaid {environment.title()} is not configured by the service yet.")
        return PlaidClient(client_id, secret, environment)
    namespace = f"plaid:{environment}"
    client_id = credentials_store.get_bank_credential(namespace, "client_id")
    secret = credentials_store.get_bank_credential(namespace, "secret")
    if not client_id or not secret:
        raise HTTPException(status_code=400, detail=f"Add Plaid {environment.title()} credentials in Settings first.")
    return PlaidClient(client_id, secret, environment)


def _get_item_access_token(item: PlaidItem) -> str | None:
    if hosted_auth_enabled():
        return decrypt_secret(item.access_token_encrypted) if item.access_token_encrypted else None
    return credentials_store.get_bank_credential(f"plaid:{item.environment}:item", item.item_id)


def _delete_item_access_token(item: PlaidItem) -> None:
    if hosted_auth_enabled():
        item.access_token_encrypted = None
    else:
        credentials_store.delete_bank_credential(f"plaid:{item.environment}:item", item.item_id)


def _plaid_error(exc: PlaidAPIError, environment: PlaidEnvironment) -> HTTPException:
    # Provider error codes are useful for troubleshooting; omit body/message/token data.
    return HTTPException(status_code=exc.status_code, detail={"code": exc.error_code, "message": f"Plaid {environment.title()} request failed."})


def _item_payload(item: PlaidItem) -> dict:
    return {
        "item_id": item.item_id, "environment": item.environment,
        "institution_id": item.institution_id, "institution_name": item.institution_name,
        "accounts": json.loads(item.accounts_json or "[]"),
        "last_sync_at": item.last_sync_at.isoformat() if item.last_sync_at else None,
        "last_sync_status": item.last_sync_status,
        "sync_counts": {"added": item.added_count, "modified": item.modified_count, "removed": item.removed_count},
        "transaction_counts": {"imported": item.imported_count, "duplicates": item.duplicate_count},
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("/config")
def get_config(environment: PlaidEnvironment = Query(default="sandbox")):
    if hosted_auth_enabled():
        prefix = "PLAID_PRODUCTION" if environment == "production" else "PLAID_SANDBOX"
        return {"environment": environment, "configured": bool(os.getenv(f"{prefix}_CLIENT_ID") and os.getenv(f"{prefix}_SECRET")), "managed": True}
    namespace = f"plaid:{environment}"
    return {"environment": environment, "configured": bool(
        credentials_store.get_bank_credential(namespace, "client_id")
        and credentials_store.get_bank_credential(namespace, "secret")
    )}


@router.post("/config")
def save_config(config: PlaidCredentials, environment: PlaidEnvironment = Query(default="sandbox")):
    if hosted_auth_enabled():
        raise HTTPException(status_code=404, detail="Plaid developer credentials are managed by the service")
    namespace = f"plaid:{environment}"
    credentials_store.save_bank_credential(namespace, "client_id", config.client_id.strip())
    credentials_store.save_bank_credential(namespace, "secret", config.secret.strip())
    return {"environment": environment, "configured": True}


@router.get("/items")
def list_items(environment: PlaidEnvironment = Query(default="sandbox")):
    with get_session() as session:
        return [_item_payload(row) for row in session.scalars(select(PlaidItem).where(
            PlaidItem.environment == environment
        ).order_by(PlaidItem.created_at.desc()))]


@router.post("/link-token")
def create_link_token(environment: PlaidEnvironment = Query(default="sandbox")):
    try:
        return {"link_token": _client(environment).create_link_token(current_owner_id()), "environment": environment}
    except PlaidAPIError as exc:
        raise _plaid_error(exc, environment)


@router.post("/exchange")
def exchange_token(request: PublicTokenRequest, environment: PlaidEnvironment = Query(default="sandbox")):
    client = _client(environment)
    try:
        exchange = client.exchange_public_token(request.public_token)
        access_token = exchange.get("access_token")
        item_id = exchange.get("item_id")
        if not access_token or not item_id:
            raise PlaidAPIError("PLAID_INVALID_RESPONSE")
        metadata, accounts = client.item_and_accounts(access_token)
        item_id = metadata.get("item_id") or item_id
        with get_session() as session:
            item = session.get(PlaidItem, item_id)
            if item is not None and item.environment != environment:
                raise HTTPException(status_code=409, detail="That Plaid Item ID is already registered in a different environment.")
            if item is None:
                item = PlaidItem(item_id=item_id, institution_name=metadata["institution_name"])
                session.add(item)
            if hosted_auth_enabled():
                item.access_token_encrypted = encrypt_secret(access_token)
            else:
                credentials_store.save_bank_credential(f"plaid:{environment}:item", item_id, access_token)
            item.environment = environment
            item.institution_id = metadata.get("institution_id")
            item.institution_name = metadata["institution_name"]
            item.accounts_json = json.dumps(accounts)
            item.last_sync_status = "not_synced"
        return {"item_id": item_id, "environment": environment,
                "institution_name": metadata["institution_name"], "accounts": accounts}
    except PlaidAPIError as exc:
        raise _plaid_error(exc, environment)


@router.post("/items/{item_id}/sync")
def sync_item(item_id: str, background_tasks: BackgroundTasks,
              environment: PlaidEnvironment = Query(default="sandbox")):
    client = _client(environment)
    with get_session() as session:
        item = session.get(PlaidItem, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Plaid {environment.title()} connection not found.")
        if item.environment != environment:
            raise HTTPException(status_code=404, detail=f"Plaid {environment.title()} connection not found.")
        original_cursor = item.cursor
        access_token = _get_item_access_token(item)
        if not access_token:
            raise HTTPException(status_code=409, detail=f"Plaid {environment.title()} access token is missing. Remove and reconnect this Item.")
        try:
            for attempt in range(3):
                cursor = original_cursor
                totals = {"added": 0, "modified": 0, "removed": 0}
                deltas = {"added": [], "modified": [], "removed": []}
                try:
                    while True:
                        page = client.sync_page(access_token, cursor)
                        for key in deltas:
                            page_rows = page.get(key, [])
                            totals[key] += len(page_rows)
                            if environment == "production":
                                deltas[key].extend(page_rows)
                        cursor = page.get("next_cursor") or cursor
                        if not page.get("has_more"):
                            break
                    ingestion = {"imported": 0, "duplicates": 0, "modified": 0,
                                 "removed": 0, "new_transaction_ids": []}
                    if environment == "production":
                        ingestion = apply_transaction_deltas(
                            session, environment=environment, item_id=item_id,
                            institution_name=item.institution_name,
                            accounts=json.loads(item.accounts_json or "[]"),
                            added=deltas["added"], modified=deltas["modified"], removed=deltas["removed"],
                        )
                        if any(ingestion[key] for key in ("imported", "modified", "removed")):
                            all_txs = session.scalars(select(Transaction)).all()
                            reconcile_subscriptions(session, all_txs)
                            invalidate_derived_data(session)
                        if ingestion["new_transaction_ids"]:
                            from backend.jobs.enrichment import enqueue_transactions, run_job
                            job_id = enqueue_transactions(session, ingestion["new_transaction_ids"])
                            if job_id:
                                background_tasks.add_task(run_job, job_id)
                            from backend.routes.search import _embed_all
                            background_tasks.add_task(_embed_all, get_session)
                    item.cursor = cursor
                    item.last_sync_at = datetime.now(timezone.utc)
                    item.last_sync_status = "synced"
                    item.added_count = totals["added"]
                    item.modified_count = totals["modified"]
                    item.removed_count = totals["removed"]
                    item.imported_count = (item.imported_count or 0) + ingestion["imported"]
                    item.duplicate_count = (item.duplicate_count or 0) + ingestion["duplicates"]
                    return {"item_id": item_id, "environment": environment,
                            "last_sync_at": item.last_sync_at.isoformat(), "sync_counts": totals,
                            "transaction_counts": {key: ingestion[key] for key in
                                ("imported", "duplicates", "modified", "removed")}}
                except PlaidAPIError as exc:
                    if exc.error_code == "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION" and attempt < 2:
                        continue
                    item.last_sync_status = "error"
                    raise
        except PlaidAPIError as exc:
            raise _plaid_error(exc, environment)
    raise HTTPException(status_code=502, detail=f"Plaid {environment.title()} sync could not complete.")


@router.delete("/items/{item_id}")
def remove_item(item_id: str, environment: PlaidEnvironment = Query(default="sandbox")):
    client = _client(environment)
    with get_session() as session:
        item = session.get(PlaidItem, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Plaid {environment.title()} connection not found.")
        if item.environment != environment:
            raise HTTPException(status_code=404, detail=f"Plaid {environment.title()} connection not found.")
        access_token = _get_item_access_token(item)
        if access_token:
            try:
                client.remove_item(access_token)
            except PlaidAPIError as exc:
                raise _plaid_error(exc, environment)
        session.delete(item)
        _delete_item_access_token(item)
    return {"status": "removed", "item_id": item_id}
