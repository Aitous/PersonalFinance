from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.models import Base, EnrichmentJob, EnrichmentJobItem, Transaction
from backend.main import app
from backend.analysis.categorizer import TransactionEnrichment
from backend.jobs.enrichment import create_job, run_job


def test_retry_recovers_fallbacks_without_changing_valid_categories():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    rows = [
        ('failed', 'other', 'RAW DESCRIPTION', 'unknown', 10),
        ('uncategorized', 'other', 'Market', 'grocery store', 10),
        ('valid', 'dining', 'Cafe', 'restaurant', 10),
        ('missing', 'travel', None, None, 10),
        ('refund', 'other', 'REFUND', 'unknown', -10),
        ('payment', 'other', 'AUTOPAY PAYMENT', 'unknown', 10),
    ]
    with session_scope() as session:
        for tx_id, category, merchant, kind, amount in rows:
            session.add(Transaction(id=tx_id, source='chase', date=date(2026, 1, 1),
                                    description=merchant or 'UNKNOWN', amount=amount,
                                    category=category, merchant_name=merchant, merchant_type=kind,
                                    enrichment_status='fallback' if tx_id in {'failed', 'uncategorized', 'missing'} else None))

    def enrich(batch):
        assert {tx.id for tx in batch} == {'failed', 'missing', 'uncategorized'}
        return {tx.id: TransactionEnrichment(id=tx.id, category='groceries',
                    merchant_name=None, is_online=False, merchant_type='grocery store')
                for tx in batch}

    with patch('backend.routes.import_csv.get_session', session_scope), \
         patch('backend.jobs.enrichment.get_session', session_scope), \
         patch('backend.llm.factory.get_llm_provider'), \
         patch('backend.analysis.categorizer.Categorizer._enrich_batch', side_effect=enrich), \
         patch('backend.routes.search.embed_texts', side_effect=lambda texts: __import__('numpy').zeros((len(texts), 384))), \
         patch('backend.analysis.merchant_normalizer.normalize_merchants', return_value={'merged': 0}):
        response = TestClient(app).post('/import/enrich')
        assert response.status_code == 200

    with session_scope() as session:
        assert session.get(Transaction, 'uncategorized').category == 'groceries'
        assert session.get(Transaction, 'failed').category == 'groceries'
        assert session.get(Transaction, 'missing').category == 'travel'
        assert session.get(Transaction, 'valid').category == 'dining'
        assert session.get(Transaction, 'payment').category == 'other'
        assert session.get(Transaction, 'refund').category == 'other'
        jobs = session.query(EnrichmentJob).all()
        assert len(jobs) == 1
        items = session.query(EnrichmentJobItem).filter_by(job_id=jobs[0].id).all()
        assert len(items) == 3
        assert all(item.attempts == 1 and item.status == 'success' for item in items)
    engine.dispose()


def test_runner_claims_once_runs_provider_outside_db_and_preserves_concurrent_manual_edits():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    @contextmanager
    def session_scope():
        with Session(engine) as session:
            yield session
            session.commit()

    with session_scope() as session:
        session.add(Transaction(id='one', source='chase', date=date(2026, 1, 1),
            description='RAW STORE', amount=20, category='travel', manual_category=True,
            merchant_name='User Merchant', city='Old City', manual_fields='["merchant_name","city"]',
            raw_enrichment='{"merchant_name":"Extracted Merchant"}'))

    class Provider:
        MODEL = 'test-model'

    with patch('backend.jobs.enrichment.get_session', session_scope):
        job_id, created = create_job('recategorize')
        assert created
        calls = []

        def enrich(batch):
            calls.append(batch)
            # A manual correction succeeds while the model call is in progress.
            with session_scope() as session:
                tx = session.get(Transaction, 'one')
                tx.city = 'Correct City'
                tx.manual_fields = '["merchant_name","city"]'
            # A duplicate callback cannot claim the running job or start another call.
            run_job(job_id, llm=Provider())
            return {'one': TransactionEnrichment(id='one', category='groceries',
                merchant_name='Model Merchant', city='Model City', is_online=True,
                merchant_type='grocery store')}

        with patch('backend.analysis.categorizer.Categorizer._enrich_batch', side_effect=enrich):
            run_job(job_id, llm=Provider())
            run_job(job_id, llm=Provider())

    assert len(calls) == 1
    with session_scope() as session:
        tx = session.get(Transaction, 'one')
        assert tx.category == 'travel'
        assert tx.merchant_name == 'User Merchant'
        assert tx.city == 'Correct City'
        assert tx.raw_enrichment.startswith('{"id": "one"')
        job = session.get(EnrichmentJob, job_id)
        item = session.query(EnrichmentJobItem).filter_by(job_id=job_id).one()
        assert job.status == 'done'
        assert item.attempts == 1 and item.model == 'test-model'
        assert item.status == 'success'
    engine.dispose()
