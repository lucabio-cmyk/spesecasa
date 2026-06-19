import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.enums import DocumentStatus, DocumentType, ExpenseScope, FiscalClassification


class DocumentOut(BaseModel):
    id: uuid.UUID
    household_id: uuid.UUID
    doc_type: DocumentType
    status: DocumentStatus
    fiscal_classification: FiscalClassification
    scope: ExpenseScope
    original_filename: str
    mime_type: str
    doc_date: date | None = None
    issuer: str | None = None
    total_amount: Decimal | None = None
    payment_method: str | None = None
    document_number: str | None = None
    fiscal_year: int | None = None
    payer_user_id: uuid.UUID | None = None
    beneficiary_user_id: uuid.UUID | None = None
    reliability_note: str | None = None
    summary: str | None = None
    retention_note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
