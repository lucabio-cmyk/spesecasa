from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import PaymentMethodType
from app.models.base import Base, TimestampMixin, enum_col


class PaymentMethod(Base, TimestampMixin):
    """Metodo di pagamento di un membro del nucleo.

    Permette di censire gli strumenti con cui i membri pagano le spese: una
    carta di credito/debito, il bancomat, una prepagata, il bonifico, i contanti,
    ecc. Ogni metodo è intestato a un utente (`user_id`) e può essere collegato a
    documenti, spese e bollette per ricostruire CON QUALE strumento (e quindi da
    chi) è stata sostenuta una spesa, oltre che valutarne la tracciabilità a fini
    fiscali. È scoping per nucleo (`household_id`)."""

    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    # Intestatario dello strumento (il soggetto che paga con questo metodo).
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Nome riconoscibile scelto dall'utente (es. "Carta Visa personale",
    # "Bancomat conto cointestato", "PayPal").
    label: Mapped[str] = mapped_column(String(120))
    method_type: Mapped[PaymentMethodType] = mapped_column(
        enum_col(PaymentMethodType), default=PaymentMethodType.ALTRO
    )
    # Circuito/emittente (Visa, Mastercard, banca, ...). Facoltativo.
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Ultime 4 cifre della carta o suffisso identificativo (mai il PAN completo:
    # non si conservano dati di pagamento sensibili).
    last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Metodo predefinito dell'utente (usato quando non specificato diversamente).
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Configurazione libera aggiuntiva (chiave→valore): IBAN parziale, scadenza,
    # alias di riconoscimento nei documenti, ecc.
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    user: Mapped["User"] = relationship()
