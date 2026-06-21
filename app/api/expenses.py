import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.deps import DB, AdminUser, CurrentUser
from app.enums import (
    SENSITIVE_CATEGORIES,
    ExpenseScope,
    FiscalClassification,
    UserRole,
)
from app.models.expense import Expense
from app.schemas.expense import ExpenseCreate, ExpenseOut, ExpenseUpdate

router = APIRouter(prefix="/expenses", tags=["expenses"])

_SENSITIVE = list(SENSITIVE_CATEGORIES)


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    user: CurrentUser,
    db: DB,
    fiscal_year: int | None = None,
    category: str | None = None,
    scope: ExpenseScope | None = None,
    fiscal_classification: FiscalClassification | None = None,
    payer_user_id: uuid.UUID | None = None,
):
    stmt = (
        select(Expense)
        .where(Expense.household_id == user.household_id)
        .order_by(Expense.purchase_date.desc().nullslast())
    )
    if fiscal_year:
        stmt = stmt.where(Expense.fiscal_year == fiscal_year)
    if category:
        stmt = stmt.where(Expense.merch_category == category)
    if scope:
        stmt = stmt.where(Expense.scope == scope)
    if fiscal_classification:
        stmt = stmt.where(Expense.fiscal_classification == fiscal_classification)
    if payer_user_id:
        stmt = stmt.where(Expense.payer_user_id == payer_user_id)
    # I farmaci sono dati sanitari sensibili: il loro dettaglio è riservato agli
    # amministratori. Per gli altri membri nascondiamo queste righe (l'OR con
    # is_(None) conserva le righe senza categoria e mantiene l'uso dell'indice).
    if user.role != UserRole.ADMIN:
        stmt = stmt.where(
            Expense.merch_category.notin_(_SENSITIVE)
            | Expense.merch_category.is_(None)
        )
    res = await db.execute(stmt)
    return list(res.scalars())


@router.get("/farmaci", response_model=list[ExpenseOut])
async def list_farmaci(
    user: AdminUser,
    db: DB,
    fiscal_year: int | None = None,
    beneficiary_user_id: uuid.UUID | None = None,
):
    """Catalogo dei FARMACI acquistati dal nucleo (categoria 'farmaci'),
    riservato agli amministratori: dato sanitario sensibile. Ogni riga porta in
    'details' i dati del farmaco riconosciuti dallo scontrino parlante e dalla
    ricerca online del codice (AIC/minsan): nome, principio attivo, ATC."""
    stmt = (
        select(Expense)
        .where(
            Expense.household_id == user.household_id,
            Expense.merch_category.in_(_SENSITIVE),
        )
        .order_by(Expense.purchase_date.desc().nullslast())
    )
    if fiscal_year:
        stmt = stmt.where(Expense.fiscal_year == fiscal_year)
    if beneficiary_user_id:
        stmt = stmt.where(Expense.beneficiary_user_id == beneficiary_user_id)
    res = await db.execute(stmt)
    return list(res.scalars())


@router.post("", response_model=ExpenseOut, status_code=201)
async def create_expense(body: ExpenseCreate, user: CurrentUser, db: DB):
    expense = Expense(household_id=user.household_id, **body.model_dump(exclude_none=True))
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    return expense


@router.patch("/{expense_id}", response_model=ExpenseOut)
async def update_expense(expense_id: uuid.UUID, body: ExpenseUpdate, user: CurrentUser, db: DB):
    expense = await db.get(Expense, expense_id)
    if not expense or expense.household_id != user.household_id:
        raise HTTPException(404, "Spesa non trovata")
    # exclude_unset: aggiorna solo i campi inviati, consentendo di azzerare
    # esplicitamente a null campi opzionali (es. payer/beneficiary).
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(expense, key, value)
    await db.commit()
    await db.refresh(expense)
    return expense


@router.delete("/{expense_id}", status_code=204)
async def delete_expense(expense_id: uuid.UUID, user: CurrentUser, db: DB):
    expense = await db.get(Expense, expense_id)
    if not expense or expense.household_id != user.household_id:
        raise HTTPException(404, "Spesa non trovata")
    await db.delete(expense)
    await db.commit()
