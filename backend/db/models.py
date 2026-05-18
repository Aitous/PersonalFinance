from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True)  # hash of source+date+amount+description
    source = Column(String, nullable=False)  # 'chase' | 'discover' | 'amex'
    date = Column(Date, nullable=False)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)  # negative=expense, positive=credit
    category = Column(String, nullable=True)
    is_subscription = Column(Boolean, default=False)
    metadata_ = Column("metadata", Text, nullable=True)  # JSON blob
    raw_csv_row = Column(Text, nullable=True)

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    frequency = Column(String, nullable=False)  # 'monthly' | 'annual'
    last_charged = Column(Date, nullable=True)
    active = Column(Boolean, default=True)

class Sync(Base):
    __tablename__ = "syncs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)
    synced_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    tx_count = Column(Integer, nullable=False)
