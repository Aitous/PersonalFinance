from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class OwnerScoped:
    """Mixin for rows whose visibility and mutation belong to one account."""
    owner_id = Column(String(128), nullable=False, index=True, default="local-owner")


class Transaction(OwnerScoped, Base):
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

class Subscription(OwnerScoped, Base):
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


class Account(OwnerScoped, Base):
    __tablename__ = "accounts"
    id = Column(String, primary_key=True)
    bank = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    last4 = Column(String(4), nullable=True)
    external_id = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class ImportBatch(OwnerScoped, Base):
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


class ImportedRow(OwnerScoped, Base):
    __tablename__ = "imported_rows"
    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String, nullable=False, index=True)
    transaction_id = Column(String, nullable=True, index=True)
    row_number = Column(Integer, nullable=False)
    row_hash = Column(String, nullable=False, index=True)
    raw_data = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="accepted")
    reason = Column(String, nullable=True)


class DataRevision(OwnerScoped, Base):
    __tablename__ = "data_revision"
    id = Column(Integer, primary_key=True)
    revision = Column(Integer, nullable=False, default=0)


class EnrichmentJob(OwnerScoped, Base):
    __tablename__ = "enrichment_jobs"
    id = Column(String, primary_key=True)
    status = Column(String, nullable=False, default="pending")
    mode = Column(String, nullable=False, default="enrich")
    total = Column(Integer, nullable=False, default=0)
    done = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class EnrichmentJobItem(OwnerScoped, Base):
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


class MerchantAlias(OwnerScoped, Base):
    __tablename__ = "merchant_aliases"
    __table_args__ = (UniqueConstraint("owner_id", "alias", name="uq_merchant_alias_owner_alias"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    alias = Column(String, nullable=False, index=True)
    canonical = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)


class CategoryRule(OwnerScoped, Base):
    __tablename__ = "category_rules"
    __table_args__ = (UniqueConstraint("owner_id", "merchant_key", name="uq_category_rule_owner_key"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_key = Column(String, nullable=False, index=True)
    merchant = Column(String, nullable=False)
    category = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

class Sync(OwnerScoped, Base):
    __tablename__ = "syncs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    tx_count = Column(Integer, nullable=False)


class MonthlyReportCache(OwnerScoped, Base):
    __tablename__ = "monthly_report_cache"

    owner_id = Column(String(128), primary_key=True, default="local-owner")
    year = Column(Integer, primary_key=True)
    month = Column(Integer, primary_key=True)
    narrative = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    data_revision = Column(Integer, nullable=False, default=-1)
    prompt_version = Column(Integer, nullable=False, default=1)


class MonthlyCategoryExplanationCache(OwnerScoped, Base):
    __tablename__ = "monthly_category_explanation_cache"

    owner_id = Column(String(128), primary_key=True, default="local-owner")
    year = Column(Integer, primary_key=True)
    month = Column(Integer, primary_key=True)
    comparison = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    data_revision = Column(Integer, nullable=False, default=-1)
    prompt_version = Column(Integer, nullable=False, default=1)


class PlaidItem(OwnerScoped, Base):
    """Non-secret metadata for one environment-scoped Plaid Item."""
    __tablename__ = "plaid_items"

    item_id = Column(String, primary_key=True)
    environment = Column(String, nullable=False, default="sandbox")
    institution_id = Column(String, nullable=True)
    institution_name = Column(String, nullable=False)
    accounts_json = Column(Text, nullable=False, default="[]")
    cursor = Column(Text, nullable=True)
    access_token_encrypted = Column(Text, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String, nullable=False, default="not_synced")
    added_count = Column(Integer, nullable=False, default=0)
    modified_count = Column(Integer, nullable=False, default=0)
    removed_count = Column(Integer, nullable=False, default=0)
    imported_count = Column(Integer, nullable=False, default=0)
    duplicate_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class PlaidTransactionIdentity(OwnerScoped, Base):
    """Maps one environment-scoped Plaid transaction ID to its ledger row."""
    __tablename__ = "plaid_transaction_identities"

    owner_id = Column(String(128), primary_key=True, default="local-owner")
    environment = Column(String, primary_key=True)
    plaid_transaction_id = Column(String, primary_key=True)
    item_id = Column(String, nullable=False, index=True)
    account_id = Column(String, nullable=True)
    transaction_id = Column(String, nullable=False, index=True)
    plaid_owned = Column(Boolean, nullable=False, default=True)


class LLMUsage(OwnerScoped, Base):
    """Privacy-minimal record of a single managed provider request."""
    __tablename__ = "llm_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    feature = Column(String, nullable=False, default="ai")
    provider = Column(String, nullable=False)
    model = Column(String, nullable=True)
    status = Column(String, nullable=False, default="reserved")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)


class AIConsent(OwnerScoped, Base):
    """Versioned confirmation that a user understands AI data processing."""
    __tablename__ = "ai_consents"

    owner_id = Column(String(128), primary_key=True, default="local-owner")
    policy_version = Column(Integer, nullable=False)
    accepted = Column(Boolean, nullable=False, default=False)
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)


class LLMPlatformUsage(Base):
    """Global circuit-breaker counter; never exposed through the client API."""
    __tablename__ = "llm_platform_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)


class AccountDeletion(Base):
    """Global tombstone preventing stale access tokens from reviving an account."""
    __tablename__ = "account_deletions"

    owner_id = Column(String(128), primary_key=True)
    status = Column(String, nullable=False, default="deleting")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
