import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Numeric, String, Text

from app.database import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SMS_SENT = "SMS_SENT"
    OPENED = "OPENED"
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    ABANDONED = "ABANDONED"
    CANCELLED = "CANCELLED"


class PaymentLink(Base):
    __tablename__ = "payment_links"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token = Column(String(32), unique=True, nullable=False, index=True)
    stripe_payment_intent_id = Column(String(255), nullable=True)
    stripe_client_secret = Column(String(500), nullable=True)
    customer_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="usd")
    description = Column(Text, nullable=False)
    status = Column(String(20), default="PENDING", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    opened_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    time_spent = Column(Numeric(10, 2), nullable=True)
    agent_name = Column(String(255), nullable=True)
