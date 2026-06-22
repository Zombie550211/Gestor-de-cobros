from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class PaymentLinkCreate(BaseModel):
    customer_name: str
    phone_number: str
    amount: Decimal
    description: str
    expires_in_minutes: int
    agent_name: str = "Agent"

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Amount must be positive")
        return v

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
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


class PaymentLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    token: str
    customer_name: str
    phone_number: str
    amount: Decimal
    currency: str
    description: str
    status: str
    created_at: datetime
    expires_at: datetime
    opened_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    agent_name: Optional[str] = None
