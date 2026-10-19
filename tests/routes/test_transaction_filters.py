from contextlib import contextmanager
from datetime import date
from unittest.mock import patch
import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.models import Base, Transaction
from backend.main import app


@pytest.fixture
def client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    @contextmanager
    def session_scope():
        with Session(engine) as s:
            yield s
            s.commit()
    with session_scope() as s:
        for i in range(60):
            s.add(Transaction(id=str(i), source='chase' if i == 59 else 'amex',
                date=date(2026, 10, 1), description='COFFEE', amount=12 if i == 59 else 5,
                category='dining', merchant_name='Cafe', city='San Mateo',
                merchant_type='coffee shop', is_online=False, is_subscription=False))
        s.add(Transaction(id='refund', source='chase', date=date(2026, 10, 2),
            description='COFFEE REFUND', amount=-12, category='dining'))
    with patch('backend.routes.transactions.get_session', session_scope), \
         patch('backend.routes.search.get_session', session_scope):
        yield TestClient(app)
    engine.dispose()


def test_column_filters_compose_and_export_matches(client):
    params = dict(category='dining', source='chase', description='coffee',
        merchant_contains='caf', city='mateo', merchant_type='coffee',
        min_amount=10, max_amount=15, is_online='false', is_subscription='false')
    r = client.get('/transactions', params=params)
    assert r.status_code == 200
    assert [t['id'] for t in r.json()] == ['59']
    rows = list(csv.DictReader(io.StringIO(client.get('/transactions/export.csv', params=params).text)))
    assert len(rows) == 1 and rows[0]['source'] == 'chase'


def test_search_filters_before_result_limit(client):
    r = client.get('/search', params=dict(q='coffee', mode='keyword', source='chase', min_amount=10))
    assert [t['id'] for t in r.json()['results']] == ['59']


def test_ids_can_be_combined_with_filters(client):
    r = client.get('/transactions', params=dict(ids='1,59', source='chase'))
    assert [t['id'] for t in r.json()] == ['59']


def test_refund_amount_range_uses_magnitude(client):
    r = client.get('/transactions', params=dict(tx_type='refunds', min_amount=10, max_amount=15))
    assert [t['id'] for t in r.json()] == ['refund']


@pytest.mark.parametrize('params', [dict(min_amount=-1), dict(min_amount=20,max_amount=10), dict(date_from='invalid')])
def test_invalid_filters_return_validation_error(client, params):
    assert client.get('/transactions', params=params).status_code == 422


@pytest.mark.parametrize('params', [
    dict(description='unmatched'), dict(merchant_contains='unmatched'),
    dict(city='unmatched'), dict(merchant_type='unmatched'),
    dict(min_amount=100), dict(max_amount=1),
    dict(is_online='true'), dict(is_subscription='true'),
    dict(date_from='2026-11-01'), dict(date_to='2026-09-01'),
])
def test_each_column_filter_excludes_nonmatching_rows(client, params):
    r = client.get('/transactions', params=params)
    assert r.status_code == 200
    assert r.json() == []

