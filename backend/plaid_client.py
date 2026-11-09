"""Small fixed-host Plaid client; never logs request or response bodies."""
from typing import Any, Literal, Optional

import requests


SANDBOX_BASE_URL = "https://sandbox.plaid.com"
PRODUCTION_BASE_URL = "https://production.plaid.com"
PlaidEnvironment = Literal["sandbox", "production"]


class PlaidAPIError(Exception):
    def __init__(self, error_code: str = "PLAID_ERROR", status_code: int = 502):
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(error_code)


class PlaidClient:
    def __init__(self, client_id: str, secret: str, environment: PlaidEnvironment = "sandbox"):
        if environment not in {"sandbox", "production"}:
            raise ValueError("Unsupported Plaid environment")
        self._auth = {"client_id": client_id, "secret": secret}
        self._environment = environment
        self._base_url = SANDBOX_BASE_URL if environment == "sandbox" else PRODUCTION_BASE_URL

    def post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        # Endpoint names are internal constants, never user-provided URLs.
        try:
            response = requests.post(
                f"{self._base_url}/{endpoint.lstrip('/')}",
                json={**payload, **self._auth}, timeout=(5, 30),
            )
        except requests.RequestException as exc:
            raise PlaidAPIError("PLAID_UNAVAILABLE", 503) from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise PlaidAPIError("PLAID_INVALID_RESPONSE", 502) from exc
        if not response.ok:
            code = body.get("error_code") if isinstance(body, dict) else None
            safe_code = code if isinstance(code, str) and code.replace("_", "").isalnum() else "PLAID_ERROR"
            raise PlaidAPIError(safe_code, 400 if response.status_code < 500 else 502)
        if not isinstance(body, dict):
            raise PlaidAPIError("PLAID_INVALID_RESPONSE", 502)
        return body

    def create_link_token(self, client_user_id: str = "personal-finance-local-user") -> str:
        result = self.post("link/token/create", {
            "client_name": f"Personal Finance ({self._environment.title()})",
            "language": "en",
            "country_codes": ["US"],
            "user": {"client_user_id": client_user_id},
            "products": ["transactions"],
            "transactions": {"days_requested": 180},
        })
        token = result.get("link_token")
        if not isinstance(token, str) or not token:
            raise PlaidAPIError("PLAID_INVALID_RESPONSE", 502)
        return token

    def exchange_public_token(self, public_token: str) -> dict[str, Any]:
        return self.post("item/public_token/exchange", {"public_token": public_token})

    def item_and_accounts(self, access_token: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        item = self.post("item/get", {"access_token": access_token}).get("item", {})
        accounts = self.post("accounts/get", {"access_token": access_token}).get("accounts", [])
        institution_id = item.get("institution_id")
        institution_name = "Sandbox institution"
        if institution_id:
            result = self.post("institutions/get_by_id", {
                "institution_id": institution_id, "country_codes": ["US"],
            })
            institution_name = result.get("institution", {}).get("name") or institution_name
        safe_accounts = [{
            "account_id": account.get("account_id"),
            "name": account.get("name") or "Account",
            "mask": account.get("mask"),
            "type": account.get("type"),
            "subtype": account.get("subtype"),
        } for account in accounts if account.get("account_id")]
        return {"item_id": item.get("item_id"), "institution_id": institution_id,
                "institution_name": institution_name}, safe_accounts

    def sync_page(self, access_token: str, cursor: Optional[str]) -> dict[str, Any]:
        payload: dict[str, Any] = {"access_token": access_token, "count": 500}
        if cursor:
            payload["cursor"] = cursor
        return self.post("transactions/sync", payload)

    def remove_item(self, access_token: str) -> None:
        self.post("item/remove", {"access_token": access_token})


class PlaidSandboxClient(PlaidClient):
    """Compatibility alias for existing Sandbox callers."""

    def __init__(self, client_id: str, secret: str):
        super().__init__(client_id, secret, "sandbox")
