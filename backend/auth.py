"""Request identity and tenant context for the API."""
from __future__ import annotations
from contextvars import ContextVar
from functools import lru_cache
import asyncio
import os
from typing import Any

import jwt
from jwt import PyJWKClient
from fastapi import HTTPException, Request
from sqlalchemy import text

LOCAL_OWNER_ID = "local-owner"
_current_owner: ContextVar[str | None] = ContextVar("current_owner", default=None)


def hosted_auth_enabled() -> bool:
    configured_mode = os.getenv("APP_ENV", "").lower()
    if configured_mode in {"production", "staging"}:
        return True
    if configured_mode in {"local", "development", "test"}:
        return False
    database_url = os.getenv("DATABASE_URL", "").lower()
    return database_url.startswith(("postgres://", "postgresql://", "postgresql+"))


def current_owner_id() -> str:
    owner_id = _current_owner.get()
    if owner_id:
        return owner_id
    if not hosted_auth_enabled():
        return LOCAL_OWNER_ID
    raise RuntimeError("A verified user identity is required for database access")


def set_current_owner(owner_id: str | None):
    return _current_owner.set(owner_id)


def reset_current_owner(token) -> None:
    _current_owner.reset(token)


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    project_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not project_url:
        raise RuntimeError("SUPABASE_URL is required when hosted authentication is enabled")
    # Keep only the short-lived JWKS-set cache so rotated keys become visible.
    return PyJWKClient(f"{project_url}/auth/v1/.well-known/jwks.json", cache_keys=False, lifespan=300)


def verify_access_token(token: str) -> dict[str, Any]:
    """Verify a Supabase asymmetric access token and its required claims."""
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        project_url = os.environ["SUPABASE_URL"].rstrip("/")
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=[signing_key.algorithm_name],
            audience="authenticated",
            issuer=f"{project_url}/auth/v1",
            options={"require": ["exp", "sub", "iss", "aud"]},
        )
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise jwt.InvalidTokenError("Missing subject")
        return claims
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc


async def authenticate_request(request: Request) -> str:
    if not hosted_auth_enabled():
        return LOCAL_OWNER_ID
    if request.url.path in {"/health", "/docs", "/openapi.json", "/redoc"}:
        return ""
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Sign in to access this resource")
    claims = await asyncio.to_thread(verify_access_token, token)
    owner_id = claims["sub"]
    try:
        from backend.db.database import engine
        with engine.connect() as connection:
            deletion = connection.execute(
                text("SELECT status FROM account_deletions WHERE owner_id = :owner_id"),
                {"owner_id": owner_id},
            ).scalar_one_or_none()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Account status could not be verified") from exc
    if deletion:
        retry_delete = request.url.path == "/account" and request.method == "DELETE"
        deletion_status = request.url.path == "/account/deletion-status" and request.method == "GET"
        if deletion != "deleting" or not (retry_delete or deletion_status):
            raise HTTPException(status_code=410, detail={"code": "account_deletion_pending", "message": "This account is being deleted."})
    return owner_id
