"""Agente di orchestrazione: revisione in background dell'archivio del nucleo.

Fa due cose, separate e complementari:

1. **Verifiche deterministiche** (sempre, niente LLM): controlla la coerenza dei
   dati già archiviati e segnala ciò che NON è stato calcolato o gestito
   correttamente — righe che non quadrano col totale del documento, documenti
   con importo ma senza righe, righe non calcolate/illeggibili, classificazioni
   da verificare, attribuzioni mancanti, possibili duplicati, elaborazioni
   fallite. Ogni problema diventa una `ReviewItem` (avviso).

2. **Fase LLM** (opzionale): un agente legge una sintesi dell'archivio e PROPONE
   miglioramenti — categorie merceologiche migliori, riclassificazioni — che
   restano in stato `pending` e vengono applicate SOLO se l'utente dà il
   consenso (vedi `apply_review_item`).

Le voci sono deduplicate tramite una `signature` deterministica: una decisione
già presa dall'utente (rifiuto/archiviazione) non viene riproposta.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.enums import (
    DocumentStatus,
    DocumentType,
    FiscalClassification,
    ReviewKind,
    ReviewSeverity,
    ReviewStatus,
)
from app.models.bill import Bill
from app.models.document import Document
from app.models.expense import Expense
from app.models.review import ReviewItem
from app.models.user import User
from app.services import categories as categories_service
from app.services.llm import create_message

# Documenti che dovrebbero avere righe di spesa (gli altri — bollette, contratti,
# verbali, F24, bonifici — sono gestiti diversamente).
_LINED_DOC_TYPES = {
    DocumentType.SCONTRINO,
    DocumentType.FATTURA,
    DocumentType.RICEVUTA,
    DocumentType.RICEVUTA_SANITARIA,
}
_OPEN_STATES = {
    ReviewStatus.PENDING,
}


def _q(value) -> Decimal:
    return Decimal(str(value or 0))


# --- Persistenza con deduplica ----------------------------------------------
async def _record(
    db: AsyncSession,
    household_id: uuid.UUID,
    *,
    kind: ReviewKind,
    signature: str,
    title: str,
    detail: str | None = None,
    severity: ReviewSeverity = ReviewSeverity.INFO,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    fiscal_year: int | None = None,
    payload: dict | None = None,
    source: str = "auto",
) -> ReviewItem | None:
    """Crea una voce di revisione, evitando i doppioni per `signature`.

    Se esiste già una voce con la stessa firma:
    - se è ancora `pending`, ne aggiorna testo/payload (i dati possono essere
      cambiati) e la restituisce;
    - se l'utente l'ha già risolta (approvata/applicata/rifiutata/archiviata),
      NON la ripropone (rispetta la decisione presa) e restituisce None.
    """
    existing = (
        await db.execute(
            select(ReviewItem)
            .where(
                ReviewItem.household_id == household_id,
                ReviewItem.signature == signature,
            )
            .order_by(ReviewItem.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status != ReviewStatus.PENDING:
            return None
        existing.title = title
        existing.detail = detail
        existing.severity = severity
        existing.payload = payload
        existing.fiscal_year = fiscal_year
        return existing

    item = ReviewItem(
        household_id=household_id,
        kind=kind,
        signature=signature,
        title=title,
        detail=detail,
        severity=severity,
        target_type=target_type,
        target_id=target_id,
        fiscal_year=fiscal_year,
        payload=payload,
        source=source,
    )
    db.add(item)
    return item


# --- Verifiche deterministiche ----------------------------------------------
async def _check_documents(
    db: AsyncSession,
    household_id: uuid.UUID,
    *,
    fiscal_year: int | None,
    document_id: uuid.UUID | None,
) -> int:
    """Controlli sui documenti e sulle loro righe. Restituisce il numero di
    avvisi creati/aggiornati."""
    # Una sola query con sottoquery aggregate (evita N+1): per ogni documento
    # otteniamo somma/numero righe collegate e se ha una bolletta collegata.
    expense_sub = (
        select(
            Expense.document_id.label("document_id"),
            func.coalesce(func.sum(Expense.line_amount), 0).label("lines_sum"),
            func.count(Expense.id).label("lines_count"),
        )
        .where(Expense.household_id == household_id)
        .group_by(Expense.document_id)
        .subquery()
    )
    bill_sub = (
        select(Bill.document_id.label("document_id"))
        .where(Bill.household_id == household_id, Bill.document_id.isnot(None))
        .group_by(Bill.document_id)
        .subquery()
    )
    stmt = (
        select(
            Document,
            func.coalesce(expense_sub.c.lines_sum, 0),
            func.coalesce(expense_sub.c.lines_count, 0),
            bill_sub.c.document_id.isnot(None),
        )
        .outerjoin(expense_sub, expense_sub.c.document_id == Document.id)
        .outerjoin(bill_sub, bill_sub.c.document_id == Document.id)
        .where(Document.household_id == household_id)
    )
    if document_id:
        stmt = stmt.where(Document.id == document_id)
    if fiscal_year:
        stmt = stmt.where(Document.fiscal_year == fiscal_year)
    rows = (await db.execute(stmt)).all()
    count = 0

    for doc, lines_sum_raw, lines_count_raw, has_bill in rows:
        lines_sum = _q(lines_sum_raw)
        lines_count = int(lines_count_raw or 0)

        label = doc.issuer or doc.original_filename or str(doc.id)[:8]
        fy = doc.fiscal_year

        # 1) Elaborazione fallita.
        if doc.status == DocumentStatus.FAILED:
            if await _record(
                db, household_id,
                kind=ReviewKind.PROCESSING_FAILED,
                signature=f"failed:{doc.id}",
                title=f"Documento non elaborato: {label}",
                detail=doc.reliability_note or "L'elaborazione del documento non è andata a buon fine.",
                severity=ReviewSeverity.CRITICAL,
                target_type="document", target_id=doc.id, fiscal_year=fy,
            ):
                count += 1
            continue

        # Considera solo i documenti già elaborati per i controlli di merito.
        if doc.status not in (DocumentStatus.COMPLETE, DocumentStatus.NEEDS_REVIEW):
            continue

        total = _q(doc.total_amount)

        # 2) Documento che dovrebbe avere righe ma non ne ha.
        if (
            not has_bill
            and lines_count == 0
            and doc.doc_type in _LINED_DOC_TYPES
            and total > 0
        ):
            if await _record(
                db, household_id,
                kind=ReviewKind.MISSING_LINES,
                signature=f"missing_lines:{doc.id}",
                title=f"Nessuna riga estratta da {label}",
                detail=(
                    f"Il documento ha un totale di {total} € ma non è stata "
                    "registrata alcuna riga di spesa: alcune voci potrebbero non "
                    "essere state lette correttamente."
                ),
                severity=ReviewSeverity.WARNING,
                target_type="document", target_id=doc.id, fiscal_year=fy,
                payload={"total_amount": str(total)},
            ):
                count += 1

        # 3) Riconciliazione: somma righe ≠ totale documento.
        if lines_count > 0 and total > 0:
            diff = (lines_sum - total).copy_abs()
            tolerance = max(Decimal("0.05"), (total * Decimal("0.01")))
            if diff > tolerance:
                if await _record(
                    db, household_id,
                    kind=ReviewKind.RECONCILIATION,
                    signature=f"reconcile:{doc.id}",
                    title=f"Le righe non quadrano con il totale ({label})",
                    detail=(
                        f"Somma delle {lines_count} righe: {lines_sum} € · "
                        f"totale del documento: {total} € · differenza: {diff} €. "
                        "Alcune righe potrebbero mancare, essere doppie o avere "
                        "un importo errato."
                    ),
                    severity=ReviewSeverity.WARNING,
                    target_type="document", target_id=doc.id, fiscal_year=fy,
                    payload={
                        "lines_sum": str(lines_sum),
                        "total_amount": str(total),
                        "difference": str(diff),
                        "lines_count": lines_count,
                    },
                ):
                    count += 1

        # 4) Classificazione fiscale da verificare.
        if doc.fiscal_classification == FiscalClassification.DA_VERIFICARE:
            if await _record(
                db, household_id,
                kind=ReviewKind.MISSING_CLASSIFICATION,
                signature=f"classif:{doc.id}",
                title=f"Classificazione fiscale da confermare ({label})",
                detail="La rilevanza fiscale del documento è ancora 'da verificare'.",
                severity=ReviewSeverity.INFO,
                target_type="document", target_id=doc.id, fiscal_year=fy,
            ):
                count += 1

        # 5) Attribuzione mancante (nessun soggetto pagante).
        if doc.payer_user_id is None and total > 0:
            if await _record(
                db, household_id,
                kind=ReviewKind.MISSING_ATTRIBUTION,
                signature=f"attrib:{doc.id}",
                title=f"Soggetto pagante non attribuito ({label})",
                detail="Il documento non è attribuito ad alcun membro del nucleo come pagante.",
                severity=ReviewSeverity.INFO,
                target_type="document", target_id=doc.id, fiscal_year=fy,
            ):
                count += 1

        # 6) Nota di affidabilità presente (incertezze annotate in estrazione).
        if doc.reliability_note and doc.reliability_note.strip():
            if await _record(
                db, household_id,
                kind=ReviewKind.RELIABILITY,
                signature=f"reliab:{doc.id}",
                title=f"Da rivedere: {label}",
                detail=doc.reliability_note.strip(),
                severity=ReviewSeverity.WARNING,
                target_type="document", target_id=doc.id, fiscal_year=fy,
            ):
                count += 1

    return count


async def _check_expense_reliability(
    db: AsyncSession,
    household_id: uuid.UUID,
    *,
    fiscal_year: int | None,
    document_id: uuid.UUID | None,
) -> int:
    """Segnala le singole righe con una nota di affidabilità (es. importo o
    descrizione incerti) o con importo nullo."""
    stmt = select(Expense).where(
        Expense.household_id == household_id,
        Expense.reliability_note.isnot(None),
    )
    if document_id:
        stmt = stmt.where(Expense.document_id == document_id)
    if fiscal_year:
        stmt = stmt.where(Expense.fiscal_year == fiscal_year)
    stmt = stmt.limit(200)
    rows = list((await db.execute(stmt)).scalars())
    count = 0
    for e in rows:
        note = (e.reliability_note or "").strip()
        if not note:
            continue
        desc = e.description_normalized or e.description_original or e.merchant or "riga"
        if await _record(
            db, household_id,
            kind=ReviewKind.SKIPPED_LINE,
            signature=f"line_reliab:{e.id}",
            title=f"Riga da verificare: {desc[:80]}",
            detail=f"{note} (importo registrato: {e.line_amount} €).",
            severity=ReviewSeverity.INFO,
            target_type="expense", target_id=e.id, fiscal_year=e.fiscal_year,
        ):
            count += 1
    return count


async def _check_duplicates(
    db: AsyncSession, household_id: uuid.UUID, *, fiscal_year: int | None
) -> int:
    """Possibili duplicati: documenti distinti con stesso emittente, data e
    totale (file diversi, quindi non intercettati dall'hash in upload)."""
    stmt = (
        select(Document)
        .where(
            Document.household_id == household_id,
            Document.issuer.isnot(None),
            Document.doc_date.isnot(None),
            Document.total_amount.isnot(None),
            Document.status.in_([DocumentStatus.COMPLETE, DocumentStatus.NEEDS_REVIEW]),
        )
        .order_by(Document.created_at)
    )
    if fiscal_year:
        stmt = stmt.where(Document.fiscal_year == fiscal_year)
    docs = list((await db.execute(stmt)).scalars())
    groups: dict[tuple, list[Document]] = {}
    for d in docs:
        key = (
            (d.issuer or "").strip().lower(),
            d.doc_date,
            _q(d.total_amount),
        )
        groups.setdefault(key, []).append(d)

    count = 0
    for key, members in groups.items():
        if len(members) < 2:
            continue
        members_sorted = sorted(members, key=lambda d: d.created_at or datetime.min)
        primary = members_sorted[0]
        dups = members_sorted[1:]
        ids = sorted(str(m.id) for m in members_sorted)
        issuer, ddate, total = key
        for dup in dups:
            # Firma stabile sul singolo documento duplicato: se in futuro un altro
            # documento entra nello stesso gruppo, le decisioni già prese
            # dall'utente sugli altri non vengono invalidate/riproposte.
            if await _record(
                db, household_id,
                kind=ReviewKind.POSSIBLE_DUPLICATE,
                signature=f"dup:{dup.id}",
                title=f"Possibile duplicato: {primary.issuer} {total} €",
                detail=(
                    f"Due documenti dello stesso emittente con la stessa data "
                    f"({ddate}) e lo stesso totale ({total} €): potrebbe trattarsi "
                    "dello stesso documento caricato due volte."
                ),
                severity=ReviewSeverity.WARNING,
                target_type="document", target_id=dup.id, fiscal_year=dup.fiscal_year,
                payload={"duplicate_of": str(primary.id), "documents": ids},
            ):
                count += 1
    return count


# --- Fase LLM (proposte previo consenso) ------------------------------------
def _llm_client():
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(
        api_key=settings.anthropic_api_key, max_retries=settings.anthropic_max_retries
    )


_PROPOSAL_TOOLS = [
    {
        "name": "propose_category",
        "description": (
            "Proponi una NUOVA categoria merceologica (o l'accorpamento di voci "
            "generiche in una categoria più chiara). NON viene applicata subito: "
            "resta in attesa del consenso dell'utente. Usa nomi brevi, generici e "
            "minuscoli. Indica in 'reassign_from' le categorie esistenti (per nome) "
            "le cui spese andrebbero spostate nella nuova categoria."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "parent": {
                    "type": "string",
                    "description": (
                        "facoltativo: macro-categoria (gruppo) di cui questa è una "
                        "sottocategoria, es. 'spesa supermercato'. Ometti per una "
                        "categoria di primo livello."
                    ),
                },
                "description": {"type": "string"},
                "examples": {"type": "array", "items": {"type": "string"}},
                "reassign_from": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string", "description": "perché è utile"},
            },
            "required": ["name", "rationale"],
        },
    },
    {
        "name": "propose_reclassification",
        "description": (
            "Proponi di cambiare la classificazione fiscale di un documento o di "
            "una spesa. NON viene applicata subito: richiede il consenso dell'utente. "
            "Non inventare percentuali o soglie."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_type": {"type": "string", "enum": ["document", "expense"]},
                "target_id": {"type": "string"},
                "fiscal_classification": {
                    "type": "string",
                    "enum": [c.value for c in FiscalClassification],
                },
                "rationale": {"type": "string"},
            },
            "required": ["target_type", "target_id", "fiscal_classification", "rationale"],
        },
    },
    {
        "name": "flag_insight",
        "description": (
            "Registra un'osservazione o anomalia utile (informativa, senza azione "
            "automatica): es. una spesa anomala, un andamento, un dato sospetto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "detail": {"type": "string"},
                "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
            },
            "required": ["title", "detail"],
        },
    },
]

_LLM_SYSTEM = (
    "Sei l'agente di orchestrazione dell'archivio spese di un nucleo familiare "
    "italiano. Il tuo compito è MIGLIORARE l'organizzazione dei dati già "
    "archiviati: proponi categorie merceologiche più chiare quando ne vedono di "
    "troppo generiche o doppioni, suggerisci riclassificazioni fiscali quando "
    "evidenti, e segnala anomalie. Lavori SOLO per PROPOSTE: usa gli strumenti "
    "propose_* e flag_insight; non applichi nulla direttamente, sarà l'utente a "
    "dare il consenso. Sii parsimonioso: poche proposte ben motivate. Non "
    "inventare dati, soglie o percentuali fiscali. Rispondi in italiano con una "
    "breve sintesi finale delle proposte fatte."
)


async def _category_usage(
    db: AsyncSession, household_id: uuid.UUID, fiscal_year: int | None
) -> list[dict]:
    stmt = (
        select(
            Expense.merch_category,
            func.count(Expense.id),
            func.coalesce(func.sum(Expense.line_amount), 0),
        )
        .where(Expense.household_id == household_id)
        .group_by(Expense.merch_category)
        .order_by(func.count(Expense.id).desc())
    )
    if fiscal_year:
        stmt = stmt.where(Expense.fiscal_year == fiscal_year)
    rows = (await db.execute(stmt)).all()
    return [
        {"category": r[0] or "(senza categoria)", "count": int(r[1]), "total": str(_q(r[2]))}
        for r in rows
    ]


async def _llm_dispatch(
    db: AsyncSession, household_id: uuid.UUID, fiscal_year: int | None, name: str, inp: dict
) -> dict:
    """Esegue un tool di proposta creando una ReviewItem in stato pending."""
    if name == "propose_category":
        cat_name = (inp.get("name") or "").strip()
        if not cat_name:
            return {"ok": False, "error": "nome categoria mancante"}
        reassign = [str(x).strip().lower() for x in (inp.get("reassign_from") or []) if str(x).strip()]
        detail = inp.get("rationale") or inp.get("description") or ""
        if reassign:
            detail += f"\nSpostando le spese da: {', '.join(reassign)}."
        item = await _record(
            db, household_id,
            kind=ReviewKind.CATEGORY_PROPOSAL,
            signature=f"propose_cat:{categories_service.normalize_name(cat_name)}",
            title=f"Proposta categoria: «{categories_service.normalize_name(cat_name)}»",
            detail=detail.strip() or None,
            severity=ReviewSeverity.INFO,
            target_type="category", target_id=None, fiscal_year=fiscal_year,
            source="agent",
            payload={
                "action": "create_category",
                "name": cat_name,
                "parent": inp.get("parent"),
                "description": inp.get("description"),
                "examples": inp.get("examples"),
                "reassign_from": reassign,
            },
        )
        return {"ok": True, "proposed": item is not None}

    if name == "propose_reclassification":
        ttype = inp.get("target_type")
        tid = inp.get("target_id")
        fc = inp.get("fiscal_classification")
        if ttype not in ("document", "expense") or not tid or fc not in [c.value for c in FiscalClassification]:
            return {"ok": False, "error": "parametri non validi"}
        try:
            tid_uuid = uuid.UUID(str(tid))
        except (ValueError, TypeError):
            return {"ok": False, "error": "target_id non valido"}
        # Verifica che il bersaglio esista e appartenga al nucleo, così non si
        # creano proposte verso ID inventati.
        model = Document if ttype == "document" else Expense
        target = await db.get(model, tid_uuid)
        if not target or target.household_id != household_id:
            return {"ok": False, "error": f"{ttype} non trovato nel nucleo"}
        item = await _record(
            db, household_id,
            kind=ReviewKind.RECLASSIFICATION,
            signature=f"reclass:{ttype}:{tid_uuid}:{fc}",
            title=f"Proposta riclassificazione → {fc}",
            detail=inp.get("rationale"),
            severity=ReviewSeverity.INFO,
            target_type=ttype, target_id=tid_uuid, fiscal_year=fiscal_year,
            source="agent",
            payload={"action": "reclassify", "target_type": ttype, "fiscal_classification": fc},
        )
        return {"ok": True, "proposed": item is not None}

    if name == "flag_insight":
        title = (inp.get("title") or "Osservazione").strip()
        sev = inp.get("severity")
        severity = ReviewSeverity(sev) if sev in [s.value for s in ReviewSeverity] else ReviewSeverity.INFO
        # Firma stabile (hash deterministico) per non riproporre lo stesso insight
        # a ogni esecuzione.
        digest = hashlib.md5(f"{title}|{inp.get('detail') or ''}".encode()).hexdigest()[:16]
        item = await _record(
            db, household_id,
            kind=ReviewKind.INSIGHT,
            signature=f"insight:{digest}",
            title=title[:300],
            detail=inp.get("detail"),
            severity=severity,
            fiscal_year=fiscal_year, source="agent",
        )
        return {"ok": True, "logged": item is not None}

    return {"ok": False, "error": "strumento sconosciuto"}


async def _run_llm(
    db: AsyncSession, household_id: uuid.UUID, fiscal_year: int | None
) -> int:
    if not settings.anthropic_api_key:
        return 0
    known = await categories_service.known_categories(db, household_id)
    usage = await _category_usage(db, household_id, fiscal_year)
    known_lines = "\n".join(
        f"- {c['name']}" + (f": {c['description']}" if c.get("description") else "")
        for c in known
    )
    usage_lines = "\n".join(
        f"- {u['category']}: {u['count']} voci, {u['total']} €" for u in usage
    ) or "(nessuna spesa registrata)"
    context = (
        f"Anno fiscale: {fiscal_year or 'tutti'}.\n\n"
        f"CATEGORIE NOTE DEL NUCLEO:\n{known_lines}\n\n"
        f"USO ATTUALE DELLE CATEGORIE (categoria: numero voci, totale):\n{usage_lines}\n\n"
        "Analizza la distribuzione: se ci sono categorie troppo generiche, "
        "voci senza categoria o accorpamenti utili, proponi miglioramenti con "
        "propose_category. Se noti classificazioni fiscali palesemente errate o "
        "anomalie, usa propose_reclassification o flag_insight. Non eccedere."
    )
    messages = [{"role": "user", "content": context}]
    client = _llm_client()
    proposals = 0
    try:
        for _ in range(settings.orchestrator_max_tool_iterations):
            resp = await create_message(
                client,
                model=settings.anthropic_model,
                max_tokens=settings.agent_max_tokens,
                system=_LLM_SYSTEM,
                tools=_PROPOSAL_TOOLS,
                messages=messages,
            )
            tool_results: list[dict] = []
            for block in resp.content:
                if block.type == "tool_use":
                    result = await _llm_dispatch(db, household_id, fiscal_year, block.name, block.input)
                    if result.get("proposed") or result.get("logged"):
                        proposals += 1
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
            messages.append({"role": "assistant", "content": resp.content})
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
                continue
            break
    except Exception:
        # La fase LLM è best-effort: non deve far fallire la revisione.
        return proposals
    return proposals


# --- Orchestrazione completa ------------------------------------------------
async def run_orchestration(
    db: AsyncSession,
    household_id: uuid.UUID,
    *,
    fiscal_year: int | None = None,
    document_id: uuid.UUID | None = None,
    use_llm: bool | None = None,
    source: str = "auto",
) -> dict:
    """Esegue una revisione completa dell'archivio del nucleo.

    - `document_id`: limita le verifiche a un singolo documento (modalità
      post-upload), saltando duplicati globali e fase LLM.
    - `use_llm`: forza on/off la fase di proposta LLM (default: dalle settings).
    """
    if not settings.enable_orchestrator:
        return {"ok": False, "reason": "orchestrator disabilitato"}

    findings = 0
    findings += await _check_documents(
        db, household_id, fiscal_year=fiscal_year, document_id=document_id
    )
    findings += await _check_expense_reliability(
        db, household_id, fiscal_year=fiscal_year, document_id=document_id
    )
    if document_id is None:
        findings += await _check_duplicates(db, household_id, fiscal_year=fiscal_year)
    await db.commit()

    proposals = 0
    run_llm = settings.orchestrator_use_llm if use_llm is None else use_llm
    if run_llm and document_id is None:
        proposals = await _run_llm(db, household_id, fiscal_year)
        await db.commit()

    pending = (
        await db.execute(
            select(func.count(ReviewItem.id)).where(
                ReviewItem.household_id == household_id,
                ReviewItem.status == ReviewStatus.PENDING,
            )
        )
    ).scalar_one()
    return {
        "ok": True,
        "checks_findings": findings,
        "proposals": proposals,
        "pending_total": int(pending),
    }


# --- Applicazione di una proposta (su consenso) -----------------------------
async def apply_review_item(
    db: AsyncSession, item: ReviewItem, user_id: uuid.UUID
) -> dict:
    """Applica l'azione di una proposta approvata. Le voci puramente informative
    vengono semplicemente segnate come gestite."""
    payload = item.payload or {}
    action = payload.get("action")
    note = ""

    try:
        if action == "create_category":
            name = payload.get("name") or ""
            res = await categories_service.create_category(
                db, item.household_id,
                name=name,
                description=payload.get("description"),
                examples=payload.get("examples"),
                parent=payload.get("parent"),
                source="user",
            )
            if res.get("error"):
                return {"ok": False, "error": res["error"]}
            norm = categories_service.normalize_name(name)
            reassigned = 0
            for old in payload.get("reassign_from") or []:
                old_norm = categories_service.normalize_name(old)
                if not old_norm or old_norm == norm:
                    continue
                rows = list(
                    (
                        await db.execute(
                            select(Expense).where(
                                Expense.household_id == item.household_id,
                                Expense.merch_category == old_norm,
                            )
                        )
                    ).scalars()
                )
                for e in rows:
                    e.merch_category = norm
                    reassigned += 1
            note = f"Categoria «{norm}» creata."
            if reassigned:
                note += f" {reassigned} spese spostate nella nuova categoria."

        elif action == "reclassify":
            ttype = payload.get("target_type")
            fc = FiscalClassification(payload.get("fiscal_classification"))
            if ttype == "document":
                doc = await db.get(Document, item.target_id)
                if not doc or doc.household_id != item.household_id:
                    return {"ok": False, "error": "documento non trovato"}
                doc.fiscal_classification = fc
            elif ttype == "expense":
                exp = await db.get(Expense, item.target_id)
                if not exp or exp.household_id != item.household_id:
                    return {"ok": False, "error": "spesa non trovata"}
                exp.fiscal_classification = fc
            else:
                return {"ok": False, "error": "target non valido"}
            note = f"Classificazione aggiornata a «{fc.value}»."

        elif action == "attribute":
            ttype = payload.get("target_type")
            payer = payload.get("payer_user_id")
            payer_uuid = uuid.UUID(str(payer)) if payer else None
            if ttype == "document":
                doc = await db.get(Document, item.target_id)
                if not doc or doc.household_id != item.household_id:
                    return {"ok": False, "error": "documento non trovato"}
                doc.payer_user_id = payer_uuid
            elif ttype == "expense":
                exp = await db.get(Expense, item.target_id)
                if not exp or exp.household_id != item.household_id:
                    return {"ok": False, "error": "spesa non trovata"}
                exp.payer_user_id = payer_uuid
            note = "Attribuzione aggiornata."

        else:
            # Avviso informativo: nessuna azione automatica, lo si prende in carico.
            note = "Voce presa in carico."

        item.status = ReviewStatus.APPLIED
        item.resolution_note = note
        # Le colonne DateTime sono naïve (TIMESTAMP WITHOUT TIME ZONE): usa un
        # UTC senza tzinfo per non mischiare naïve/aware in Postgres.
        item.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        item.resolved_by_user_id = user_id
        await db.commit()
        return {"ok": True, "note": note}
    except Exception as exc:  # pragma: no cover - difensivo
        await db.rollback()
        item.status = ReviewStatus.FAILED
        item.resolution_note = f"Errore applicazione: {exc}"
        await db.commit()
        return {"ok": False, "error": str(exc)}


async def pending_count(db: AsyncSession, household_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count(ReviewItem.id)).where(
                    ReviewItem.household_id == household_id,
                    ReviewItem.status == ReviewStatus.PENDING,
                )
            )
        ).scalar_one()
    )
