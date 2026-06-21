import uuid
from datetime import datetime

from pydantic import BaseModel


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None
    examples: list[str] | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    examples: list[str] | None = None
    active: bool | None = None


class CategoryOut(BaseModel):
    id: uuid.UUID
    household_id: uuid.UUID
    name: str
    description: str | None = None
    examples: list[str] | None = None
    source: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class KnownCategory(BaseModel):
    """Categoria "nota" al nucleo: una di base (builtin) oppure personalizzata."""

    name: str
    description: str | None = None
    examples: list[str] | None = None
    builtin: bool
    sensitive: bool = False
    # Presente solo per le categorie personalizzate (gestibili/eliminabili).
    id: uuid.UUID | None = None
    source: str | None = None
