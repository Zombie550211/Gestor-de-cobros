import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Text

from app.database import Base


class ChargeStatus(str, enum.Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REQUIRES_ACTION = "REQUIRES_ACTION"
    PROCESSING = "PROCESSING"


class Charge(Base):
    """Cobro ejecutado sobre una tarjeta ya guardada.

    Cada fila es un cobro adicional hecho desde el Data Center, sin volver a
    pedirle los datos al cliente. Apunta al payment_link donde esa tarjeta se
    registró por primera vez.
    """

    __tablename__ = "charges"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    payment_link_id = Column(
        String(36), ForeignKey("payment_links.id"), nullable=False, index=True
    )
    stripe_payment_intent_id = Column(String(255), nullable=True, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="usd", nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=ChargeStatus.PROCESSING.value, nullable=False)
    failure_message = Column(Text, nullable=True)
    agent_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
