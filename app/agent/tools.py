import base64
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    BillStatus,
    DocumentStatus,
    DocumentType,
    ExpenseScope,
    FiscalClassification,
    MERCHANDISE_CATEGORIES,
    UTILITY_DEFAULT_UNIT,
    UtilityType,
)
from app.models.bill import Bill
from app.models.document import Document
from app.models.expense import Expense
from app.models.property_unit import PropertyUnit
from app.models.user import User
from app.services import bills as bills_service
from app.services import search as search_service
from app.services import stats as stats_service
from app.services.resolvers import (
    find_existing_document,
    resolve_member_id,
    resolve_unit_id,
    to_date,
    to_decimal,
)
from app.services.storage import get_storage


def file_to_content_block(mime_type: str, data: bytes) -> dict:
    """Costruisce il blocco di contenuto (document/image) per passare un file
    originale al modello. Usato sia in fase di upload sia da read_document."""
    b64 = base64.standard_b64encode(data).decode()
    if mime_type == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    if mime_type and mime_type.startswith("image/"):
        return {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}}
    # fallback: prova come documento PDF
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}

_FISCAL = [c.value for c in FiscalClassification]
_SCOPE = [s.value for s in ExpenseScope]
_DOC_TYPE = [d.value for d in DocumentType]
_UTILITY = [u.value for u in UtilityType]
_BILL_STATUS = [s.value for s in BillStatus]


@dataclass
class AgentContext:
    household_id: uuid.UUID
    user_id: uuid.UUID
    document_id: uuid.UUID | None = None


# --- Schemi degli strumenti esposti al modello -----------------------------
TOOLS = [
    {
        "name": "list_household_members",
        "description": "Elenca i membri del nucleo familiare (id, nome, codice fiscale, ruolo). Usalo per attribuire correttamente soggetto pagante e beneficiario.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_property_units",
        "description": (
            "Elenca le UNITÀ IMMOBILIARI configurate dal nucleo (casa/e, appartamenti, "
            "box, ...). Per ognuna: id, nome, indirizzo, alias (come compare nei documenti: "
            "interno/scala/subalterno, codice condòmino, nomi intestatari), nome del "
            "condominio, intestatario, millesimi, se è l'unità principale e note di "
            "addestramento. USALO quando elabori una spesa di CONDOMINIO o un VERBALE DI "
            "ASSEMBLEA per capire a quale unità del nucleo si riferisce il documento, "
            "soprattutto se nel documento compaiono più unità/condòmini."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "find_existing_document",
        "description": "Verifica se un documento esiste gia (anti-duplicazione), per hash del file o per data+emittente+importo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_hash": {"type": "string"},
                "doc_date": {"type": "string", "description": "AAAA-MM-GG"},
                "issuer": {"type": "string"},
                "total_amount": {"type": "number"},
            },
        },
    },
    {
        "name": "search_documents",
        "description": (
            "Cerca nei DOCUMENTI archiviati per SIGNIFICATO (ricerca semantica) oltre che per "
            "parole chiave: utile per ritrovare un documento di cui non si ricordano gli "
            "estremi esatti (es. 'la fattura del dentista dell'anno scorso', 'la polizza "
            "auto', 'lo scontrino della farmacia'). Restituisce i documenti più pertinenti "
            "con id, tipo, emittente, data, importo, sintesi e punteggio. Usalo per trovare "
            "il document_id da passare poi a read_document quando serve aprire l'originale."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "cosa stai cercando, in linguaggio naturale"},
                "limit": {"type": "integer", "description": "max risultati (default 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_document",
        "description": (
            "Apri e RILEGGI il file originale (PDF/immagine) di un documento già archiviato "
            "per analizzarlo di nuovo: rileggere righe e importi, estrarre dettagli non ancora "
            "salvati, o rispondere a una domanda dell'utente sul contenuto del documento. "
            "Indica document_id (ottenuto da find_existing_document/find_expenses, dalla lista "
            "documenti, o indicato dall'utente); in fase di elaborazione di un upload puoi "
            "ometterlo per rileggere il documento corrente. Usalo solo quando serve davvero "
            "guardare l'originale: il file verrà allegato come contenuto nella risposta dello "
            "strumento. Dopo averlo letto, se aggiorni dei dati persistili con save_document/"
            "add_expenses/save_bill."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "id del documento da rileggere (opzionale durante l'elaborazione di un upload)"},
            },
        },
    },
    {
        "name": "save_document",
        "description": (
            "Salva/aggiorna i metadati (header) del documento in elaborazione: tipo, data, "
            "emittente, importi, classificazione fiscale, attribuzione e stato. Estrai e "
            "conserva quanti più dati possibile tra quelli realmente presenti sul documento "
            "(non inventarli): partita IVA/CF dell'emittente, intestatario e suo codice "
            "fiscale, imponibile e IVA, valuta, scadenza di pagamento, tracciabilità del "
            "pagamento. Per qualunque altro dato utile non previsto dai campi (es. IBAN, "
            "POD/PDR, codice tributo F24, numero pratica, targa, periodo di competenza) usa "
            "il campo libero 'details' come oggetto chiave→valore."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_type": {"type": "string", "enum": _DOC_TYPE},
                "doc_date": {"type": "string", "description": "AAAA-MM-GG"},
                "issuer": {"type": "string", "description": "nome dell'emittente/negozio"},
                "issuer_vat": {"type": "string", "description": "partita IVA o codice fiscale dell'emittente"},
                "recipient_name": {"type": "string", "description": "intestatario del documento (a chi è intestato)"},
                "recipient_fiscal_code": {"type": "string", "description": "codice fiscale dell'intestatario"},
                "total_amount": {"type": "number", "description": "importo totale (lordo)"},
                "taxable_amount": {"type": "number", "description": "imponibile (al netto IVA)"},
                "vat_amount": {"type": "number", "description": "importo IVA"},
                "currency": {"type": "string", "description": "valuta ISO, es. EUR (default EUR)"},
                "payment_method": {"type": "string"},
                "payment_traceability": {"type": "string", "description": "nota su tracciabilità del pagamento (carta/bonifico vs contanti): incide sulla detraibilità"},
                "document_number": {"type": "string"},
                "due_date": {"type": "string", "description": "scadenza di pagamento AAAA-MM-GG (fatture/F24/avvisi)"},
                "fiscal_year": {"type": "integer"},
                "fiscal_classification": {"type": "string", "enum": _FISCAL},
                "scope": {"type": "string", "enum": _SCOPE},
                "payer": {"type": "string", "description": "nome o id del soggetto pagante"},
                "beneficiary": {"type": "string", "description": "nome o id del beneficiario"},
                "tags": {"type": "string", "description": "parole chiave separate da virgola (es. 'farmacia, ticket, dentista')"},
                "details": {"type": "object", "description": "dati strutturati aggiuntivi presenti sul documento (chiave→valore)"},
                "reliability_note": {"type": "string"},
                "retention_note": {"type": "string"},
                "status": {"type": "string", "enum": [s.value for s in DocumentStatus]},
            },
        },
    },
    {
        "name": "add_expenses",
        "description": "Aggiunge una o piu righe/movimenti di spesa collegati al documento in elaborazione. Per gli scontrini, una riga per articolo con categoria merceologica.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lines": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "purchase_date": {"type": "string", "description": "AAAA-MM-GG"},
                            "merchant": {"type": "string"},
                            "description_original": {"type": "string"},
                            "description_normalized": {"type": "string"},
                            "merch_category": {"type": "string", "enum": MERCHANDISE_CATEGORIES},
                            "quantity": {"type": "number"},
                            "unit_price": {"type": "number", "description": "prezzo unitario, se indicato"},
                            "line_amount": {"type": "number"},
                            "discount": {"type": "number"},
                            "fiscal_classification": {"type": "string", "enum": _FISCAL},
                            "scope": {"type": "string", "enum": _SCOPE},
                            "payer": {"type": "string"},
                            "beneficiary": {"type": "string"},
                            "fiscal_year": {"type": "integer"},
                            "details": {"type": "object", "description": "dati aggiuntivi della riga (es. aliquota IVA, reparto, codice prodotto)"},
                            "reliability_note": {"type": "string"},
                        },
                        "required": ["line_amount"],
                    },
                }
            },
            "required": ["lines"],
        },
    },
    {
        "name": "record_expense",
        "description": "Registra una spesa descritta dall'utente in chat, SENZA documento allegato. Usalo quando l'utente racconta una spesa a parole (es. 'ho speso 45 euro in farmacia oggi'). line_amount e obbligatorio: se manca, NON inventarlo, chiedi all'utente. Se la spesa puo essere fiscalmente rilevante e mancano soggetto pagante/beneficiario, chiedili prima di registrare.",
        "input_schema": {
            "type": "object",
            "properties": {
                "purchase_date": {"type": "string", "description": "AAAA-MM-GG"},
                "merchant": {"type": "string", "description": "negozio o emittente"},
                "description_original": {"type": "string", "description": "cosa ha detto l'utente"},
                "description_normalized": {"type": "string", "description": "descrizione chiara e sintetica"},
                "merch_category": {"type": "string", "enum": MERCHANDISE_CATEGORIES},
                "quantity": {"type": "number"},
                "unit_price": {"type": "number", "description": "prezzo unitario, se indicato"},
                "line_amount": {"type": "number"},
                "discount": {"type": "number"},
                "fiscal_classification": {"type": "string", "enum": _FISCAL},
                "scope": {"type": "string", "enum": _SCOPE},
                "payer": {"type": "string", "description": "nome o id del soggetto pagante"},
                "beneficiary": {"type": "string", "description": "nome o id del beneficiario"},
                "fiscal_year": {"type": "integer"},
                "details": {"type": "object", "description": "dati aggiuntivi della spesa (chiave→valore)"},
                "reliability_note": {"type": "string"},
            },
            "required": ["line_amount"],
        },
    },
    {
        "name": "save_bill",
        "description": (
            "Registra una BOLLETTA / spesa di casa ricorrente (luce, gas, acqua, "
            "rifiuti/TARI, internet/telefono, riscaldamento, condominio, ...) estratta "
            "dal documento in elaborazione. Usalo per le bollette al posto di add_expenses, "
            "per abilitare valutazione dei costi (consumi, costo unitario, andamento) e "
            "amministrazione (scadenze, stato pagamento). Estrai periodo di competenza, "
            "scadenza, importo totale e, se presenti, consumo con unità (kWh/Smc/m³) e "
            "scomposizione del costo. Non inventare i valori mancanti."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "utility_type": {"type": "string", "enum": _UTILITY},
                "supplier": {"type": "string", "description": "fornitore/emittente"},
                "service_id": {"type": "string", "description": "POD (luce), PDR (gas) o codice cliente"},
                "bill_number": {"type": "string"},
                "period_start": {"type": "string", "description": "inizio competenza AAAA-MM-GG"},
                "period_end": {"type": "string", "description": "fine competenza AAAA-MM-GG"},
                "issue_date": {"type": "string", "description": "data emissione AAAA-MM-GG"},
                "due_date": {"type": "string", "description": "scadenza pagamento AAAA-MM-GG"},
                "total_amount": {"type": "number"},
                "energy_cost": {"type": "number", "description": "costo materia prima (energia/gas)"},
                "fixed_cost": {"type": "number", "description": "quote fisse/trasporto/gestione"},
                "taxes": {"type": "number", "description": "imposte/accise/IVA"},
                "consumption_quantity": {"type": "number"},
                "consumption_unit": {"type": "string", "description": "kWh, Smc, m³, ..."},
                "status": {"type": "string", "enum": _BILL_STATUS},
                "payment_method": {"type": "string", "description": "domiciliazione/RID, bonifico, ..."},
                "payer": {"type": "string", "description": "intestatario/soggetto che paga"},
                "property_unit": {"type": "string", "description": "unità immobiliare a cui si riferisce (nome, alias o id da list_property_units): essenziale per il condominio quando il nucleo ha più unità"},
                "fiscal_year": {"type": "integer"},
                "reliability_note": {"type": "string"},
                "notes": {"type": "string"},
                "details": {"type": "object", "description": "dati strutturati liberi: per il condominio salva qui l'analisi del verbale/riparto (deliberazioni rilevanti, quota ordinaria/straordinaria, fondo, lavori potenzialmente agevolabili con bonus, elenco rate e scadenze, millesimi applicati)"},
            },
        },
    },
    {
        "name": "record_bill",
        "description": (
            "Registra una bolletta descritta a parole in chat, SENZA documento allegato "
            "(es. 'bolletta della luce di 84 euro in scadenza il 30/06'). total_amount o "
            "utility_type sono il minimo utile: se mancano entrambi chiedi all'utente. "
            "Stessi campi di save_bill."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "utility_type": {"type": "string", "enum": _UTILITY},
                "supplier": {"type": "string"},
                "service_id": {"type": "string"},
                "bill_number": {"type": "string"},
                "period_start": {"type": "string", "description": "AAAA-MM-GG"},
                "period_end": {"type": "string", "description": "AAAA-MM-GG"},
                "issue_date": {"type": "string", "description": "AAAA-MM-GG"},
                "due_date": {"type": "string", "description": "AAAA-MM-GG"},
                "total_amount": {"type": "number"},
                "energy_cost": {"type": "number"},
                "fixed_cost": {"type": "number"},
                "taxes": {"type": "number"},
                "consumption_quantity": {"type": "number"},
                "consumption_unit": {"type": "string"},
                "status": {"type": "string", "enum": _BILL_STATUS},
                "payment_method": {"type": "string"},
                "payer": {"type": "string"},
                "property_unit": {"type": "string", "description": "unità immobiliare a cui si riferisce (nome, alias o id)"},
                "fiscal_year": {"type": "integer"},
                "reliability_note": {"type": "string"},
                "notes": {"type": "string"},
                "details": {"type": "object", "description": "dati strutturati liberi (es. per il condominio: deliberazioni, quota ordinaria/straordinaria, rate)"},
            },
        },
    },
    {
        "name": "query_bills",
        "description": (
            "Analizza le bollette/spese di casa del nucleo: valutazione costi per tipo di "
            "utenza (totale, medio, costo unitario), andamento nel tempo e scadenzario "
            "(bollette scadute e in arrivo non pagate). Usalo per domande tipo 'quanto "
            "spendo di luce?', 'è aumentato il gas?', 'quali bollette devo pagare?'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fiscal_year": {"type": "integer"},
                "utility_type": {"type": "string", "enum": _UTILITY},
                "property_unit": {"type": "string", "description": "limita l'analisi a un'unità immobiliare (nome, alias o id)"},
                "include_upcoming": {"type": "boolean", "description": "includi lo scadenzario"},
            },
        },
    },
    {
        "name": "query_expenses",
        "description": "Interroga lo storico spese del nucleo con filtri e restituisce aggregati (totale, per categoria, per classificazione fiscale).",
        "input_schema": {
            "type": "object",
            "properties": {
                "fiscal_year": {"type": "integer"},
                "category": {"type": "string"},
                "classification": {"type": "string", "enum": _FISCAL},
            },
        },
    },
    {
        "name": "find_expenses",
        "description": (
            "Cerca SINGOLE spese/movimenti del nucleo (non aggregati) per individuarne una "
            "da correggere o cancellare. Restituisce id, data, negozio, descrizione, importo, "
            "categoria e se proviene da un documento. Filtri opzionali: testo (negozio/"
            "descrizione), anno, categoria, data esatta. Usalo PRIMA di delete_expense per "
            "trovare l'id corretto e per mostrare all'utente le candidate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "testo cercato in negozio/descrizione"},
                "fiscal_year": {"type": "integer"},
                "category": {"type": "string", "enum": MERCHANDISE_CATEGORIES},
                "purchase_date": {"type": "string", "description": "AAAA-MM-GG"},
                "limit": {"type": "integer", "description": "max risultati (default 20)"},
            },
        },
    },
    {
        "name": "delete_expense",
        "description": (
            "Cancella DEFINITIVAMENTE una spesa/movimento dato il suo id (ottenuto da "
            "find_expenses). Operazione irreversibile: usala solo dopo aver individuato con "
            "certezza la spesa e aver ricevuto conferma dall'utente. Se la spesa proviene da "
            "un documento (from_document=true) avvisa l'utente che la cifra del documento "
            "potrebbe non quadrare più, e procedi solo se confermato."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "expense_id": {"type": "string", "description": "id della spesa da cancellare"},
            },
            "required": ["expense_id"],
        },
    },
    {
        "name": "get_yearly_summary",
        "description": "Riepilogo annuale del nucleo: totale e ripartizione per classificazione fiscale; opzionalmente filtrato per soggetto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fiscal_year": {"type": "integer"},
                "subject": {"type": "string", "description": "nome o id del soggetto"},
            },
            "required": ["fiscal_year"],
        },
    },
]


# --- Dispatcher -------------------------------------------------------------
async def dispatch(name: str, tool_input: dict, db: AsyncSession, ctx: AgentContext) -> dict:
    try:
        if name == "list_household_members":
            res = await db.execute(select(User).where(User.household_id == ctx.household_id))
            return {
                "members": [
                    {
                        "id": str(u.id),
                        "full_name": u.full_name,
                        "codice_fiscale": u.codice_fiscale,
                        "role": str(u.role),
                    }
                    for u in res.scalars()
                ]
            }

        if name == "list_property_units":
            res = await db.execute(
                select(PropertyUnit)
                .where(PropertyUnit.household_id == ctx.household_id)
                .order_by(PropertyUnit.is_primary.desc(), PropertyUnit.name)
            )
            return {
                "units": [
                    {
                        "id": str(u.id),
                        "name": u.name,
                        "address": u.address,
                        "aliases": u.aliases,
                        "owner_name": u.owner_name,
                        "condominium_name": u.condominium_name,
                        "millesimi": str(u.millesimi) if u.millesimi is not None else None,
                        "is_primary": u.is_primary,
                        "notes": u.notes,
                        "details": u.details,
                    }
                    for u in res.scalars()
                ]
            }

        if name == "find_existing_document":
            found = await find_existing_document(
                db,
                ctx.household_id,
                file_hash=tool_input.get("file_hash"),
                doc_date=to_date(tool_input.get("doc_date")),
                issuer=tool_input.get("issuer"),
                total_amount=to_decimal(tool_input.get("total_amount")),
            )
            if found:
                return {"found": True, "document_id": str(found.id), "summary": found.summary}
            return {"found": False}

        if name == "search_documents":
            hits, mode = await search_service.search_documents(
                db, ctx.household_id, tool_input.get("query", ""), tool_input.get("limit") or 10
            )
            return {
                "mode": mode,
                "count": len(hits),
                "documents": [
                    {
                        "id": str(doc.id),
                        "doc_type": str(doc.doc_type),
                        "issuer": doc.issuer,
                        "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
                        "total_amount": str(doc.total_amount) if doc.total_amount is not None else None,
                        "fiscal_year": doc.fiscal_year,
                        "summary": doc.summary,
                        "score": round(score, 4) if score is not None else None,
                    }
                    for doc, score in hits
                ],
            }

        if name == "read_document":
            raw_id = tool_input.get("document_id") or ctx.document_id
            if not raw_id:
                return {"ok": False, "error": "nessun document_id indicato"}
            try:
                doc_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError):
                return {"ok": False, "error": "document_id non valido"}
            doc = await db.get(Document, doc_id)
            if not doc or doc.household_id != ctx.household_id:
                return {"ok": False, "error": "documento non trovato"}
            try:
                data = get_storage().read(doc.storage_path)
            except Exception as exc:
                return {"ok": False, "error": f"impossibile leggere il file originale: {exc}"}
            # Il blocco file (PDF/immagine) viene allegato dal runner alla risposta
            # dello strumento tramite la chiave speciale _content_blocks.
            return {
                "ok": True,
                "document_id": str(doc.id),
                "original_filename": doc.original_filename,
                "mime_type": doc.mime_type,
                "doc_type": str(doc.doc_type),
                "note": "File originale allegato di seguito: analizzalo per rispondere o per estrarre nuovi dettagli.",
                "_content_blocks": [file_to_content_block(doc.mime_type, data)],
            }

        if name == "save_document":
            if not ctx.document_id:
                return {"ok": False, "error": "nessun documento in elaborazione"}
            doc = await db.get(Document, ctx.document_id)
            if not doc:
                return {"ok": False, "error": "documento non trovato"}
            if "doc_type" in tool_input:
                doc.doc_type = DocumentType(tool_input["doc_type"])
            if "fiscal_classification" in tool_input:
                doc.fiscal_classification = FiscalClassification(tool_input["fiscal_classification"])
            if "scope" in tool_input:
                doc.scope = ExpenseScope(tool_input["scope"])
            if "status" in tool_input:
                doc.status = DocumentStatus(tool_input["status"])
            doc.doc_date = to_date(tool_input.get("doc_date")) or doc.doc_date
            doc.issuer = tool_input.get("issuer", doc.issuer)
            doc.issuer_vat = tool_input.get("issuer_vat", doc.issuer_vat)
            doc.recipient_name = tool_input.get("recipient_name", doc.recipient_name)
            doc.recipient_fiscal_code = tool_input.get("recipient_fiscal_code", doc.recipient_fiscal_code)
            doc.total_amount = to_decimal(tool_input.get("total_amount")) or doc.total_amount
            doc.taxable_amount = to_decimal(tool_input.get("taxable_amount")) or doc.taxable_amount
            doc.vat_amount = to_decimal(tool_input.get("vat_amount")) or doc.vat_amount
            doc.currency = tool_input.get("currency", doc.currency)
            doc.payment_method = tool_input.get("payment_method", doc.payment_method)
            doc.payment_traceability = tool_input.get("payment_traceability", doc.payment_traceability)
            doc.document_number = tool_input.get("document_number", doc.document_number)
            doc.due_date = to_date(tool_input.get("due_date")) or doc.due_date
            doc.tags = tool_input.get("tags", doc.tags)
            new_details = tool_input.get("details")
            if isinstance(new_details, dict) and new_details:
                # merge non distruttivo: conserva dettagli già estratti in passate precedenti
                doc.details = {**(doc.details or {}), **new_details}
            doc.reliability_note = tool_input.get("reliability_note", doc.reliability_note)
            doc.retention_note = tool_input.get("retention_note", doc.retention_note)
            if tool_input.get("fiscal_year"):
                doc.fiscal_year = int(tool_input["fiscal_year"])
            elif doc.doc_date:
                doc.fiscal_year = doc.doc_date.year
            doc.payer_user_id = (
                await resolve_member_id(db, ctx.household_id, tool_input.get("payer"))
                or doc.payer_user_id
            )
            doc.beneficiary_user_id = (
                await resolve_member_id(db, ctx.household_id, tool_input.get("beneficiary"))
                or doc.beneficiary_user_id
            )
            await db.commit()
            return {"ok": True, "document_id": str(doc.id), "fiscal_year": doc.fiscal_year}

        if name == "add_expenses":
            if not ctx.document_id:
                return {"ok": False, "error": "nessun documento in elaborazione"}
            doc = await db.get(Document, ctx.document_id)
            if not doc:
                return {"ok": False, "error": "documento non trovato"}
            inserted = 0
            for line in tool_input.get("lines", []):
                amount = to_decimal(line.get("line_amount"))
                if amount is None:
                    continue
                pdate = to_date(line.get("purchase_date")) or (doc.doc_date if doc else None)
                fyear = line.get("fiscal_year")
                if fyear:
                    fyear = int(fyear)
                elif pdate:
                    fyear = pdate.year
                elif doc:
                    fyear = doc.fiscal_year
                payer = await resolve_member_id(db, ctx.household_id, line.get("payer"))
                beneficiary = await resolve_member_id(db, ctx.household_id, line.get("beneficiary"))
                expense = Expense(
                    household_id=ctx.household_id,
                    document_id=ctx.document_id,
                    payer_user_id=payer or (doc.payer_user_id if doc else None),
                    beneficiary_user_id=beneficiary or (doc.beneficiary_user_id if doc else None),
                    purchase_date=pdate,
                    merchant=line.get("merchant") or (doc.issuer if doc else None),
                    description_original=line.get("description_original"),
                    description_normalized=line.get("description_normalized"),
                    merch_category=line.get("merch_category"),
                    quantity=to_decimal(line.get("quantity")),
                    unit_price=to_decimal(line.get("unit_price")),
                    line_amount=amount,
                    discount=to_decimal(line.get("discount")),
                    fiscal_classification=FiscalClassification(
                        line.get("fiscal_classification", FiscalClassification.NON_RILEVANTE.value)
                    ),
                    scope=ExpenseScope(line.get("scope", ExpenseScope.FAMILIARE.value)),
                    fiscal_year=fyear,
                    details=line.get("details") if isinstance(line.get("details"), dict) else None,
                    reliability_note=line.get("reliability_note"),
                )
                db.add(expense)
                inserted += 1
            await db.commit()
            return {"ok": True, "inserted": inserted}

        if name == "record_expense":
            amount = to_decimal(tool_input.get("line_amount"))
            if amount is None:
                return {"ok": False, "error": "manca l'importo: chiedi all'utente quanto ha speso prima di registrare"}
            pdate = to_date(tool_input.get("purchase_date"))
            fyear = tool_input.get("fiscal_year")
            if fyear:
                fyear = int(fyear)
            elif pdate:
                fyear = pdate.year
            payer = await resolve_member_id(db, ctx.household_id, tool_input.get("payer"))
            beneficiary = await resolve_member_id(db, ctx.household_id, tool_input.get("beneficiary"))
            expense = Expense(
                household_id=ctx.household_id,
                document_id=None,  # spesa manuale, senza documento allegato
                payer_user_id=payer or ctx.user_id,
                beneficiary_user_id=beneficiary,
                purchase_date=pdate,
                merchant=tool_input.get("merchant"),
                description_original=tool_input.get("description_original"),
                description_normalized=tool_input.get("description_normalized"),
                merch_category=tool_input.get("merch_category"),
                quantity=to_decimal(tool_input.get("quantity")),
                unit_price=to_decimal(tool_input.get("unit_price")),
                line_amount=amount,
                discount=to_decimal(tool_input.get("discount")),
                fiscal_classification=FiscalClassification(
                    tool_input.get("fiscal_classification", FiscalClassification.NON_RILEVANTE.value)
                ),
                scope=ExpenseScope(tool_input.get("scope", ExpenseScope.FAMILIARE.value)),
                fiscal_year=fyear,
                details=tool_input.get("details") if isinstance(tool_input.get("details"), dict) else None,
                reliability_note=tool_input.get("reliability_note"),
            )
            db.add(expense)
            await db.commit()
            await db.refresh(expense)
            return {
                "ok": True,
                "expense_id": str(expense.id),
                "line_amount": str(expense.line_amount),
                "fiscal_year": expense.fiscal_year,
                "payer_user_id": str(expense.payer_user_id) if expense.payer_user_id else None,
            }

        if name == "find_expenses":
            stmt = (
                select(Expense)
                .where(Expense.household_id == ctx.household_id)
                .order_by(Expense.purchase_date.desc().nullslast(), Expense.created_at.desc())
            )
            if tool_input.get("fiscal_year"):
                stmt = stmt.where(Expense.fiscal_year == int(tool_input["fiscal_year"]))
            if tool_input.get("category"):
                stmt = stmt.where(Expense.merch_category == tool_input["category"])
            pdate = to_date(tool_input.get("purchase_date"))
            if pdate:
                stmt = stmt.where(Expense.purchase_date == pdate)
            needle = (tool_input.get("query") or "").strip().lower()
            if needle:
                like = f"%{needle}%"
                stmt = stmt.where(
                    func.lower(func.coalesce(Expense.merchant, ""))
                    .concat(" ")
                    .concat(func.lower(func.coalesce(Expense.description_normalized, "")))
                    .concat(" ")
                    .concat(func.lower(func.coalesce(Expense.description_original, "")))
                    .like(like)
                )
            limit = int(tool_input.get("limit") or 20)
            stmt = stmt.limit(max(1, min(limit, 50)))
            res = await db.execute(stmt)
            rows = list(res.scalars())
            return {
                "count": len(rows),
                "expenses": [
                    {
                        "id": str(e.id),
                        "purchase_date": e.purchase_date.isoformat() if e.purchase_date else None,
                        "merchant": e.merchant,
                        "description": e.description_normalized or e.description_original,
                        "line_amount": str(e.line_amount),
                        "merch_category": e.merch_category,
                        "fiscal_classification": str(e.fiscal_classification),
                        "from_document": e.document_id is not None,
                    }
                    for e in rows
                ],
            }

        if name == "delete_expense":
            raw_id = tool_input.get("expense_id")
            try:
                expense_id = uuid.UUID(str(raw_id))
            except (ValueError, TypeError):
                return {"ok": False, "error": "expense_id non valido"}
            expense = await db.get(Expense, expense_id)
            if not expense or expense.household_id != ctx.household_id:
                return {"ok": False, "error": "spesa non trovata"}
            snapshot = {
                "id": str(expense.id),
                "purchase_date": expense.purchase_date.isoformat() if expense.purchase_date else None,
                "merchant": expense.merchant,
                "description": expense.description_normalized or expense.description_original,
                "line_amount": str(expense.line_amount),
                "from_document": expense.document_id is not None,
            }
            await db.delete(expense)
            await db.commit()
            return {"ok": True, "deleted": snapshot}

        if name in ("save_bill", "record_bill"):
            doc_id = ctx.document_id if name == "save_bill" else None
            doc = await db.get(Document, doc_id) if doc_id else None
            utype_raw = tool_input.get("utility_type")
            utype = UtilityType(utype_raw) if utype_raw in _UTILITY else UtilityType.ALTRO
            period_end = to_date(tool_input.get("period_end"))
            period_start = to_date(tool_input.get("period_start"))
            issue_date = to_date(tool_input.get("issue_date"))
            due_date = to_date(tool_input.get("due_date"))
            fyear = tool_input.get("fiscal_year")
            if fyear:
                fyear = int(fyear)
            else:
                ref = period_end or period_start or issue_date or due_date
                fyear = ref.year if ref else (doc.fiscal_year if doc else None)
            unit = tool_input.get("consumption_unit") or UTILITY_DEFAULT_UNIT.get(utype.value) or None
            status_raw = tool_input.get("status")
            status = BillStatus(status_raw) if status_raw in _BILL_STATUS else BillStatus.DA_PAGARE
            payer = await resolve_member_id(db, ctx.household_id, tool_input.get("payer"))
            unit_id = await resolve_unit_id(db, ctx.household_id, tool_input.get("property_unit"))
            bill_details = tool_input.get("details")
            if not isinstance(bill_details, dict) or not bill_details:
                bill_details = None
            # Importo 0,00 è valido (es. nota di credito/conguaglio): usa il
            # fallback del documento solo se l'importo è davvero assente (None).
            total = to_decimal(tool_input.get("total_amount"))
            if total is None and doc:
                total = doc.total_amount
            bill = Bill(
                household_id=ctx.household_id,
                document_id=doc_id,
                payer_user_id=payer or (doc.payer_user_id if doc else None),
                property_unit_id=unit_id,
                utility_type=utype,
                supplier=tool_input.get("supplier") or (doc.issuer if doc else None),
                service_id=tool_input.get("service_id"),
                bill_number=tool_input.get("bill_number"),
                period_start=period_start,
                period_end=period_end,
                issue_date=issue_date or (doc.doc_date if doc else None),
                due_date=due_date,
                total_amount=total,
                energy_cost=to_decimal(tool_input.get("energy_cost")),
                fixed_cost=to_decimal(tool_input.get("fixed_cost")),
                taxes=to_decimal(tool_input.get("taxes")),
                consumption_quantity=to_decimal(tool_input.get("consumption_quantity")),
                consumption_unit=unit,
                status=status,
                payment_method=tool_input.get("payment_method"),
                fiscal_year=fyear,
                reliability_note=tool_input.get("reliability_note"),
                notes=tool_input.get("notes"),
                details=bill_details,
            )
            if bill.total_amount is None and utype is UtilityType.ALTRO:
                return {
                    "ok": False,
                    "error": "manca sia l'importo sia il tipo di utenza: chiedi all'utente",
                }
            # Se è un documento, marcalo come bolletta per coerenza dell'archivio.
            if doc and doc.doc_type != DocumentType.BOLLETTA:
                doc.doc_type = DocumentType.BOLLETTA
            db.add(bill)
            await db.commit()
            await db.refresh(bill)
            return {
                "ok": True,
                "bill_id": str(bill.id),
                "utility_type": str(bill.utility_type),
                "total_amount": str(bill.total_amount) if bill.total_amount is not None else None,
                "due_date": bill.due_date.isoformat() if bill.due_date else None,
                "status": str(bill.status),
                "fiscal_year": bill.fiscal_year,
                "property_unit_id": str(bill.property_unit_id) if bill.property_unit_id else None,
            }

        if name == "query_bills":
            year = tool_input.get("fiscal_year")
            year = int(year) if year else None
            unit_id = await resolve_unit_id(db, ctx.household_id, tool_input.get("property_unit"))
            result = {
                "cost_analysis": await bills_service.cost_analysis(
                    db, ctx.household_id, year, unit_id
                ),
                "trend": await bills_service.trend(
                    db, ctx.household_id, tool_input.get("utility_type"), year, unit_id
                ),
            }
            if tool_input.get("include_upcoming"):
                result["upcoming"] = await bills_service.upcoming(
                    db, ctx.household_id, unit_id=unit_id
                )
            return result

        if name == "query_expenses":
            year = tool_input.get("fiscal_year")
            return {
                "by_category": await stats_service.by_category(db, ctx.household_id, year),
                "fiscal_summary": await stats_service.fiscal_summary(db, ctx.household_id, year),
            }

        if name == "get_yearly_summary":
            year = int(tool_input["fiscal_year"])
            return {
                "year": year,
                "fiscal_summary": await stats_service.fiscal_summary(db, ctx.household_id, year),
                "by_member": await stats_service.by_member(db, ctx.household_id, year),
            }

        return {"error": f"strumento sconosciuto: {name}"}
    except Exception as exc:  # difensivo: l'errore torna al modello
        await db.rollback()
        return {"ok": False, "error": str(exc)}
