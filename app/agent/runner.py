import json
from datetime import date

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.system_prompt import SYSTEM_PROMPT
from app.agent.tools import TOOLS, AgentContext, dispatch, file_to_content_block
from app.config import settings
from app.enums import DocumentStatus, FiscalClassification
from app.models.document import Document
from app.models.household import Household
from app.models.property_unit import PropertyUnit
from app.services import categories as categories_service
from app.services.embeddings import index_document
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


async def _household_context(db: AsyncSession, household_id) -> str:
    """Blocco di "addestramento" per il system prompt: istruzioni libere del
    nucleo + unità immobiliari configurate. Permette all'agente di attribuire
    correttamente le spese (es. condominio) senza chiedere ogni volta."""
    parts: list[str] = []
    household = await db.get(Household, household_id)
    if household and household.agent_instructions and household.agent_instructions.strip():
        parts.append(
            "ISTRUZIONI DEL NUCLEO (addestramento fornito dall'utente, rispettale "
            f"quando pertinenti):\n{household.agent_instructions.strip()}"
        )
    res = await db.execute(
        select(PropertyUnit)
        .where(PropertyUnit.household_id == household_id)
        .order_by(PropertyUnit.is_primary.desc(), PropertyUnit.name)
    )
    units = list(res.scalars())
    if units:
        lines = []
        for u in units:
            bits = [f'"{u.name}"']
            if u.is_primary:
                bits.append("(principale)")
            if u.address:
                bits.append(f"indirizzo: {u.address}")
            if u.condominium_name:
                bits.append(f"condominio: {u.condominium_name}")
            if u.owner_name:
                bits.append(f"intestatario: {u.owner_name}")
            if u.aliases:
                bits.append(f"compare anche come: {u.aliases}")
            if u.millesimi is not None:
                bits.append(f"millesimi: {u.millesimi}")
            if u.notes:
                bits.append(f"note: {u.notes}")
            lines.append("- " + "; ".join(bits))
        parts.append(
            "UNITÀ IMMOBILIARI DEL NUCLEO (usale per attribuire le spese di "
            "condominio all'unità corretta; se un documento ne cita una di queste, "
            "è quella del nucleo):\n" + "\n".join(lines)
        )
    return ("\n\n" + "\n\n".join(parts)) if parts else ""


async def _categories_context(db: AsyncSession, household_id) -> str:
    """Elenca le categorie merceologiche NOTE al nucleo (di base + personalizzate)
    nel system prompt, così l'agente riusa quelle esistenti ed evita doppioni; se
    nessuna è adatta può crearne una nuova con create_expense_category."""
    known = await categories_service.known_categories(db, household_id)
    base = [c for c in known if c["builtin"]]
    custom = [c for c in known if not c["builtin"]]

    def _fmt(c) -> str:
        desc = f" — {c['description']}" if c.get("description") else ""
        ex = c.get("examples")
        ex_txt = f" (es. {', '.join(ex)})" if ex else ""
        return f"{c['name']}{desc}{ex_txt}"

    # Categorie di base divise tra macro-categorie di primo livello (parent
    # vuoto) e sottocategorie di reparto del supermercato (parent valorizzato).
    base_top = [c for c in base if not c.get("parent")]
    base_subs = [c for c in base if c.get("parent")]
    top_lines = [f"- {_fmt(c)}" for c in base_top]
    sub_lines = [f"  · {_fmt(c)}" for c in base_subs]

    parts = [
        "CATEGORIE MERCEOLOGICHE NOTE DEL NUCLEO — gerarchia a due livelli "
        "(macro-categoria → sottocategoria). Classifica SEMPRE sulla foglia più "
        "specifica e riusa una categoria nota quando descrive bene la spesa; crea "
        "una nuova categoria con create_expense_category SOLO se nessuna è adatta "
        "(nome breve/generico/minuscolo, senza doppioni). Macro-categorie di base:\n"
        + "\n".join(top_lines)
    ]
    if sub_lines:
        parts.append(
            "Macro-categoria «spesa supermercato» — usa una di queste "
            "SOTTOCATEGORIE di reparto per la spesa al supermercato (NON usare nomi "
            "generici tipo 'supermercato'/'spesa'/'alimentari'):\n"
            + "\n".join(sub_lines)
        )
    if custom:
        custom_top = [c for c in custom if not c.get("parent")]
        custom_subs = [c for c in custom if c.get("parent")]
        custom_lines = [f"- {_fmt(c)}" for c in custom_top]
        custom_lines += [
            f"  · {_fmt(c)} [in «{c['parent']}»]" for c in custom_subs
        ]
        parts.append(
            "Categorie personalizzate del nucleo (già create, riusale):\n"
            + "\n".join(custom_lines)
        )
    return "\n\n" + "\n\n".join(parts)


async def _run_loop(db: AsyncSession, ctx: AgentContext, messages: list[dict]) -> str:
    tools = _build_tools()
    system_text = f"{SYSTEM_PROMPT}\n\nData odierna: {date.today().isoformat()}."
    system_text += await _household_context(db, ctx.household_id)
    system_text += await _categories_context(db, ctx.household_id)
    # Riservatezza dei farmaci (dati sanitari): l'agente sa se l'interlocutore è
    # amministratore e si comporta di conseguenza.
    if ctx.is_admin:
        system_text += (
            "\n\nL'utente con cui stai parlando è AMMINISTRATORE del nucleo: può "
            "vedere il dettaglio dei farmaci."
        )
    else:
        system_text += (
            "\n\nL'utente con cui stai parlando NON è amministratore del nucleo: "
            "NON rivelare il dettaglio dei farmaci (nomi commerciali, principio "
            "attivo, codici AIC/minsan, quantità, beneficiario). Se li chiede, "
            "spiega con cortesia che la consultazione dei farmaci è riservata "
            "all'amministratore del nucleo. Puoi comunque rispondere su tutto il "
            "resto."
        )
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


async def process_document(
    db: AsyncSession, document: Document, extra_instruction: str | None = None
) -> None:
    """Pipeline: legge il file, lo passa al modello (vision/PDF) con i tool,
    il modello estrae/classifica/attribuisce e persiste, poi salva la sintesi.

    `extra_instruction` (opzionale) sono indicazioni libere dell'utente per
    questa specifica (ri)elaborazione: vengono aggiunte all'istruzione di base
    con priorità, es. "questa è una bolletta del gas della seconda casa" oppure
    "attribuisci tutto a Mario e ignora la riga del sacchetto"."""
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
            "add_expenses, assegnando a ogni riga una categoria tra quelle NOTE del nucleo "
            "(creane una nuova con create_expense_category solo se nessuna è adatta) e "
            "conservando in 'details' i dati strutturati utili realmente presenti (marca, "
            "unità di misura, peso/volume, codice prodotto, reparto, aliquota IVA, sconto); "
            "se è una BOLLETTA/spesa di casa (luce, gas, acqua, rifiuti, "
            "internet, condominio, ...) usa invece save_bill estraendo periodo, scadenza, "
            "consumo e costo; 6) concludi con una sintesi pratica in italiano. Non inventare "
            "dati assenti né soglie o percentuali; lascia vuoti i campi non leggibili."
        )
        if extra_instruction and extra_instruction.strip():
            instruction += (
                "\n\nISTRUZIONI AGGIUNTIVE DELL'UTENTE PER QUESTA RIELABORAZIONE "
                "(prioritarie: seguile con attenzione anche quando correggono o "
                "precisano quanto sopra):\n" + extra_instruction.strip()
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
        # Indicizzazione semantica (best-effort: non deve far fallire la pipeline).
        try:
            if await index_document(db, document):
                await db.commit()
        except Exception:
            await db.rollback()
    except Exception as exc:
        await db.rollback()
        await db.refresh(document)
        document.status = DocumentStatus.FAILED
        document.reliability_note = f"Errore elaborazione: {exc}"
        await db.commit()


async def chat(
    db: AsyncSession,
    household_id,
    user_id,
    history: list[dict],
    message: str,
    is_admin: bool = False,
) -> str:
    """Agente conversazionale per interrogazioni ('quanto ho speso in farmaci nel 2025?')."""
    ctx = AgentContext(
        household_id=household_id, user_id=user_id, document_id=None, is_admin=is_admin
    )
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": message})
    return await _run_loop(db, ctx, messages) or "Non ho una risposta."
