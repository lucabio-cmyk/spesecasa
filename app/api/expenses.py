import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.deps import DB, CurrentUser
from app.enums import ExpenseScope
from app.models.expense import Expense
from app.schemas.expense import ExpenseCreate, ExpenseOut, ExpenseUpdate

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    user: CurrentUser,
    db: DB,
    fiscal_year: int | None = None,
    category: str | None = None,
    scope: ExpenseScope | None = None,
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
    for key, value in body.model_dump(exclude_none=True).items():
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
