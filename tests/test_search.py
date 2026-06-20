"""Test della ricerca semantica nell'archivio (con fallback keyword).
Livello smoke: niente DB, verifica tool, schemi, servizio e prompt."""
import asyncio


def test_search_documents_tool_exposed():
    from app.agent.tools import TOOLS

    tool = next((t for t in TOOLS if t.get("name") == "search_documents"), None)
    assert tool is not None
    assert tool["input_schema"]["required"] == ["query"]


def test_search_endpoint_registered_before_detail():
    from app.api.documents import router

    paths = [r.path for r in router.routes]
    assert "/documents/search" in paths
    # La rotta letterale deve precedere quella parametrica per la priorità di match.
    assert paths.index("/documents/search") < paths.index("/documents/{document_id}")


def test_search_hit_schema_has_score():
    from app.schemas.document import DocumentOut, DocumentSearchHit

    assert issubclass(DocumentSearchHit, DocumentOut)
    assert "score" in DocumentSearchHit.model_fields


def test_embed_text_disabled_returns_none():
    from app.services.embeddings import embed_text

    # enable_semantic_search è False di default: nessuna chiamata di rete.
    assert asyncio.run(embed_text("qualcosa")) is None


def test_empty_query_returns_empty_mode():
    from app.services.search import search_documents

    hits, mode = asyncio.run(search_documents(None, None, "   ", 10))
    assert hits == []
    assert mode == "empty"


def test_clamp_limit_bounds():
    from app.services.search import _clamp_limit

    assert _clamp_limit(0) == 1
    assert _clamp_limit(None) == 20
    assert _clamp_limit(1000) == 50


def test_build_document_text_includes_key_fields():
    from datetime import date
    from app.services.embeddings import build_document_text
    from app.models.document import Document

    class _Result:
        def all(self):
            return []

    class _FakeDB:
        async def execute(self, *_a, **_k):
            return _Result()

    doc = Document(
        issuer="Studio Dentistico Rossi",
        summary="Fattura per visita odontoiatrica",
        tags="dentista, sanitaria",
        doc_date=date(2025, 3, 1),
    )
    text = asyncio.run(build_document_text(_FakeDB(), doc))
    assert "Studio Dentistico Rossi" in text
    assert "odontoiatrica" in text
    assert "dentista" in text


def test_system_prompt_covers_semantic_search():
    from app.agent.system_prompt import SYSTEM_PROMPT

    assert "search_documents" in SYSTEM_PROMPT
