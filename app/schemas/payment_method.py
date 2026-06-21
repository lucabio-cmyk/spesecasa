import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.enums import PaymentMethodType


class PaymentMethodBase(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    method_type: PaymentMethodType = PaymentMethodType.ALTRO
    provider: str | None = None
    last4: str | None = Field(default=None, max_length=8)
    is_default: bool = False
    active: bool = True
    notes: str | None = None
    details: dict | None = None


class PaymentMethodCreate(PaymentMethodBase):
    # Intestatario del metodo. Se omesso, si usa l'utente corrente.
    user_id: uuid.UUID | None = None


class PaymentMethodUpdate(BaseModel):
    """Aggiornamento parziale: si modifica solo ciò che viene inviato."""

    user_id: uuid.UUID | None = None
    label: str | None = Field(default=None, min_length=1, max_length=120)
    method_type: PaymentMethodType | None = None
    provider: str | None = None
    last4: str | None = Field(default=None, max_length=8)
    is_default: bool | None = None
    active: bool | None = None
    notes: str | None = None
    details: dict | None = None


class PaymentMethodOut(PaymentMethodBase):
    id: uuid.UUID
    household_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
