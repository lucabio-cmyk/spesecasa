import base64
import json

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.system_prompt import SYSTEM_PROMPT
from app.agent.tools import TOOLS, AgentContext, dispatch
from app.config import settings
from app.enums import DocumentStatus, FiscalClassification
from app.models.document import Document
from app.services.storage import get_storage

client = AsyncAnthropic(api_key=settings.anthropic_api_key)


def _build_tools() -> list[dict]:
    """Strumenti dell'app + (opzionale) ricerca web server-side per affinare e
    verificare le regole fiscali aggiornate. La web_search è eseguita da
    Anthropic: non richiede dispatch lato client."""
    tools = list(TOOLS)
    if settings.enable_web_search:
        tools.append(
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": settings.web_search_max_uses,
                "user_location": {
                    "type": "approximate",
                    "country": settings.web_search_country,
                },
            }
        )
    return tools


def _file_block(mime_type: str, data: bytes) -> dict:
    b64 = base64.standard_b64encode(data).decode()
    if mime_type == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    if mime_type.startswith("image/"):
        return {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}}
    # fallback: prova come documento PDF
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}


async def _run_loop(db: AsyncSession, ctx: AgentContext, messages: list[dict]) -> str:
    tools = _build_tools()
    final_text = ""
    for _ in range(settings.agent_max_tool_iterations):
        resp = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.agent_max_tokens,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        tool_results: list[dict] = []
        turn_text = ""
        for block in resp.content:
            if block.type == "text":
                turn_text += block.text
            elif block.type == "tool_use":  # solo strumenti applicativi (client-side)
                result = await dispatch(block.name, block.input, db, ctx)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str, ensure_ascii=False),
                    }
                )
            # I blocchi server-side (server_tool_use / web_search_tool_result)
            # sono gestiti da Anthropic: vanno solo conservati nella history.

        # Si conserva il content grezzo: preserva anche i blocchi di ricerca web.
        messages.append({"role": "assistant", "content": resp.content})
        if turn_text:
            final_text = turn_text

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
            continue
        if resp.stop_reason == "pause_turn":
            # Turno messo in pausa (es. ricerca web lunga): si prosegue.
            continue
        break

    return final_text.strip()


async def process_document(db: AsyncSession, document: Document) -> None:
    """Pipeline: legge il file, lo passa al modello (vision/PDF) con i tool,
    il modello estrae/classifica/attribuisce e persiste, poi salva la sintesi."""
    document.status = DocumentStatus.PROCESSING
    await db.commit()
    try:
        data = get_storage().read(document.storage_path)
        ctx = AgentContext(
            household_id=document.household_id,
            user_id=document.uploaded_by_user_id,
            document_id=document.id,
        )
        instruction = (
            "Elabora il documento allegato. Passi: 1) usa list_household_members per "
            "conoscere i membri del nucleo; 2) identifica il tipo ed estrai i dati; "
            "3) usa find_existing_document per evitare duplicati; 4) classifica "
            "fiscalmente e attribuisci soggetto pagante/beneficiario/ambito; 5) salva "
            "l'header con save_document e le righe con add_expenses; 6) concludi con una "
            "sintesi pratica in italiano. Non inventare soglie o percentuali."
        )
        messages = [
            {"role": "user", "content": [_file_block(document.mime_type, data), {"type": "text", "text": instruction}]}
        ]
        summary = await _run_loop(db, ctx, messages)

        await db.refresh(document)
        document.summary = summary or document.summary
        if document.status == DocumentStatus.PROCESSING:
            document.status = (
                DocumentStatus.NEEDS_REVIEW
                if document.fiscal_classification == FiscalClassification.DA_VERIFICARE
                else DocumentStatus.COMPLETE
            )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        await db.refresh(document)
        document.status = DocumentStatus.FAILED
        document.reliability_note = f"Errore elaborazione: {exc}"
        await db.commit()


async def chat(db: AsyncSession, household_id, user_id, history: list[dict], message: str) -> str:
    """Agente conversazionale per interrogazioni ('quanto ho speso in farmaci nel 2025?')."""
    ctx = AgentContext(household_id=household_id, user_id=user_id, document_id=None)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": message})
    return await _run_loop(db, ctx, messages) or "Non ho una risposta."
