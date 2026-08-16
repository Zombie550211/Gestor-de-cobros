import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text

from app.database import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SMS_SENT = "SMS_SENT"
    EMAIL_SENT = "EMAIL_SENT"
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
    customer_email = Column(String(255), nullable=True)
    phone_number = Column(String(20), nullable=True)
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

    # --- Tarjeta guardada (Data Center) ---------------------------------
    # Nunca se guarda el número de tarjeta: Stripe custodia los datos y aquí
    # solo se conservan sus identificadores (reutilizables) y los últimos 4
    # dígitos para que el agente reconozca la tarjeta.
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_payment_method_id = Column(String(255), nullable=True, index=True)
    card_brand = Column(String(30), nullable=True)
    card_last4 = Column(String(4), nullable=True)
    card_exp_month = Column(Integer, nullable=True)
    card_exp_year = Column(Integer, nullable=True)
    card_funding = Column(String(20), nullable=True)
    card_country = Column(String(2), nullable=True)
    # Huella estable de la tarjeta física: Stripe emite un payment_method nuevo
    # en cada cobro, así que esto es lo que permite reconocer al mismo cliente.
    card_fingerprint = Column(String(64), nullable=True, index=True)
    # "checkout":  el cliente autorizó guardarla al pagar -> cobrable de nuevo.
    # "recovered": recuperada del historial de Stripe -> solo lectura. Stripe
    #              impide reutilizar un método de pago que se cobró sin Customer,
    #              así que estas tarjetas no se pueden volver a cobrar.
    card_source = Column(String(20), nullable=True)
