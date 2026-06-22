import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.deps import DB, AdminUser, CurrentUser
from app.enums import (
    SENSITIVE_CATEGORIES,
    ExpenseScope,
    FiscalClassification,
    UserRole,
)
from app.models.expense import Expense
from app.schemas.expense import ExpenseCreate, ExpenseOut, ExpenseUpdate
from app.services import categories as categories_service
from app.services.resolvers import (
    member_belongs_to_household,
    payment_method_belongs_to_household,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])

_SENSITIVE = list(SENSITIVE_CATEGORIES)


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    user: CurrentUser,
    db: DB,
    fiscal_year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    category: str | None = None,
    group: str | None = None,
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
    # Filtro per mese (1..12, validato da Query) sulla data di acquisto:
    # alimenta il drill-down dall'andamento mensile della dashboard/analisi.
    if month:
        stmt = stmt.where(func.extract("month", Expense.purchase_date) == month)
    if category:
        stmt = stmt.where(Expense.merch_category == category)
    # Filtro per macro-categoria (gruppo): include tutte le foglie del gruppo
    # (es. tutte le voci di reparto sotto «spesa supermercato»). Alimenta il
    # drill-down dalla vista "Spesa per categoria" della dashboard. Normalizziamo
    # il valore: le chiavi di `leaf_group` sono normalizzate (minuscolo/trim).
    if group:
        norm_group = categories_service.normalize_name(group)
        leaf_group = await categories_service.leaf_to_group(db, user.household_id)
        leaves = [leaf for leaf, grp in leaf_group.items() if grp == norm_group]
        if leaves:
            stmt = stmt.where(Expense.merch_category.in_(leaves))
        else:
            stmt = stmt.where(Expense.merch_category == norm_group)
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
    # Pagante di default: l'utente che registra la spesa, se non già indicato.
    if expense.payer_user_id is None:
        expense.payer_user_id = user.id
    # Canonicalizza la categoria (normalizza + rimappa varianti, es. 'medicinali'
    # → 'farmaci') così la riga è coerente con viste/aggregati/riservatezza.
    if expense.merch_category:
        expense.merch_category = categories_service.canonical_category(expense.merch_category)
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
    updates = body.model_dump(exclude_unset=True)
    # L'importo della riga è obbligatorio: non può essere azzerato.
    if "line_amount" in updates and updates["line_amount"] is None:
        raise HTTPException(422, "L'importo della riga è obbligatorio")
    # Questi campi sono NOT NULL nel DB: non possono essere azzerati.
    for field in ("fiscal_classification", "scope"):
        if field in updates and updates[field] is None:
            raise HTTPException(422, f"Il campo {field} non può essere nullo")
    # Isolamento dei dati: pagante/beneficiario devono appartenere al nucleo.
    for field in ("payer_user_id", "beneficiary_user_id"):
        if field in updates and not await member_belongs_to_household(
            db, user.household_id, updates[field]
        ):
            raise HTTPException(422, "Soggetto non valido per questo nucleo")
    if "payment_method_id" in updates and not await payment_method_belongs_to_household(
        db, user.household_id, updates["payment_method_id"]
    ):
        raise HTTPException(422, "Metodo di pagamento non valido per questo nucleo")
    for key, value in updates.items():
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
