import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.document import Document
from app.models.expense import Expense
from app.models.user import User


async def by_category(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    stmt = (
        select(Expense.merch_category, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.merch_category)
        .order_by(func.sum(Expense.line_amount).desc())
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)
    return [
        {"category": c or "n/d", "total": float(t or 0), "count": n}
        for c, t, n in res.all()
    ]


async def by_member(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    stmt = (
        select(User.full_name, func.sum(Expense.line_amount), func.count())
        .join(Expense, Expense.payer_user_id == User.id)
        .where(Expense.household_id == household_id)
        .group_by(User.full_name)
        .order_by(func.sum(Expense.line_amount).desc())
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)
    return [
        {"member": m, "total": float(t or 0), "count": n} for m, t, n in res.all()
    ]


async def by_scope(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    stmt = (
        select(Expense.scope, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.scope)
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)
    return [
        {"scope": str(s), "total": float(t or 0), "count": n} for s, t, n in res.all()
    ]


async def yearly(db: AsyncSession, household_id: uuid.UUID):
    stmt = (
        select(Expense.fiscal_year, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.fiscal_year)
        .order_by(Expense.fiscal_year)
    )
    res = await db.execute(stmt)
    return [
        {"year": y, "total": float(t or 0), "count": n} for y, t, n in res.all()
    ]


async def fiscal_summary(
    db: AsyncSession, household_id: uuid.UUID, year: int | None = None
):
    stmt = (
        select(Expense.fiscal_classification, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.fiscal_classification)
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)
    return [
        {"classification": str(c), "total": float(t or 0), "count": n}
        for c, t, n in res.all()
    ]


async def overview(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    """KPI sintetici per la dashboard: totale speso, n. movimenti, n. documenti,
    documenti da rivedere e totale potenzialmente agevolabile."""
    exp = select(
        func.coalesce(func.sum(Expense.line_amount), 0),
        func.count(Expense.id),
    ).where(Expense.household_id == household_id)
    if year:
        exp = exp.where(Expense.fiscal_year == year)
    total, lines = (await db.execute(exp)).one()

    ded = select(func.coalesce(func.sum(Expense.line_amount), 0)).where(
        Expense.household_id == household_id,
        Expense.fiscal_classification.in_(["detraibile", "deducibile"]),
    )
    if year:
        ded = ded.where(Expense.fiscal_year == year)
    deductible = (await db.execute(ded)).scalar_one()

    docs = select(func.count(Document.id)).where(Document.household_id == household_id)
    review = select(func.count(Document.id)).where(
        Document.household_id == household_id,
        Document.status.in_(["needs_review", "pending", "processing"]),
    )
    if year:
        docs = docs.where(Document.fiscal_year == year)
    docs_count = (await db.execute(docs)).scalar_one()
    review_count = (await db.execute(review)).scalar_one()

    return {
        "total": float(total or 0),
        "lines": int(lines or 0),
        "documents": int(docs_count or 0),
        "to_review": int(review_count or 0),
        "deductible_total": float(deductible or 0),
    }


async def fiscal_by_member(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    """Per l'export al commercialista: per ogni soggetto pagante e per ogni
    classificazione fiscale, totale e numero movimenti."""
    payer = aliased(User)
    stmt = (
        select(
            payer.full_name,
            payer.codice_fiscale,
            Expense.fiscal_classification,
            func.sum(Expense.line_amount),
            func.count(Expense.id),
        )
        .join(payer, Expense.payer_user_id == payer.id, isouter=True)
        .where(Expense.household_id == household_id)
        .group_by(payer.full_name, payer.codice_fiscale, Expense.fiscal_classification)
        .order_by(payer.full_name, Expense.fiscal_classification)
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)
    return [
        {
            "member": name or "Non attribuito",
            "codice_fiscale": cf or "",
            "classification": str(c),
            "total": float(t or 0),
            "count": n,
        }
        for name, cf, c, t, n in res.all()
    ]
