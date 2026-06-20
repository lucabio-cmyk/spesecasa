from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PropertyUnit(Base, TimestampMixin):
    """Unità immobiliare del nucleo (casa, appartamento, box, ...).

    Serve a gestire meglio le spese di condominio e ad "addestrare" l'agente:
    come l'unità compare nei documenti (verbali di assemblea, riparti millesimali,
    avvisi di pagamento), l'intestatario, il nome del condominio, i millesimi.
    Quando un documento condominiale cita PIÙ unità, queste configurazioni
    permettono di attribuire correttamente la spesa all'unità del nucleo invece
    di chiedere ogni volta."""

    __tablename__ = "property_units"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    # Nome riconoscibile scelto dall'utente (es. "Casa Via Roma 10, int. 5").
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    # Come l'unità compare nei documenti: interno/scala/subalterno, codice
    # condòmino, nomi degli intestatari, ... (sinonimi separati da virgola).
    # Sono il cuore dell'"addestramento": aiutano a riconoscere l'unità nei
    # verbali e nei riparti quando l'assemblea riguarda più unità.
    aliases: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Intestatario come compare nei verbali/riparti (può differire dal membro).
    owner_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    condominium_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Quota millesimale dell'unità (per verificare i riparti di spesa).
    millesimi: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    # Unità principale: usata come default quando l'attribuzione è incerta.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Configurazione libera aggiuntiva (chiave→valore) per l'addestramento.
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
