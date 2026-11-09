from unittest.mock import Mock, patch

import pytest

from backend.plaid_client import PlaidClient, PlaidSandboxClient


@pytest.mark.parametrize(("environment", "expected_host"), [
    ("sandbox", "https://sandbox.plaid.com/test/endpoint"),
    ("production", "https://production.plaid.com/test/endpoint"),
])
def test_plaid_client_uses_fixed_environment_host(environment, expected_host):
    response = Mock(ok=True)
    response.json.return_value = {"ok": True}
    with patch("backend.plaid_client.requests.post", return_value=response) as post:
        client = PlaidClient("client", "secret", environment)
        assert client.post("/test/endpoint", {}) == {"ok": True}
    assert post.call_args.args[0] == expected_host


def test_unknown_plaid_environment_is_rejected():
    with pytest.raises(ValueError, match="Unsupported Plaid environment"):
        PlaidClient("client", "secret", "https://attacker.invalid")


def test_legacy_sandbox_client_remains_sandbox_only():
    client = PlaidSandboxClient("client", "secret")
    assert client._base_url == "https://sandbox.plaid.com"
