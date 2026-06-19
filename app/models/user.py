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
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    # Rilevante a fini fiscali: la detrazione/deduzione è personale (per CF).
    codice_fiscale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    role: Mapped[UserRole] = mapped_column(enum_col(UserRole), default=UserRole.MEMBER)

    household: Mapped["Household"] = relationship(back_populates="users")
