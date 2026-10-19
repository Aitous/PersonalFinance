from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True)
    source = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=True)
    merchant_name = Column(String, nullable=True)
    city = Column(String, nullable=True)
    is_online = Column(Boolean, nullable=True)
    merchant_type = Column(String, nullable=True)
    is_subscription = Column(Boolean, default=False)
    metadata_ = Column("metadata", Text, nullable=True)
    raw_csv_row = Column(Text, nullable=True)
    embedding = Column(Text, nullable=True)
    account_id = Column(String, nullable=True, index=True)
    original_amount = Column(Float, nullable=True)
    amount_minor = Column(Integer, nullable=True)
    currency = Column(String(3), nullable=True)
    bank_fitid = Column(String, nullable=True, index=True)
    kind = Column(String, nullable=True)
    manual_category = Column(Boolean, nullable=False, default=False)
    enrichment_status = Column(String, nullable=True)
    enrichment_input_hash = Column(String, nullable=True)
    embedding_input_hash = Column(String, nullable=True)
    embedding_model_version = Column(String, nullable=True)
    manual_fields = Column(Text, nullable=True)
    raw_enrichment = Column(Text, nullable=True)

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    frequency = Column(String, nullable=False)  # 'monthly' | 'annual'
    last_charged = Column(Date, nullable=True)
    active = Column(Boolean, default=True)
    origin = Column(String, nullable=False, default="detected")
    dismissed = Column(Boolean, nullable=False, default=False)
    user_active = Column(Boolean, nullable=True)
    supporting_transaction_ids = Column(Text, nullable=True)


class Account(Base):
    __tablename__ = "accounts"
    id = Column(String, primary_key=True)
    bank = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    last4 = Column(String(4), nullable=True)
    external_id = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id = Column(String, primary_key=True)
    bank = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True, index=True)
    filename = Column(String, nullable=False)
    checksum = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    status = Column(String, nullable=False, default="imported")
    input_count = Column(Integer, nullable=False, default=0)
    parsed_count = Column(Integer, nullable=False, default=0)
    rejected_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    new_count = Column(Integer, nullable=False, default=0)
    from_date = Column(Date, nullable=True)
    to_date = Column(Date, nullable=True)


class ImportedRow(Base):
    __tablename__ = "imported_rows"
    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String, nullable=False, index=True)
    transaction_id = Column(String, nullable=True, index=True)
    row_number = Column(Integer, nullable=False)
    row_hash = Column(String, nullable=False, index=True)
    raw_data = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="accepted")
    reason = Column(String, nullable=True)


class DataRevision(Base):
    __tablename__ = "data_revision"
    id = Column(Integer, primary_key=True)
    revision = Column(Integer, nullable=False, default=0)


class EnrichmentJob(Base):
    __tablename__ = "enrichment_jobs"
    id = Column(String, primary_key=True)
    status = Column(String, nullable=False, default="pending")
    mode = Column(String, nullable=False, default="enrich")
    total = Column(Integer, nullable=False, default=0)
    done = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class EnrichmentJobItem(Base):
    __tablename__ = "enrichment_job_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    transaction_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    model = Column(String, nullable=True)
    input_hash = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class MerchantAlias(Base):
    __tablename__ = "merchant_aliases"
    id = Column(Integer, primary_key=True, autoincrement=True)
    alias = Column(String, nullable=False, unique=True, index=True)
    canonical = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

class Sync(Base):
    __tablename__ = "syncs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    tx_count = Column(Integer, nullable=False)


class MonthlyReportCache(Base):
    __tablename__ = "monthly_report_cache"

    year = Column(Integer, primary_key=True)
    month = Column(Integer, primary_key=True)
    narrative = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    data_revision = Column(Integer, nullable=False, default=-1)
