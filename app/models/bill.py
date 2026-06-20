from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import BillStatus, UtilityType
from app.models.base import Base, TimestampMixin, enum_col


class Bill(Base, TimestampMixin):
    """Bolletta / spesa domestica ricorrente (luce, gas, acqua, rifiuti,
    internet, condominio, ...). Entità strutturata per la valutazione dei costi
    (consumi, costo unitario, andamento) e l'amministrazione (scadenze, stato
    di pagamento). Può essere collegata al documento da cui è stata estratta."""

    __tablename__ = "bills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Intestatario dell'utenza / soggetto che sostiene la spesa.
    payer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # Unità immobiliare a cui si riferisce la spesa (utile soprattutto per il
    # condominio quando il nucleo possiede/gestisce più unità).
    property_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("property_units.id", ondelete="SET NULL"), nullable=True, index=True
    )

    utility_type: Mapped[UtilityType] = mapped_column(
        enum_col(UtilityType), default=UtilityType.ALTRO, index=True
    )
    supplier: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Identificativo dell'utenza (POD per la luce, PDR per il gas, codice cliente).
    service_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bill_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Periodo di competenza (a cosa si riferisce il consumo fatturato).
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)

    # Importi: totale e scomposizione utile alla valutazione del costo.
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    energy_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # materia prima
    fixed_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # quote fisse/trasporto
    taxes: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # imposte/accise/IVA

    # Consumo fatturato e relativa unità (kWh, Smc, m³, ...).
    consumption_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    consumption_unit: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Amministrazione: stato di pagamento.
    status: Mapped[BillStatus] = mapped_column(
        enum_col(BillStatus), default=BillStatus.DA_PAGARE, index=True
    )
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(100), nullable=True)  # RID/domiciliazione, bonifico...

    fiscal_year: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    reliability_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Dati strutturati liberi: per il condominio l'agente vi salva l'analisi del
    # verbale/riparto (deliberazioni rilevanti, quota ordinaria/straordinaria,
    # fondo, lavori potenzialmente agevolabili, rate e relative scadenze).
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    document: Mapped["Document | None"] = relationship()
    property_unit: Mapped["PropertyUnit | None"] = relationship()
