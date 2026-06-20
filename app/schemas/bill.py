import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.enums import BillStatus, UtilityType


class BillBase(BaseModel):
    document_id: uuid.UUID | None = None
    payer_user_id: uuid.UUID | None = None
    property_unit_id: uuid.UUID | None = None
    utility_type: UtilityType = UtilityType.ALTRO
    supplier: str | None = None
    service_id: str | None = None
    bill_number: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    issue_date: date | None = None
    due_date: date | None = None
    total_amount: Decimal | None = None
    energy_cost: Decimal | None = None
    fixed_cost: Decimal | None = None
    taxes: Decimal | None = None
    consumption_quantity: Decimal | None = None
    consumption_unit: str | None = None
    status: BillStatus = BillStatus.DA_PAGARE
    paid_date: date | None = None
    payment_method: str | None = None
    fiscal_year: int | None = None
    reliability_note: str | None = None
    notes: str | None = None
    details: dict | None = None


class BillCreate(BillBase):
    pass


class BillUpdate(BaseModel):
    payer_user_id: uuid.UUID | None = None
    property_unit_id: uuid.UUID | None = None
    utility_type: UtilityType | None = None
    supplier: str | None = None
    service_id: str | None = None
    bill_number: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    issue_date: date | None = None
    due_date: date | None = None
    total_amount: Decimal | None = None
    energy_cost: Decimal | None = None
    fixed_cost: Decimal | None = None
    taxes: Decimal | None = None
    consumption_quantity: Decimal | None = None
    consumption_unit: str | None = None
    status: BillStatus | None = None
    paid_date: date | None = None
    payment_method: str | None = None
    fiscal_year: int | None = None
    reliability_note: str | None = None
    notes: str | None = None
    details: dict | None = None


class BillOut(BillBase):
    id: uuid.UUID
    household_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
