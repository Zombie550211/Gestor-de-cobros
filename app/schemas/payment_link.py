from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class PaymentLinkCreate(BaseModel):
    customer_name: str
    customer_email: EmailStr
    phone_number: Optional[str] = None
    amount: Decimal
    description: str
    expires_in_minutes: int
    agent_name: str = "Agent"

    @field_validator("amount")
    @classmethod
    def amount_in_range(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be positive")
        if v > Decimal("50000"):
            raise ValueError("Amount cannot exceed $50,000")
        return v

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        digits = "".join(filter(str.isdigit, v))
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits[0] == "1":
            return f"+{digits}"
        raise ValueError("Invalid US phone number — must be 10 digits")

    @field_validator("expires_in_minutes")
    @classmethod
    def valid_expiry(cls, v: int) -> int:
        if v < 5 or v > 10080:
            raise ValueError("Expiry must be between 5 minutes and 7 days")
        return v


class ActivityUpdate(BaseModel):
    status: Optional[str] = None
    time_spent: Optional[float] = None

    @field_validator("time_spent")
    @classmethod
    def valid_time_spent(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if v < 0 or v > 86400:
            raise ValueError("Invalid time_spent")
        return v


class PaymentLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    token: str
    customer_name: str
    customer_email: Optional[str] = None
    phone_number: Optional[str] = None
    amount: Decimal
    currency: str
    description: str
    status: str
    created_at: datetime
    expires_at: datetime
    opened_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    agent_name: Optional[str] = None
