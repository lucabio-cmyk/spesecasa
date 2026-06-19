from datetime import datetime
from enum import Enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


def enum_col(enum_cls: type[Enum], **kw) -> SAEnum:
    """Enum salvato come VARCHAR (niente tipo nativo Postgres: migrazioni più
    semplici e riutilizzo dello stesso enum su più tabelle senza conflitti)."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=50,
        values_callable=lambda e: [m.value for m in e],
        **kw,
    )
