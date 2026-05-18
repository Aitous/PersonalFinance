import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from backend.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

def test_get_transactions_empty():
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    with patch("backend.routes.transactions.get_session", return_value=mock_session):
        response = client.get("/transactions")
        assert response.status_code == 200
        assert response.json() == []

def test_get_subscriptions_empty():
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.execute.return_value.scalars.return_value.all.return_value = []
    with patch("backend.routes.transactions.get_session", return_value=mock_session):
        response = client.get("/subscriptions")
        assert response.status_code == 200
