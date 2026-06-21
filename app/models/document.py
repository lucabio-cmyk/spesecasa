from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.enums import DocumentStatus, DocumentType, ExpenseScope, FiscalClassification
from app.models.base import Base, TimestampMixin, enum_col


class Document(Base, TimestampMixin):
    """Documento archiviato (scontrino/fattura/ricevuta/...) con l'header dei
    dati estratti, classificazione fiscale, attribuzione e file originale."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Attribuzione fiscale: chi ha pagato e per chi.
    payer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    beneficiary_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # Metodo di pagamento usato (carta/bancomat/... intestato a un membro).
    payment_method_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_methods.id", ondelete="SET NULL"), nullable=True
    )

    doc_type: Mapped[DocumentType] = mapped_column(
        enum_col(DocumentType), default=DocumentType.ALTRO
    )
    status: Mapped[DocumentStatus] = mapped_column(
        enum_col(DocumentStatus), default=DocumentStatus.PENDING, index=True
    )
    fiscal_classification: Mapped[FiscalClassification] = mapped_column(
        enum_col(FiscalClassification), default=FiscalClassification.DA_VERIFICARE
    )
    scope: Mapped[ExpenseScope] = mapped_column(
        enum_col(ExpenseScope), default=ExpenseScope.FAMILIARE
    )

    # File originale conservato
    original_filename: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    storage_path: Mapped[str] = mapped_column(String(1000))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)  # anti-duplicazione

    # Metadati estratti (header)
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(300), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(100), nullable=True)
    document_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # Dettagli estratti aggiuntivi (per un archivio più ricco e interrogabile)
    issuer_vat: Mapped[str | None] = mapped_column(String(32), nullable=True)  # P.IVA/CF emittente
    recipient_name: Mapped[str | None] = mapped_column(String(300), nullable=True)  # intestatario
    recipient_fiscal_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    taxable_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # imponibile
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # IVA
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)  # ISO 4217, default EUR
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # scadenza pagamento
    payment_traceability: Mapped[str | None] = mapped_column(Text, nullable=True)  # rilevante per detraibilità
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # parole chiave separate da virgola
    # Dati strutturati liberi estratti dal documento (campi non previsti dallo
    # schema: es. POD/PDR, IBAN, codice tributo F24, scomposizione voci, ecc.).
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    reliability_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    retention_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Ricerca semantica (opzionale). Richiede estensione pgvector nel DB.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dim), nullable=True
    )

    expenses: Mapped[list["Expense"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
