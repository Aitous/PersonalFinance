import pytest
from unittest.mock import patch, call
from backend.credentials import CredentialsStore

def test_save_and_get_bank_credential():
    store = CredentialsStore()
    with patch("keyring.set_password") as mock_set, \
         patch("keyring.get_password", return_value="mypassword"):
        store.save_bank_credential("chase", "username", "myuser")
        store.save_bank_credential("chase", "password", "mypassword")
        pwd = store.get_bank_credential("chase", "password")
        assert pwd == "mypassword"

def test_save_and_get_llm_api_key():
    store = CredentialsStore()
    with patch("keyring.set_password") as mock_set, \
         patch("keyring.get_password", return_value="sk-ant-abc123"):
        store.save_llm_key("claude", "sk-ant-abc123")
        key = store.get_llm_key("claude")
        assert key == "sk-ant-abc123"

def test_missing_credential_returns_none():
    store = CredentialsStore()
    with patch("keyring.get_password", return_value=None):
        result = store.get_bank_credential("chase", "password")
        assert result is None
