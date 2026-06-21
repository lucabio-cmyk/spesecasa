from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import ReviewKind, ReviewSeverity, ReviewStatus
from app.models.base import Base, TimestampMixin, enum_col


class ReviewItem(Base, TimestampMixin):
    """Voce prodotta dall'agente di orchestrazione in background.

    Raccoglie due cose: (1) AVVISI quando qualcosa non torna o non è stato
    gestito correttamente (righe che non quadrano col totale, righe non
    calcolate, attribuzioni/classificazioni mancanti, possibili duplicati,
    elaborazioni fallite); (2) PROPOSTE che migliorano l'archivio (nuove
    categorie, riclassificazioni, attribuzioni) da applicare SOLO previo
    consenso dell'utente.

    Il `payload` JSONB descrive — per le proposte — l'azione applicabile quando
    l'utente approva (es. creare una categoria, riclassificare una spesa). La
    `signature` è una firma deterministica usata per non duplicare lo stesso
    avviso/proposta a ogni esecuzione."""

    __tablename__ = "review_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[ReviewKind] = mapped_column(enum_col(ReviewKind), index=True)
    severity: Mapped[ReviewSeverity] = mapped_column(
        enum_col(ReviewSeverity), default=ReviewSeverity.INFO, index=True
    )
    status: Mapped[ReviewStatus] = mapped_column(
        enum_col(ReviewStatus), default=ReviewStatus.PENDING, index=True
    )

    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Firma deterministica per evitare doppioni dello stesso avviso/proposta.
    signature: Mapped[str | None] = mapped_column(String(200), index=True, nullable=True)

    # Oggetto a cui si riferisce (document/expense/bill/category) — facoltativo.
    target_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)

    # Azione applicabile (per le proposte) e dati di contesto dell'avviso.
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Chi/cosa l'ha generata: "auto" (deterministico), "agent" (LLM), "manual".
    source: Mapped[str] = mapped_column(String(20), default="auto")

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # Esito dell'eventuale applicazione (messaggio leggibile).
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
