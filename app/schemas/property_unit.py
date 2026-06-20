import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PropertyUnitBase(BaseModel):
    name: str
    address: str | None = None
    aliases: str | None = None
    owner_name: str | None = None
    condominium_name: str | None = None
    millesimi: Decimal | None = None
    is_primary: bool = False
    notes: str | None = None
    details: dict | None = None


class PropertyUnitCreate(PropertyUnitBase):
    pass


class PropertyUnitUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    aliases: str | None = None
    owner_name: str | None = None
    condominium_name: str | None = None
    millesimi: Decimal | None = None
    is_primary: bool | None = None
    notes: str | None = None
    details: dict | None = None


class PropertyUnitOut(PropertyUnitBase):
    id: uuid.UUID
    household_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class HouseholdSettingsUpdate(BaseModel):
    """Aggiornamento delle impostazioni del nucleo (solo admin)."""

    name: str | None = None
    agent_instructions: str | None = None
