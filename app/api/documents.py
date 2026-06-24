import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from sqlalchemy import delete, select

from app.database import SessionLocal
from app.deps import DB, AdminUser, CurrentUser
from app.enums import DocumentStatus, DocumentType
from app.models.document import Document
from app.models.expense import Expense
from app.models.bill import Bill
from app.schemas.document import (
    DocumentOut,
    DocumentSearchHit,
    DocumentUpdate,
    ReorganizeResult,
    ReprocessRequest,
)
from app.schemas.expense import ExpenseOut
from app.services import archive as archive_service
from app.services import search as search_service
from app.services.resolvers import (
    member_belongs_to_household,
    payment_method_belongs_to_household,
)
from app.services.spreadsheets import normalize_mime
from app.services.storage import file_hash, get_storage

router = APIRouter(prefix="/documents", tags=["documents"])


async def _process(
    document_id: uuid.UUID, extra_instruction: str | None = None
) -> None:
    # Import locale per evitare l'inizializzazione del client Anthropic all'avvio.
    from app.agent.runner import process_document
    from app.config import settings as _settings

    household_id = None
    async with SessionLocal() as db:
        doc = await db.get(Document, document_id)
        if doc:
            household_id = doc.household_id
            await process_document(db, doc, extra_instruction=extra_instruction)

    # A elaborazione conclusa, l'agente di orchestrazione verifica il documento
    # (righe ↔ totale, classificazione, attribuzione) e segnala ciò che non è
    # stato calcolato/gestito correttamente. Best-effort: non deve far fallire
    # l'upload.
    if (
        household_id is not None
        and _settings.enable_orchestrator
        and _settings.orchestrator_run_after_upload
    ):
        from app.services import orchestrator

        async with SessionLocal() as db:
            try:
                await orchestrator.run_orchestration(
                    db, household_id, document_id=document_id, use_llm=False
                )
            except Exception:
                await db.rollback()


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
    # Posizione di atterraggio temporanea: l'archivio "ordinato" (per anno/tipo
    # con nome parlante) viene costruito a fine elaborazione dall'agente
    # (app/services/archive.py). Finché un documento non è elaborato (o se
    # fallisce) resta qui, nell'inbox, chiaramente separato dall'archivio pulito.
    year = datetime.now(timezone.utc).year
    rel = f"{user.household_id}/_inbox/{year}/{digest[:16]}_{safe_name}"
    path = get_storage().save(rel, data)

    # Normalizza il MIME: alcuni browser inviano i fogli Excel come
    # octet-stream; lo deduciamo dall'estensione per riconoscerli poi.
    mime_type = normalize_mime(file.filename, file.content_type)
    doc = Document(
        household_id=user.household_id,
        uploaded_by_user_id=user.id,
        # Chi carica il documento è il pagante di default: l'agente lo conferma o
        # lo corregge solo se dal documento emerge un altro soggetto pagante.
        payer_user_id=user.id,
        original_filename=file.filename or "documento",
        mime_type=mime_type,
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


@router.patch("/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: uuid.UUID, body: DocumentUpdate, user: CurrentUser, db: DB
):
    """Correzione manuale dei campi di un documento (diciture, importi,
    classificazione e attribuzione). Aggiorna solo i campi inviati."""
    doc = await db.get(Document, document_id)
    if not doc or doc.household_id != user.household_id:
        raise HTTPException(404, "Documento non trovato")
    # exclude_unset: aggiorna solo i campi inviati, consentendo di azzerare
    # esplicitamente a null i campi opzionali (es. payer/beneficiary).
    updates = body.model_dump(exclude_unset=True)
    # Questi campi sono NOT NULL nel DB: non possono essere azzerati.
    for field in ("doc_type", "fiscal_classification", "scope"):
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
        setattr(doc, key, value)
    await db.commit()
    await db.refresh(doc)
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
async def reprocess(
    document_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    bg: BackgroundTasks,
    body: ReprocessRequest | None = None,
):
    """Rielabora un documento. Accetta istruzioni libere opzionali
    (`instruction`) che guidano l'agente in questa elaborazione. Le righe e le
    bollette già estratte dal documento vengono rimosse prima della
    rielaborazione, così l'estrazione riparte pulita senza duplicati."""
    doc = await db.get(Document, document_id)
    if not doc or doc.household_id != user.household_id:
        raise HTTPException(404, "Documento non trovato")
    # Evita race condition tra task in background: se è già in coda o in
    # elaborazione, non avviare una seconda rielaborazione.
    if doc.status in (DocumentStatus.PENDING, DocumentStatus.PROCESSING):
        raise HTTPException(409, "Il documento è già in coda o in elaborazione")
    # Pulizia dei dati derivati dal documento per evitare duplicati: l'agente
    # ri-estrae da capo righe e bollette.
    await db.execute(delete(Expense).where(Expense.document_id == doc.id))
    await db.execute(delete(Bill).where(Bill.document_id == doc.id))
    doc.status = DocumentStatus.PENDING
    await db.commit()
    instruction = body.instruction if body else None
    bg.add_task(_process, doc.id, instruction)
    await db.refresh(doc)
    return doc


@router.post("/reorganize", response_model=ReorganizeResult)
async def reorganize_archive(user: AdminUser, db: DB):
    """Riordina l'archivio ESISTENTE: sposta e rinomina i documenti già
    elaborati nella struttura ordinata (anno/tipo + nome parlante), senza
    richiamare l'agente. Utile per allineare lo storico caricato prima
    dell'introduzione dell'archivio ordinato. Riservato all'amministratore.

    Best-effort e idempotente: i file già al posto giusto non si muovono, un
    errore di I/O su un documento non blocca gli altri (il file resta dov'era)."""
    storage = get_storage()
    res = await db.execute(
        select(Document).where(
            Document.household_id == user.household_id,
            Document.status.in_(
                [DocumentStatus.COMPLETE, DocumentStatus.NEEDS_REVIEW]
            ),
        )
    )
    examined = moved = skipped = errors = 0
    for doc in res.scalars():
        examined += 1
        if not doc.storage_path:
            skipped += 1
            continue
        try:
            new_abs = storage.move(doc.storage_path, archive_service.archive_relpath(doc))
        except Exception:
            errors += 1
            continue
        if new_abs != doc.storage_path:
            doc.storage_path = new_abs
            moved += 1
        else:
            skipped += 1
    await db.commit()
    return ReorganizeResult(
        examined=examined, moved=moved, skipped=skipped, errors=errors
    )


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
