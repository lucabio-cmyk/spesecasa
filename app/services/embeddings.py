import httpx

from app.config import settings


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
