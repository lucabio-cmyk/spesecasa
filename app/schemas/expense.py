import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.enums import ExpenseScope, FiscalClassification


class ExpenseBase(BaseModel):
    document_id: uuid.UUID | None = None
    payer_user_id: uuid.UUID | None = None
    beneficiary_user_id: uuid.UUID | None = None
    purchase_date: date | None = None
    merchant: str | None = None
    description_original: str | None = None
    description_normalized: str | None = None
    merch_category: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_amount: Decimal
    discount: Decimal | None = None
    fiscal_classification: FiscalClassification = FiscalClassification.NON_RILEVANTE
    scope: ExpenseScope = ExpenseScope.FAMILIARE
    fiscal_year: int | None = None
    details: dict | None = None
    reliability_note: str | None = None


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(BaseModel):
    merch_category: str | None = None
    description_normalized: str | None = None
    fiscal_classification: FiscalClassification | None = None
    scope: ExpenseScope | None = None
    payer_user_id: uuid.UUID | None = None
    beneficiary_user_id: uuid.UUID | None = None
    reliability_note: str | None = None


class ExpenseOut(ExpenseBase):
    id: uuid.UUID
    household_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
