import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.user import User


def to_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def to_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None


async def resolve_member_id(
    db: AsyncSession, household_id: uuid.UUID, name_or_id
) -> uuid.UUID | None:
    """Risolve un membro del nucleo da uuid oppure da nome (match parziale)."""
    if not name_or_id:
        return None
    # Prova come UUID
    try:
        candidate = uuid.UUID(str(name_or_id))
        user = await db.get(User, candidate)
        if user and user.household_id == household_id:
            return user.id
    except (ValueError, AttributeError):
        pass
    # Match per nome
    needle = str(name_or_id).strip().lower()
    res = await db.execute(select(User).where(User.household_id == household_id))
    for user in res.scalars():
        if needle and needle in user.full_name.lower():
            return user.id
    return None


async def find_existing_document(
    db: AsyncSession,
    household_id: uuid.UUID,
    *,
    file_hash: str | None = None,
    doc_date: date | None = None,
    issuer: str | None = None,
    total_amount: Decimal | None = None,
) -> Document | None:
    """Anti-duplicazione: stesso file (hash) oppure stessa terna data+emittente+importo."""
    base = select(Document).where(Document.household_id == household_id)
    if file_hash:
        res = await db.execute(base.where(Document.file_hash == file_hash))
        found = res.scalars().first()
        if found:
            return found
    if doc_date and issuer and total_amount is not None:
        res = await db.execute(
            base.where(
                Document.doc_date == doc_date,
                Document.issuer == issuer,
                Document.total_amount == total_amount,
            )
        )
        return res.scalars().first()
    return None
