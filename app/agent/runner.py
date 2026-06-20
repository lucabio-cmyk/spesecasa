import json
from datetime import date

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.system_prompt import SYSTEM_PROMPT
from app.agent.tools import TOOLS, AgentContext, dispatch, file_to_content_block
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


async def _run_loop(db: AsyncSession, ctx: AgentContext, messages: list[dict]) -> str:
    tools = _build_tools()
    system_text = f"{SYSTEM_PROMPT}\n\nData odierna: {date.today().isoformat()}."
    final_text = ""
    for _ in range(settings.agent_max_tool_iterations):
        resp = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.agent_max_tokens,
            system=system_text,
            tools=tools,
            messages=messages,
        )

        tool_results: list[dict] = []
        # Blocchi file (PDF/immagine) da allegare alla risposta degli strumenti,
        # es. quando read_document rilegge un originale per l'analisi.
        extra_blocks: list[dict] = []
        turn_text = ""
        for block in resp.content:
            if block.type == "text":
                turn_text += block.text
            elif block.type == "tool_use":  # solo strumenti applicativi (client-side)
                # La ricerca web è server-side (arriva come server_tool_use): non
                # va mai eseguita localmente. Guardia difensiva per sicurezza.
                if block.name == "web_search":
                    continue
                result = await dispatch(block.name, block.input, db, ctx)
                blocks = result.pop("_content_blocks", None) if isinstance(result, dict) else None
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str, ensure_ascii=False),
                    }
                )
                if blocks:
                    extra_blocks.extend(blocks)
            # I blocchi server-side (server_tool_use / web_search_tool_result)
            # sono gestiti da Anthropic: vanno solo conservati nella history.

        # Si conserva il content grezzo: preserva anche i blocchi di ricerca web.
        messages.append({"role": "assistant", "content": resp.content})
        if turn_text:
            final_text = turn_text

        if tool_results:
            # I file allegati (extra_blocks) seguono i tool_result nello stesso turno
            # utente, così il modello può analizzarli subito.
            messages.append({"role": "user", "content": tool_results + extra_blocks})
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
            "conoscere i membri del nucleo; 2) identifica il tipo ed estrai TUTTI i dati "
            "utili realmente presenti: data, emittente e sua P.IVA/CF, intestatario e suo "
            "codice fiscale, numero documento, importo totale, imponibile e IVA, valuta, "
            "modalità e tracciabilità del pagamento, scadenza; metti gli altri dati utili "
            "non previsti dai campi (IBAN, POD/PDR, codice tributo F24, periodo, ecc.) in "
            "'details', e aggiungi parole chiave in 'tags'; 3) usa find_existing_document "
            "per evitare duplicati; 4) classifica fiscalmente e attribuisci soggetto "
            "pagante/beneficiario/ambito; 5) salva l'header con save_document e le righe con "
            "add_expenses; se è una BOLLETTA/spesa di casa (luce, gas, acqua, rifiuti, "
            "internet, condominio, ...) usa invece save_bill estraendo periodo, scadenza, "
            "consumo e costo; 6) concludi con una sintesi pratica in italiano. Non inventare "
            "dati assenti né soglie o percentuali; lascia vuoti i campi non leggibili."
        )
        messages = [
            {"role": "user", "content": [file_to_content_block(document.mime_type, data), {"type": "text", "text": instruction}]}
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
