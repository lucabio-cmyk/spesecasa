import csv
import io
import uuid
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from app.deps import DB, CurrentUser
from app.enums import BillStatus, UtilityType
from app.models.bill import Bill
from app.schemas.bill import BillCreate, BillOut, BillUpdate
from app.services import bills as bills_service

router = APIRouter(prefix="/bills", tags=["bills"])


def _derive_fiscal_year(b: Bill) -> int | None:
    """Anno fiscale: dal periodo di competenza, altrimenti dalla scadenza/emissione."""
    ref = b.period_end or b.period_start or b.issue_date or b.due_date
    return ref.year if ref else b.fiscal_year


@router.get("", response_model=list[BillOut])
async def list_bills(
    user: CurrentUser,
    db: DB,
    fiscal_year: int | None = None,
    utility_type: UtilityType | None = None,
    status: BillStatus | None = None,
):
    stmt = (
        select(Bill)
        .where(Bill.household_id == user.household_id)
        .order_by(Bill.due_date.desc().nullslast(), Bill.created_at.desc())
    )
    if fiscal_year:
        stmt = stmt.where(Bill.fiscal_year == fiscal_year)
    if utility_type:
        stmt = stmt.where(Bill.utility_type == utility_type)
    if status:
        stmt = stmt.where(Bill.status == status)
    res = await db.execute(stmt)
    return list(res.scalars())


@router.post("", response_model=BillOut, status_code=201)
async def create_bill(body: BillCreate, user: CurrentUser, db: DB):
    bill = Bill(household_id=user.household_id, **body.model_dump(exclude_none=True))
    if bill.fiscal_year is None:
        bill.fiscal_year = _derive_fiscal_year(bill)
    db.add(bill)
    await db.commit()
    await db.refresh(bill)
    return bill


@router.get("/overview")
async def overview(user: CurrentUser, db: DB, year: int | None = None):
    return await bills_service.overview(db, user.household_id, year)


@router.get("/analysis")
async def analysis(user: CurrentUser, db: DB, year: int | None = None):
    """Valutazione costi per tipo di utenza (totale, medio, costo unitario)."""
    return await bills_service.cost_analysis(db, user.household_id, year)


@router.get("/trend")
async def trend(
    user: CurrentUser,
    db: DB,
    utility_type: UtilityType | None = None,
    year: int | None = None,
):
    return await bills_service.trend(
        db, user.household_id, utility_type.value if utility_type else None, year
    )


@router.get("/upcoming")
async def upcoming(user: CurrentUser, db: DB):
    """Scadenzario: bollette scadute e in arrivo non ancora saldate."""
    return await bills_service.upcoming(db, user.household_id)


@router.get("/export.csv")
async def export_csv(user: CurrentUser, db: DB, year: int | None = None):
    """Esporta le bollette in CSV per archivio/amministrazione."""
    stmt = (
        select(Bill)
        .where(Bill.household_id == user.household_id)
        .order_by(Bill.utility_type, Bill.due_date.asc().nullslast())
    )
    if year:
        stmt = stmt.where(Bill.fiscal_year == year)
    rows = list((await db.execute(stmt)).scalars())
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        [
            "Tipo utenza", "Fornitore", "Numero", "Periodo dal", "Periodo al",
            "Scadenza", "Totale EUR", "Consumo", "Unità", "Stato", "Pagata il",
        ]
    )
    for b in rows:
        writer.writerow(
            [
                str(b.utility_type), b.supplier or "", b.bill_number or "",
                b.period_start or "", b.period_end or "", b.due_date or "",
                f"{float(b.total_amount):.2f}".replace(".", ",") if b.total_amount is not None else "",
                f"{float(b.consumption_quantity):.3f}".replace(".", ",") if b.consumption_quantity is not None else "",
                b.consumption_unit or "", str(b.status), b.paid_date or "",
            ]
        )
    suffix = f"_{year}" if year else ""
    # BOM UTF-8: Excel su Windows interpreta correttamente gli accenti (Unità, ...).
    return Response(
        content="\ufeff" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bollette{suffix}.csv"'},
    )


@router.get("/{bill_id}", response_model=BillOut)
async def get_bill(bill_id: uuid.UUID, user: CurrentUser, db: DB):
    bill = await db.get(Bill, bill_id)
    if not bill or bill.household_id != user.household_id:
        raise HTTPException(404, "Bolletta non trovata")
    return bill


@router.patch("/{bill_id}", response_model=BillOut)
async def update_bill(bill_id: uuid.UUID, body: BillUpdate, user: CurrentUser, db: DB):
    bill = await db.get(Bill, bill_id)
    if not bill or bill.household_id != user.household_id:
        raise HTTPException(404, "Bolletta non trovata")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(bill, key, value)
    if bill.fiscal_year is None:
        bill.fiscal_year = _derive_fiscal_year(bill)
    await db.commit()
    await db.refresh(bill)
    return bill


@router.post("/{bill_id}/pay", response_model=BillOut)
async def mark_paid(
    bill_id: uuid.UUID, user: CurrentUser, db: DB, paid_date: date | None = None
):
    """Segna una bolletta come pagata (amministrazione del pagato)."""
    bill = await db.get(Bill, bill_id)
    if not bill or bill.household_id != user.household_id:
        raise HTTPException(404, "Bolletta non trovata")
    bill.status = BillStatus.PAGATA
    bill.paid_date = paid_date or date.today()
    await db.commit()
    await db.refresh(bill)
    return bill


@router.delete("/{bill_id}", status_code=204)
async def delete_bill(bill_id: uuid.UUID, user: CurrentUser, db: DB):
    bill = await db.get(Bill, bill_id)
    if not bill or bill.household_id != user.household_id:
        raise HTTPException(404, "Bolletta non trovata")
    await db.delete(bill)
    await db.commit()
