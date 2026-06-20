import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import UtilityType
from app.models.bill import Bill

# Stati che indicano una bolletta ancora da saldare.
_OPEN_STATUSES = ("da_pagare", "scaduta", "rateizzata")


async def cost_analysis(
    db: AsyncSession, household_id: uuid.UUID, year: int | None = None
) -> list[dict]:
    """Valutazione costi per tipo di utenza: totale, n. bollette, importo medio,
    consumo totale e costo unitario medio (€/unità) quando il consumo è noto."""
    stmt = (
        select(
            Bill.utility_type,
            func.coalesce(func.sum(Bill.total_amount), 0),
            func.count(Bill.id),
            func.avg(Bill.total_amount),
            func.coalesce(func.sum(Bill.consumption_quantity), 0),
            func.max(Bill.consumption_unit),
        )
        .where(Bill.household_id == household_id)
        .group_by(Bill.utility_type)
        .order_by(func.sum(Bill.total_amount).desc())
    )
    if year:
        stmt = stmt.where(Bill.fiscal_year == year)
    res = await db.execute(stmt)
    out = []
    for utype, total, count, avg, consumption, unit in res.all():
        total_f = float(total or 0)
        cons_f = float(consumption or 0)
        out.append(
            {
                "utility_type": str(utype),
                "total": total_f,
                "count": int(count or 0),
                "avg_amount": float(avg or 0),
                "consumption": cons_f,
                "consumption_unit": unit or "",
                # Costo unitario medio sul periodo (solo se c'è consumo misurato).
                "unit_cost": round(total_f / cons_f, 4) if cons_f else None,
            }
        )
    return out


async def trend(
    db: AsyncSession,
    household_id: uuid.UUID,
    utility_type: str | None = None,
    year: int | None = None,
) -> list[dict]:
    """Andamento dei costi nel tempo, per anno fiscale e tipo di utenza.
    Utile a confrontare i periodi e individuare rincari o consumi anomali."""
    stmt = (
        select(
            Bill.fiscal_year,
            Bill.utility_type,
            func.coalesce(func.sum(Bill.total_amount), 0),
            func.coalesce(func.sum(Bill.consumption_quantity), 0),
            func.count(Bill.id),
        )
        .where(Bill.household_id == household_id)
        .group_by(Bill.fiscal_year, Bill.utility_type)
        .order_by(Bill.fiscal_year, Bill.utility_type)
    )
    if utility_type:
        stmt = stmt.where(Bill.utility_type == utility_type)
    if year:
        stmt = stmt.where(Bill.fiscal_year == year)
    res = await db.execute(stmt)
    return [
        {
            "year": fy,
            "utility_type": str(utype),
            "total": float(total or 0),
            "consumption": float(cons or 0),
            "count": int(count or 0),
        }
        for fy, utype, total, cons, count in res.all()
    ]


async def upcoming(
    db: AsyncSession, household_id: uuid.UUID, limit: int = 50
) -> dict:
    """Scadenzario: bollette non saldate, separando le scadute da quelle in
    arrivo. Cuore della parte amministrativa."""
    today = date.today()
    stmt = (
        select(Bill)
        .where(
            Bill.household_id == household_id,
            Bill.status.in_(_OPEN_STATUSES),
        )
        .order_by(Bill.due_date.asc().nullslast())
        .limit(limit)
    )
    res = await db.execute(stmt)
    bills = list(res.scalars())
    overdue, due_soon = [], []
    total_open = 0.0
    for b in bills:
        amount = float(b.total_amount or 0)
        total_open += amount
        row = {
            "id": str(b.id),
            "utility_type": str(b.utility_type),
            "supplier": b.supplier,
            "due_date": b.due_date.isoformat() if b.due_date else None,
            "total_amount": amount,
            "status": str(b.status),
        }
        if b.due_date and b.due_date < today:
            row["days_overdue"] = (today - b.due_date).days
            overdue.append(row)
        else:
            if b.due_date:
                row["days_left"] = (b.due_date - today).days
            due_soon.append(row)
    return {
        "overdue": overdue,
        "due_soon": due_soon,
        "open_count": len(bills),
        "open_total": round(total_open, 2),
    }


async def overview(
    db: AsyncSession, household_id: uuid.UUID, year: int | None = None
) -> dict:
    """KPI sintetici per la dashboard delle spese di casa."""
    base = select(
        func.coalesce(func.sum(Bill.total_amount), 0), func.count(Bill.id)
    ).where(Bill.household_id == household_id)
    if year:
        base = base.where(Bill.fiscal_year == year)
    total, count = (await db.execute(base)).one()

    open_stmt = select(
        func.coalesce(func.sum(Bill.total_amount), 0), func.count(Bill.id)
    ).where(
        Bill.household_id == household_id,
        Bill.status.in_(_OPEN_STATUSES),
    )
    open_total, open_count = (await db.execute(open_stmt)).one()

    overdue_stmt = select(func.count(Bill.id)).where(
        Bill.household_id == household_id,
        Bill.status.in_(_OPEN_STATUSES),
        Bill.due_date < date.today(),
    )
    overdue_count = (await db.execute(overdue_stmt)).scalar_one()

    return {
        "total": float(total or 0),
        "count": int(count or 0),
        "open_total": float(open_total or 0),
        "open_count": int(open_count or 0),
        "overdue_count": int(overdue_count or 0),
    }
