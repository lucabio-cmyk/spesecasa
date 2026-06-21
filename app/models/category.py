from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ExpenseCategory(Base, TimestampMixin):
    """Categoria merceologica PERSONALIZZATA del nucleo.

    Le categorie "stabili" di base restano definite in
    `app.enums.MERCHANDISE_CATEGORIES`; questa tabella raccoglie solo le
    categorie aggiuntive create dall'agente (quando nessuna di quelle esistenti
    descrive bene una spesa) o dall'utente. Sono scoping per nucleo e arricchite
    con descrizione ed esempi, così la classificazione resta coerente nel tempo
    e l'archivio è più informativo. `name` è normalizzato (minuscolo, spazi
    ridotti) e unico per nucleo."""

    __tablename__ = "expense_categories"
    __table_args__ = (
        UniqueConstraint("household_id", "name", name="uq_expense_category_household_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Esempi di voci che rientrano nella categoria (lista di stringhe), utili
    # all'agente per classificare in modo coerente.
    examples: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Chi l'ha creata: "agent" (dall'analisi documenti/chat) o "user" (dalla GUI).
    source: Mapped[str] = mapped_column(String(20), default="agent")
    # Disattivata: non più proposta all'agente, ma lo storico resta valido.
    active: Mapped[bool] = mapped_column(Boolean, default=True)
