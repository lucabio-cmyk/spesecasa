import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.document import Document
from app.models.expense import Expense


async def embed_text(text: str) -> list[float] | None:
    """Ritorna l'embedding del testo, o None se la feature è disattivata.
    Usato (opzionalmente) per ricerca semantica su documenti/descrizioni."""
    if not settings.enable_semantic_search or not text:
        return None

    if settings.embedding_provider == "voyage" and settings.voyage_api_key:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.voyage_api_key}"},
                json={"input": [text], "model": settings.embedding_model},
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]

    # TODO(claude-code): aggiungere altri provider (OpenAI, locale, ...)
    return None


async def build_document_text(db: AsyncSession, document: Document) -> str:
    """Compone una rappresentazione testuale ricca del documento (header +
    sintesi + voci) da trasformare in embedding per la ricerca semantica."""
    parts: list[str] = []
    if document.doc_type:
        parts.append(f"Tipo: {document.doc_type.value}")
    if document.issuer:
        parts.append(f"Emittente: {document.issuer}")
    if document.recipient_name:
        parts.append(f"Intestatario: {document.recipient_name}")
    if document.doc_date:
        parts.append(f"Data: {document.doc_date.isoformat()}")
    if document.total_amount is not None:
        parts.append(f"Totale: {document.total_amount}")
    if document.fiscal_classification:
        parts.append(f"Classificazione fiscale: {document.fiscal_classification.value}")
    if document.tags:
        parts.append(f"Tag: {document.tags}")
    if document.summary:
        parts.append(document.summary)

    res = await db.execute(
        select(
            Expense.description_normalized,
            Expense.description_original,
            Expense.merch_category,
        ).where(Expense.document_id == document.id)
    )
    tokens: list[str] = []
    for descr_norm, descr_orig, category in res.all():
        token = descr_norm or descr_orig
        if token:
            tokens.append(token)
        if category:
            tokens.append(category)
    if tokens:
        # dict.fromkeys: deduplica preservando l'ordine
        parts.append("Voci: " + ", ".join(dict.fromkeys(tokens)))

    return "\n".join(parts)


async def index_document(db: AsyncSession, document: Document) -> bool:
    """Calcola e imposta l'embedding del documento. No-op (ritorna False) se la
    ricerca semantica è disattivata o il provider non è configurato. Il commit
    della transazione è responsabilità del chiamante."""
    text = await build_document_text(db, document)
    vector = await embed_text(text)
    if vector is None:
        return False
    document.embedding = vector
    return True
