import uuid
from datetime import datetime

from pydantic import BaseModel


class ReviewItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    severity: str
    status: str
    title: str
    detail: str | None = None
    target_type: str | None = None
    target_id: uuid.UUID | None = None
    fiscal_year: int | None = None
    payload: dict | None = None
    source: str
    resolution_note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewSummary(BaseModel):
    pending: int = 0
    info: int = 0
    warning: int = 0
    critical: int = 0
    proposals: int = 0  # proposte in attesa di consenso


class ReviewRunResult(BaseModel):
    ok: bool
    checks_findings: int = 0
    proposals: int = 0
    pending_total: int = 0
    reason: str | None = None
