"""Sezione "Revisione": avvisi e proposte dell'agente di orchestrazione.

L'agente gira in background e produce voci di revisione (`ReviewItem`): avvisi
quando qualcosa non è stato calcolato/gestito correttamente e proposte di
miglioramento (categorie, riclassificazioni) che si applicano SOLO previo
consenso dell'utente, qui con Approva/Rifiuta/Archivia.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import case, func, select

from app.deps import DB, CurrentUser
from app.enums import (
    REVIEW_PROPOSAL_KINDS,
    ReviewSeverity,
    ReviewStatus,
)
from app.models.review import ReviewItem
from app.schemas.review import ReviewItemOut, ReviewRunResult, ReviewSummary
from app.services import orchestrator

router = APIRouter(prefix="/review", tags=["review"])


@router.post("/run", response_model=ReviewRunResult)
async def run_review(
    user: CurrentUser,
    db: DB,
    fiscal_year: int | None = None,
    use_llm: bool | None = None,
):
    """Avvia subito una revisione completa dell'archivio (sincrona: restituisce
    l'esito con il conteggio di avvisi e proposte)."""
    result = await orchestrator.run_orchestration(
        db, user.household_id, fiscal_year=fiscal_year, use_llm=use_llm, source="manual"
    )
    return ReviewRunResult(**result)


@router.get("", response_model=list[ReviewItemOut])
async def list_review_items(
    user: CurrentUser,
    db: DB,
    status_filter: ReviewStatus | None = None,
    severity: ReviewSeverity | None = None,
    fiscal_year: int | None = None,
):
    stmt = select(ReviewItem).where(ReviewItem.household_id == user.household_id)
    # Default: mostra solo le voci ancora aperte (pending).
    stmt = stmt.where(
        ReviewItem.status == (status_filter or ReviewStatus.PENDING)
    )
    if severity:
        stmt = stmt.where(ReviewItem.severity == severity)
    if fiscal_year:
        stmt = stmt.where(ReviewItem.fiscal_year == fiscal_year)
    # Ordine: prima le più gravi, poi le più recenti.
    severity_order = case(
        (ReviewItem.severity == ReviewSeverity.CRITICAL, 0),
        (ReviewItem.severity == ReviewSeverity.WARNING, 1),
        else_=2,
    )
    stmt = stmt.order_by(severity_order.asc(), ReviewItem.created_at.desc())
    return list((await db.execute(stmt)).scalars())


@router.get("/summary", response_model=ReviewSummary)
async def review_summary(user: CurrentUser, db: DB):
    """Conteggi per il badge e l'intestazione della sezione."""
    rows = (
        await db.execute(
            select(ReviewItem.severity, ReviewItem.kind, func.count(ReviewItem.id))
            .where(
                ReviewItem.household_id == user.household_id,
                ReviewItem.status == ReviewStatus.PENDING,
            )
            .group_by(ReviewItem.severity, ReviewItem.kind)
        )
    ).all()
    summary = ReviewSummary()
    for severity, kind, n in rows:
        n = int(n)
        summary.pending += n
        sev = str(severity)
        if sev == ReviewSeverity.INFO.value:
            summary.info += n
        elif sev == ReviewSeverity.WARNING.value:
            summary.warning += n
        elif sev == ReviewSeverity.CRITICAL.value:
            summary.critical += n
        if str(kind) in REVIEW_PROPOSAL_KINDS:
            summary.proposals += n
    return summary


async def _get_item(db, household_id, item_id) -> ReviewItem:
    item = await db.get(ReviewItem, item_id)
    if not item or item.household_id != household_id:
        raise HTTPException(404, "Voce di revisione non trovata")
    return item


@router.post("/{item_id}/approve", response_model=ReviewItemOut)
async def approve_item(item_id: uuid.UUID, user: CurrentUser, db: DB):
    """Dà il consenso: applica la proposta (o prende in carico l'avviso)."""
    item = await _get_item(db, user.household_id, item_id)
    if item.status not in (ReviewStatus.PENDING, ReviewStatus.FAILED):
        raise HTTPException(409, "La voce è già stata gestita")
    result = await orchestrator.apply_review_item(db, item, user.id)
    if not result.get("ok"):
        raise HTTPException(400, result.get("error", "Impossibile applicare la proposta"))
    await db.refresh(item)
    return item


@router.post("/{item_id}/reject", response_model=ReviewItemOut)
async def reject_item(item_id: uuid.UUID, user: CurrentUser, db: DB):
    """Rifiuta la proposta: non sarà più riproposta."""
    item = await _get_item(db, user.household_id, item_id)
    item.status = ReviewStatus.REJECTED
    item.resolved_at = datetime.utcnow()
    item.resolved_by_user_id = user.id
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/{item_id}/dismiss", response_model=ReviewItemOut)
async def dismiss_item(item_id: uuid.UUID, user: CurrentUser, db: DB):
    """Archivia un avviso senza azione: non sarà più riproposto."""
    item = await _get_item(db, user.household_id, item_id)
    item.status = ReviewStatus.DISMISSED
    item.resolved_at = datetime.utcnow()
    item.resolved_by_user_id = user.id
    await db.commit()
    await db.refresh(item)
    return item
