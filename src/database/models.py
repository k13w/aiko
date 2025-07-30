from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

class ReconciliationStatus(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class ReconciliationType(enum.Enum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    iugu_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    current_balance = Column(Float, nullable=False, default=0.0)
    last_sync = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ReconciliationRecord(Base):
    __tablename__ = "reconciliation_records"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    local_balance = Column(Float, nullable=False)
    iugu_balance = Column(Float, nullable=False)
    difference = Column(Float, nullable=False)
    status = Column(Enum(ReconciliationStatus), nullable=False)
    type = Column(Enum(ReconciliationType), nullable=False)
    error_message = Column(String, nullable=True)
    reconciliation_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account", backref="reconciliation_records")

class AdjustmentRecord(Base):
    __tablename__ = "adjustment_records"

    id = Column(Integer, primary_key=True)
    reconciliation_id = Column(Integer, ForeignKey("reconciliation_records.id"))
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    reconciliation = relationship("ReconciliationRecord", backref="adjustments")