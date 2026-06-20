import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.bill import Bill
from app.models.document import Document
from app.models.expense import Expense
from app.models.user import User

# Categoria con cui le bollette/spese di casa compaiono nelle viste aggregate
# della dashboard, così da contare *tutte* le spese senza confonderle con le
# categorie merceologiche degli scontrini.
BILLS_CATEGORY = "Bollette / casa"
# Le bollette sono spese del nucleo: nelle ripartizioni per ambito le
# attribuiamo all'ambito familiare.
BILLS_SCOPE = "familiare"


async def by_category(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    stmt = (
        select(Expense.merch_category, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.merch_category)
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)
    rows = [
        {"category": c or "n/d", "total": float(t or 0), "count": n}
        for c, t, n in res.all()
    ]

    # Aggiunge le bollette come categoria a sé, per tenere conto di tutte le spese.
    btotal, bcount = await _bills_total(db, household_id, year)
    if bcount:
        rows.append({"category": BILLS_CATEGORY, "total": btotal, "count": bcount})

    rows.sort(key=lambda r: r["total"], reverse=True)
    return rows


async def by_member(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    totals: dict[str, list] = {}

    estmt = (
        select(User.full_name, func.sum(Expense.line_amount), func.count())
        .join(Expense, Expense.payer_user_id == User.id)
        .where(Expense.household_id == household_id)
        .group_by(User.full_name)
    )
    if year:
        estmt = estmt.where(Expense.fiscal_year == year)
    for m, t, n in (await db.execute(estmt)).all():
        totals[m] = [float(t or 0), int(n or 0)]

    # Anche le bollette concorrono alla spesa del soggetto pagante (intestatario).
    bstmt = (
        select(User.full_name, func.sum(Bill.total_amount), func.count())
        .join(Bill, Bill.payer_user_id == User.id)
        .where(Bill.household_id == household_id)
        .group_by(User.full_name)
    )
    if year:
        bstmt = bstmt.where(Bill.fiscal_year == year)
    for m, t, n in (await db.execute(bstmt)).all():
        row = totals.setdefault(m, [0.0, 0])
        row[0] += float(t or 0)
        row[1] += int(n or 0)

    out = [
        {"member": m, "total": round(t, 2), "count": n}
        for m, (t, n) in totals.items()
    ]
    out.sort(key=lambda r: r["total"], reverse=True)
    return out


async def by_scope(db: AsyncSession, household_id: uuid.UUID, year: int | None = None):
    stmt = (
        select(Expense.scope, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.scope)
    )
    if year:
        stmt = stmt.where(Expense.fiscal_year == year)
    res = await db.execute(stmt)
    totals: dict[str, list] = {
        str(s): [float(t or 0), int(n or 0)] for s, t, n in res.all()
    }

    # Le bollette sono spese del nucleo: le sommiamo all'ambito familiare.
    btotal, bcount = await _bills_total(db, household_id, year)
    if bcount:
        row = totals.setdefault(BILLS_SCOPE, [0.0, 0])
        row[0] += btotal
        row[1] += bcount

    return [
        {"scope": s, "total": round(t, 2), "count": n}
        for s, (t, n) in totals.items()
    ]


async def yearly(db: AsyncSession, household_id: uuid.UUID):
    totals: dict[int, list] = {}

    estmt = (
        select(Expense.fiscal_year, func.sum(Expense.line_amount), func.count())
        .where(Expense.household_id == household_id)
        .group_by(Expense.fiscal_year)
    )
    for y, t, n in (await db.execute(estmt)).all():
        totals[y] = [float(t or 0), int(n or 0)]

    bstmt = (
        select(Bill.fiscal_year, func.sum(Bill.total_amount), func.count())
        .where(Bill.household_id == household_id)
        .group_by(Bill.fiscal_year)
    )
    for y, t, n in (await db.execute(bstmt)).all():
        row = totals.setdefault(y, [0.0, 0])
        row[0] += float(t or 0)
        row[1] += int(n or 0)

    return [
        {"year": y, "total": round(t, 2), "count": n}
        for y, (t, n) in sorted(totals.items(), key=lambda kv: (kv[0] is None, kv[0]))
    ]


async def _bills_total(
    db: AsyncSession, household_id: uuid.UUID, year: int | None = None
) -> tuple[float, int]:
    """Totale e numero delle bollette/spese di casa del nucleo."""
    stmt = select(
        func.coalesce(func.sum(Bill.total_amount), 0), func.count(Bill.id)
    ).where(Bill.household_id == household_id)
    if year:
        stmt = stmt.where(Bill.fiscal_year == year)
    total, count = (await db.execute(stmt)).one()
    return float(total or 0), int(count or 0)


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
    """KPI sintetici per la dashboard: totale speso (spese + bollette), n.
    movimenti, n. bollette, n. documenti, documenti da rivedere e totale
    potenzialmente agevolabile."""
    exp = select(
        func.coalesce(func.sum(Expense.line_amount), 0),
        func.count(Expense.id),
    ).where(Expense.household_id == household_id)
    if year:
        exp = exp.where(Expense.fiscal_year == year)
    expenses_total, lines = (await db.execute(exp)).one()

    # Le bollette/spese di casa sono archiviate a parte: le includiamo qui per
    # avere il totale di *tutte* le spese del nucleo nella dashboard.
    bills_total, bills_count = await _bills_total(db, household_id, year)

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

    expenses_total = float(expenses_total or 0)
    return {
        "total": round(expenses_total + bills_total, 2),
        "expenses_total": round(expenses_total, 2),
        "bills_total": round(bills_total, 2),
        "lines": int(lines or 0),
        "bills": int(bills_count or 0),
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
