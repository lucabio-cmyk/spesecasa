import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from sqlalchemy import select

from app.database import SessionLocal
from app.deps import DB, CurrentUser
from app.enums import DocumentStatus, DocumentType
from app.models.document import Document
from app.models.expense import Expense
from app.schemas.document import DocumentOut, DocumentSearchHit
from app.schemas.expense import ExpenseOut
from app.services import search as search_service
from app.services.storage import file_hash, get_storage

router = APIRouter(prefix="/documents", tags=["documents"])


async def _process(document_id: uuid.UUID) -> None:
    # Import locale per evitare l'inizializzazione del client Anthropic all'avvio.
    from app.agent.runner import process_document

    async with SessionLocal() as db:
        doc = await db.get(Document, document_id)
        if doc:
            await process_document(db, doc)


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    user: CurrentUser,
    db: DB,
    bg: BackgroundTasks,
    response: Response,
    file: UploadFile = File(...),
    note: str | None = Form(None),
):
    """Carica un documento (scontrino/fattura/...). Salva il file e avvia in
    background l'elaborazione dell'agente.

    Verifica anti-duplicazione: se lo stesso file (identico hash) è già presente
    nell'archivio del nucleo, NON viene ricaricato; si risponde 200 con il
    documento esistente e l'header `X-Document-Duplicate: 1`."""
    data = await file.read()
    digest = file_hash(data)

    dup = await db.execute(
        select(Document).where(
            Document.household_id == user.household_id,
            Document.file_hash == digest,
        )
    )
    existing = dup.scalars().first()
    if existing:
        response.status_code = status.HTTP_200_OK
        response.headers["X-Document-Duplicate"] = "1"
        return existing

    # Sanifica il nome file per evitare path traversal (es. "../../evil"):
    # si conserva solo il basename, normalizzando anche i separatori Windows.
    safe_name = Path((file.filename or "documento").replace("\\", "/")).name or "documento"
    year = datetime.now(timezone.utc).year
    rel = f"{user.household_id}/{year}/{digest[:16]}_{safe_name}"
    path = get_storage().save(rel, data)

    doc = Document(
        household_id=user.household_id,
        uploaded_by_user_id=user.id,
        original_filename=file.filename or "documento",
        mime_type=file.content_type or "application/octet-stream",
        storage_path=path,
        file_hash=digest,
        status=DocumentStatus.PENDING,
        retention_note=note,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    bg.add_task(_process, doc.id)
    return doc


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    user: CurrentUser,
    db: DB,
    fiscal_year: int | None = None,
    doc_type: DocumentType | None = None,
    status: DocumentStatus | None = None,
):
    stmt = (
        select(Document)
        .where(Document.household_id == user.household_id)
        .order_by(Document.created_at.desc())
    )
    if fiscal_year:
        stmt = stmt.where(Document.fiscal_year == fiscal_year)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if status:
        stmt = stmt.where(Document.status == status)
    res = await db.execute(stmt)
    return list(res.scalars())


@router.get("/search", response_model=list[DocumentSearchHit])
async def search_documents(
    user: CurrentUser,
    db: DB,
    response: Response,
    q: str,
    limit: int = 20,
):
    """Ricerca nell'archivio per significato (semantica, pgvector cosine) con
    fallback automatico alle parole chiave. L'header `X-Search-Mode` indica la
    modalità effettiva (`semantic` | `keyword` | `empty`)."""
    hits, mode = await search_service.search_documents(db, user.household_id, q, limit)
    response.headers["X-Search-Mode"] = mode
    results: list[DocumentSearchHit] = []
    for doc, score in hits:
        hit = DocumentSearchHit.model_validate(doc)
        hit.score = score
        results.append(hit)
    return results


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, user: CurrentUser, db: DB):
    doc = await db.get(Document, document_id)
    if not doc or doc.household_id != user.household_id:
        raise HTTPException(404, "Documento non trovato")
    return doc


@router.get("/{document_id}/file")
async def get_document_file(document_id: uuid.UUID, user: CurrentUser, db: DB):
    doc = await db.get(Document, document_id)
    if not doc or doc.household_id != user.household_id:
        raise HTTPException(404, "Documento non trovato")
    data = get_storage().read(doc.storage_path)
    return Response(
        content=data,
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'inline; filename="{doc.original_filename}"'},
    )


@router.get("/{document_id}/expenses", response_model=list[ExpenseOut])
async def document_expenses(document_id: uuid.UUID, user: CurrentUser, db: DB):
    """Righe/movimenti collegati a un documento (dettaglio scontrino)."""
    doc = await db.get(Document, document_id)
    if not doc or doc.household_id != user.household_id:
        raise HTTPException(404, "Documento non trovato")
    res = await db.execute(
        select(Expense)
        .where(Expense.document_id == document_id)
        .order_by(Expense.created_at)
    )
    return list(res.scalars())


@router.post("/{document_id}/reprocess", response_model=DocumentOut)
async def reprocess(document_id: uuid.UUID, user: CurrentUser, db: DB, bg: BackgroundTasks):
    doc = await db.get(Document, document_id)
    if not doc or doc.household_id != user.household_id:
        raise HTTPException(404, "Documento non trovato")
    doc.status = DocumentStatus.PENDING
    await db.commit()
    bg.add_task(_process, doc.id)
    await db.refresh(doc)
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, user: CurrentUser, db: DB):
    """Elimina un documento, le sue righe collegate e il file originale."""
    doc = await db.get(Document, document_id)
    if not doc or doc.household_id != user.household_id:
        raise HTTPException(404, "Documento non trovato")
    try:
        get_storage().delete(doc.storage_path)
    except Exception:
        pass  # il record viene comunque rimosso
    await db.delete(doc)
    await db.commit()
