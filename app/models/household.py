from __future__ import annotations

import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Household(Base, TimestampMixin):
    """Nucleo familiare: contenitore di utenti, documenti e spese."""

    __tablename__ = "households"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200))
    # Istruzioni libere per "addestrare" l'agente sul nucleo: convenzioni,
    # preferenze di classificazione, come trattare casi ricorrenti (es. quale
    # unità immobiliare considerare per il condominio). Vengono iniettate nel
    # system prompt dell'agente. Configurabili dalla GUI (Impostazioni).
    agent_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    users: Mapped[list["User"]] = relationship(back_populates="household")
