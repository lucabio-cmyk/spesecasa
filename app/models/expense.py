from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import ExpenseScope, FiscalClassification
from app.models.base import Base, TimestampMixin, enum_col


class Expense(Base, TimestampMixin):
    """Movimento/riga di spesa. Uno scontrino del supermercato genera molte
    righe (una per articolo, con categoria merceologica); una ricevuta singola
    genera una riga. Tabella granulare usata per le statistiche."""

    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    payer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    beneficiary_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    purchase_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(300), nullable=True)
    description_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    merch_category: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)

    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    line_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    fiscal_classification: Mapped[FiscalClassification] = mapped_column(
        enum_col(FiscalClassification), default=FiscalClassification.NON_RILEVANTE
    )
    scope: Mapped[ExpenseScope] = mapped_column(
        enum_col(ExpenseScope), default=ExpenseScope.FAMILIARE
    )
    fiscal_year: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    reliability_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document | None"] = relationship(back_populates="expenses")
