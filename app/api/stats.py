import csv
import io
from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response

from app.deps import DB, CurrentUser
from app.enums import SENSITIVE_CATEGORIES, UserRole
from app.services import stats as stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


def _is_admin(user) -> bool:
    return user.role == UserRole.ADMIN


@router.get("/overview")
async def overview(user: CurrentUser, db: DB, year: int | None = None):
    return await stats_service.overview(db, user.household_id, year)


@router.get("/by-category")
async def by_category(user: CurrentUser, db: DB, year: int | None = None):
    rows = await stats_service.by_category(db, user.household_id, year)
    # La categoria "farmaci" è un dato sanitario sensibile: ai non-amministratori
    # non mostriamo nemmeno l'aggregato per categoria.
    if user.role != UserRole.ADMIN:
        rows = [r for r in rows if r["category"] not in SENSITIVE_CATEGORIES]
    return rows


@router.get("/by-member")
async def by_member(user: CurrentUser, db: DB, year: int | None = None):
    return await stats_service.by_member(db, user.household_id, year)


@router.get("/by-scope")
async def by_scope(user: CurrentUser, db: DB, year: int | None = None):
    return await stats_service.by_scope(db, user.household_id, year)


@router.get("/yearly")
async def yearly(user: CurrentUser, db: DB):
    return await stats_service.yearly(db, user.household_id)


@router.get("/fiscal-summary")
async def fiscal_summary(user: CurrentUser, db: DB, year: int | None = None):
    return await stats_service.fiscal_summary(db, user.household_id, year)


@router.get("/fiscal-by-member")
async def fiscal_by_member(user: CurrentUser, db: DB, year: int | None = None):
    return await stats_service.fiscal_by_member(db, user.household_id, year)


@router.get("/monthly")
async def monthly(user: CurrentUser, db: DB, year: int | None = None):
    """Andamento mensile (gen→dic) di spese e bollette per l'anno indicato
    (default: anno corrente)."""
    return await stats_service.monthly(db, user.household_id, year or date.today().year)


@router.get("/top-merchants")
async def top_merchants(
    user: CurrentUser, db: DB, year: int | None = None, limit: int = 10
):
    """Esercenti/fornitori su cui si spende di più. Ai non-amministratori non
    espone le righe della categoria sensibile farmaci."""
    limit = max(1, min(limit, 50))
    return await stats_service.top_merchants(
        db, user.household_id, year, limit, _is_admin(user)
    )


@router.get("/compare")
async def compare(user: CurrentUser, db: DB, year: int | None = None):
    """Confronto dell'anno (default: corrente) con il precedente, per categoria."""
    return await stats_service.compare_years(
        db, user.household_id, year or date.today().year, _is_admin(user)
    )


@router.get("/insights")
async def insights(user: CurrentUser, db: DB, year: int | None = None):
    """Osservazioni automatiche sulla situazione di spesa del nucleo."""
    return await stats_service.insights(
        db, user.household_id, year or date.today().year, _is_admin(user)
    )


@router.get("/export.csv")
async def export_csv(user: CurrentUser, db: DB, year: int | None = None):
    """Esporta il riepilogo per soggetto e classificazione fiscale in CSV,
    pronto per il commercialista. Solo aggregazione: nessun calcolo d'imposta."""
    rows = await stats_service.fiscal_by_member(db, user.household_id, year)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Soggetto", "Codice fiscale", "Classificazione fiscale", "Totale EUR", "N. movimenti"])
    for r in rows:
        writer.writerow([
            r["member"],
            r["codice_fiscale"],
            r["classification"],
            f"{r['total']:.2f}".replace(".", ","),
            r["count"],
        ])
    suffix = f"_{year}" if year else ""
    filename = f"riepilogo_fiscale{suffix}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
