from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import UserRole
from app.models.base import Base, TimestampMixin, enum_col


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    # Email e password sono opzionali: un familiare può esistere come semplice
    # soggetto (per attribuire spese/documenti) SENZA accesso all'app. Hanno
    # entrambi un valore solo per i membri con accesso (login). L'unicità
    # dell'email vale solo quando è valorizzata (Postgres ammette più NULL).
    email: Mapped[str | None] = mapped_column(
        String(320), unique=True, index=True, nullable=True
    )
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200))
    # Rilevante a fini fiscali: la detrazione/deduzione è personale (per CF).
    codice_fiscale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    role: Mapped[UserRole] = mapped_column(enum_col(UserRole), default=UserRole.MEMBER)

    household: Mapped["Household"] = relationship(back_populates="users")
