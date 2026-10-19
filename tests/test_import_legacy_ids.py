import json
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.db.models import Base, Transaction
from backend.parsers.csv_parser import _make_id
from backend.sync_service import SyncService


@pytest.mark.parametrize('is_duplicate', [True, False])
def test_import_handles_legacy_sign_ids_without_dropping_refunds(is_duplicate):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    day = date(2025, 1, 1)
    raw = dict(Description='STORE', Amount='-12.00')
    current_id = _make_id('chase', day, 'STORE', 12)
    legacy_id = _make_id('chase', day, 'STORE', -12)
    with Session(engine) as session:
        session.add(Transaction(id=legacy_id, source='chase', date=day,
            description='STORE', amount=12 if is_duplicate else -12,
            category='shopping', raw_csv_row=json.dumps(raw if is_duplicate else dict(Description='STORE', Amount='12.00'))))
        session.commit()
        incoming = Transaction(id=current_id, source='chase', date=day,
            description='STORE', amount=12, raw_csv_row=json.dumps(raw))
        service = SyncService(session, MagicMock())
        service._categorizer.categorize = MagicMock(return_value={})
        service._sub_detector.detect = MagicMock(return_value=[])
        result = service.import_transactions([incoming])
        assert result['tx_count'] == (0 if is_duplicate else 1)
        assert len(session.execute(select(Transaction)).scalars().all()) == (1 if is_duplicate else 2)
        if is_duplicate:
            service._categorizer.categorize.assert_not_called()
    engine.dispose()
