from datetime import date, datetime, timezone
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.models import Account, Base, ImportBatch, Sync, Transaction


def test_catalog_preserves_source_values_and_reports_unknown_attribution_and_coverage():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Account(id="acct-1", bank="Chase", name="Checking", last4="1234"))
        session.add_all([
            Transaction(id="1", source="Chase", date=date(2025, 12, 31), description="RAW PRIVATE TEXT", amount=42,
                        merchant_name="Cafe OAK", city="Oakland", category="Dining", account_id="acct-1",
                        metadata_='{"Country":"UNITED STATES"}', currency="USD"),
            Transaction(id="2", source="Mystery", date=date(2026, 1, 1), description="PRIVATE", amount=5,
                        merchant_name="Cafe Oak", city=None, category=None, account_id="missing-account",
                        metadata_="{}", currency=None),
            Transaction(id="3", source="Mystery", date=date(2026, 1, 2), description="PRIVATE", amount=1,
                        merchant_name=None, city="", category="", account_id=None, metadata_=None),
        ])
        session.add(ImportBatch(id="batch", bank="Chase", account_id="acct-1", filename="private.csv",
                                checksum="secret-hash", created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
                                status="imported", from_date=date(2025, 12, 1), to_date=date(2025, 12, 31)))
        session.add(Sync(id=1, source="Chase", synced_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
                         from_date=date(2025, 12, 1), to_date=date(2025, 12, 31), tx_count=1))
        session.commit()

        from backend.analysis.data_catalog import build_catalog
        catalog = build_catalog(session)

    assert catalog["transaction_count"] == 3
    assert catalog["observed_date_range"] == {"from": "2025-12-31", "through": "2026-01-02"}
    assert catalog["years"] == [
        {"year": 2025, "count": 1, "months": [{"month": 12, "count": 1}]},
        {"year": 2026, "count": 2, "months": [{"month": 1, "count": 2}]},
    ]
    assert catalog["unknown_account_count"] == 2
    assert catalog["data_quality"]["missing_city"] == 2
    assert catalog["data_quality"]["missing_merchant"] == 1
    assert catalog["data_quality"]["missing_category"] == 2
    assert catalog["countries"] == [{"name": "UNITED STATES", "count": 1}]
    assert catalog["coverage"]["complete_statement_periods"] is False
    assert catalog["coverage"]["imports"] == [
        {"account_id": "acct-1", "from_date": "2025-12-01", "to_date": "2025-12-31", "status": "imported"}
    ]
    assert catalog["freshness"]["latest_import_at"] == "2026-01-04T00:00:00+00:00"
    serialized = json.dumps(catalog)
    for private in ("RAW PRIVATE TEXT", "PRIVATE", "private.csv", "secret-hash", '"amount"'):
        assert private not in serialized
