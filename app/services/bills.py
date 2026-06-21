import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import UtilityType
from app.models.bill import Bill

# Stati che indicano una bolletta ancora da saldare.
_OPEN_STATUSES = ("da_pagare", "scaduta", "rateizzata")


async def _cost_agg(
    db: AsyncSession,
    household_id: uuid.UUID,
    year: int | None,
    unit_id: uuid.UUID | None,
) -> dict[str, dict]:
    """Aggregati di costo/consumo per tipo di utenza (chiave = utility_type)."""
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
    )
    if year:
        stmt = stmt.where(Bill.fiscal_year == year)
    if unit_id:
        stmt = stmt.where(Bill.property_unit_id == unit_id)
    res = await db.execute(stmt)
    agg: dict[str, dict] = {}
    for utype, total, count, avg, consumption, unit in res.all():
        total_f = float(total or 0)
        cons_f = float(consumption or 0)
        agg[str(utype)] = {
            "total": total_f,
            "count": int(count or 0),
            "avg_amount": float(avg or 0),
            "consumption": cons_f,
            "consumption_unit": unit or "",
            "unit_cost": round(total_f / cons_f, 4) if cons_f else None,
        }
    return agg


def _pct_change(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


async def cost_analysis(
    db: AsyncSession,
    household_id: uuid.UUID,
    year: int | None = None,
    unit_id: uuid.UUID | None = None,
) -> list[dict]:
    """Valutazione costi per tipo di utenza: totale, n. bollette, importo medio,
    consumo totale e costo unitario medio (€/unità) quando il consumo è noto.
    Se è indicato un anno, aggiunge il confronto con l'anno precedente (spesa,
    consumo e costo unitario) per evidenziare rincari e consumi anomali."""
    current = await _cost_agg(db, household_id, year, unit_id)
    prev = await _cost_agg(db, household_id, year - 1, unit_id) if year else {}

    out = []
    for utype, cur in current.items():
        row = {"utility_type": utype, **cur}
        if year:
            p = prev.get(utype)
            row["prev_total"] = round(p["total"], 2) if p else 0.0
            row["total_delta_pct"] = _pct_change(cur["total"], p["total"]) if p else None
            row["prev_unit_cost"] = p["unit_cost"] if p else None
            row["unit_cost_delta_pct"] = (
                _pct_change(cur["unit_cost"], p["unit_cost"])
                if p and p.get("unit_cost") and cur.get("unit_cost")
                else None
            )
            row["prev_consumption"] = round(p["consumption"], 3) if p else 0.0
            row["consumption_delta_pct"] = (
                _pct_change(cur["consumption"], p["consumption"])
                if p and p["consumption"]
                else None
            )
        out.append(row)
    out.sort(key=lambda r: r["total"], reverse=True)
    return out


async def monthly(
    db: AsyncSession,
    household_id: uuid.UUID,
    year: int,
    unit_id: uuid.UUID | None = None,
) -> list[dict]:
    """Andamento mensile delle bollette dell'anno indicato (gen→dic): totale e
    numero per mese, utile a leggere la stagionalità di luce/gas/riscaldamento."""
    ref = func.coalesce(
        Bill.period_end, Bill.issue_date, Bill.due_date, Bill.period_start
    )
    bmonth = func.extract("month", ref)
    stmt = (
        select(bmonth, func.coalesce(func.sum(Bill.total_amount), 0), func.count(Bill.id))
        .where(Bill.household_id == household_id, Bill.fiscal_year == year)
        .group_by(bmonth)
    )
    if unit_id:
        stmt = stmt.where(Bill.property_unit_id == unit_id)
    totals = {m: [0.0, 0] for m in range(1, 13)}
    for m, total, count in (await db.execute(stmt)).all():
        if m is None:
            continue
        totals[int(m)] = [float(total or 0), int(count or 0)]
    return [
        {"month": m, "total": round(totals[m][0], 2), "count": totals[m][1]}
        for m in range(1, 13)
    ]


async def trend(
    db: AsyncSession,
    household_id: uuid.UUID,
    utility_type: str | None = None,
    year: int | None = None,
    unit_id: uuid.UUID | None = None,
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
    if unit_id:
        stmt = stmt.where(Bill.property_unit_id == unit_id)
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
    db: AsyncSession,
    household_id: uuid.UUID,
    limit: int = 50,
    unit_id: uuid.UUID | None = None,
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
    if unit_id:
        stmt = stmt.where(Bill.property_unit_id == unit_id)
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
    """KPI sintetici per la dashboard delle spese di casa. Le spese di
    CONDOMINIO sono tenute distinte dalle bollette delle utenze (luce, gas,
    acqua, ...): hanno natura diversa (quote ordinarie/straordinarie, lavori)
    e vanno mostrate come categoria a sé nella dashboard."""
    # Totali divisi per "condominio" vs resto (utenze), in un'unica query.
    split_stmt = select(
        Bill.utility_type,
        func.coalesce(func.sum(Bill.total_amount), 0),
        func.count(Bill.id),
    ).where(Bill.household_id == household_id).group_by(Bill.utility_type)
    if year:
        split_stmt = split_stmt.where(Bill.fiscal_year == year)
    utilities_total, utilities_count = 0.0, 0
    condo_total, condo_count = 0.0, 0
    for utype, total, count in (await db.execute(split_stmt)).all():
        if utype == UtilityType.CONDOMINIO:
            condo_total += float(total or 0)
            condo_count += int(count or 0)
        else:
            utilities_total += float(total or 0)
            utilities_count += int(count or 0)

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
        # totale complessivo (utenze + condominio): retrocompatibile
        "total": round(utilities_total + condo_total, 2),
        "count": utilities_count + condo_count,
        # bollette delle utenze (escluso condominio)
        "utilities_total": round(utilities_total, 2),
        "utilities_count": utilities_count,
        # spese condominiali, distinte
        "condo_total": round(condo_total, 2),
        "condo_count": condo_count,
        "open_total": float(open_total or 0),
        "open_count": int(open_count or 0),
        "overdue_count": int(overdue_count or 0),
    }
