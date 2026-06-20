"""Ricerca documenti dell'archivio: semantica (pgvector cosine) con fallback
automatico alla ricerca per parole chiave quando la feature è disattivata, il
provider di embedding non è configurato, o nessun documento è ancora indicizzato."""
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.services.embeddings import embed_text

# Documento + punteggio di similarità (0..1) se semantico, None se per keyword.
SearchHit = tuple[Document, float | None]


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        limit = 20
    return max(1, min(int(limit), 50))


async def _keyword_search(
    db: AsyncSession, household_id: uuid.UUID, query: str, limit: int
) -> list[SearchHit]:
    # ilike è già case-insensitive e or_ su singole colonne consente al planner
    # di sfruttare gli indici (es. trigram) evitando la full table scan.
    like = f"%{query}%"
    stmt = (
        select(Document)
        .where(
            Document.household_id == household_id,
            or_(
                Document.summary.ilike(like),
                Document.issuer.ilike(like),
                Document.recipient_name.ilike(like),
                Document.tags.ilike(like),
                Document.document_number.ilike(like),
            ),
        )
        .order_by(Document.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    return [(doc, None) for doc in res.scalars()]


async def search_documents(
    db: AsyncSession, household_id: uuid.UUID, query: str, limit: int | None = 20
) -> tuple[list[SearchHit], str]:
    """Ritorna (risultati, modalità). modalità: 'semantic' | 'keyword' | 'empty'."""
    query = (query or "").strip()
    limit = _clamp_limit(limit)
    if not query:
        return [], "empty"

    # Resilienza: se il provider di embedding è irraggiungibile / in errore,
    # si ripiega in modo trasparente sulla ricerca per parole chiave.
    try:
        vector = await embed_text(query)
    except Exception:
        vector = None
    if vector is not None:
        distance = Document.embedding.cosine_distance(vector)
        stmt = (
            select(Document, distance.label("distance"))
            .where(
                Document.household_id == household_id,
                Document.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(limit)
        )
        res = await db.execute(stmt)
        # cosine distance ∈ [0,2]; similarità = 1 - distanza (clamp a 0).
        hits = [(doc, max(0.0, 1.0 - float(dist))) for doc, dist in res.all()]
        if hits:
            return hits, "semantic"
        # Nessun documento ancora indicizzato: ripiega sulle parole chiave.

    return await _keyword_search(db, household_id, query, limit), "keyword"
