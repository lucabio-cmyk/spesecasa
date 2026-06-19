from __future__ import annotations

import uuid

from sqlalchemy import String
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

    users: Mapped[list["User"]] = relationship(back_populates="household")
