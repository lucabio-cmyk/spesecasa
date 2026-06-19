import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    DocumentStatus,
    DocumentType,
    ExpenseScope,
    FiscalClassification,
    MERCHANDISE_CATEGORIES,
)
from app.models.document import Document
from app.models.expense import Expense
from app.models.user import User
from app.services import stats as stats_service
from app.services.resolvers import (
    find_existing_document,
    resolve_member_id,
    to_date,
    to_decimal,
)

_FISCAL = [c.value for c in FiscalClassification]
_SCOPE = [s.value for s in ExpenseScope]
_DOC_TYPE = [d.value for d in DocumentType]


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
        "name": "save_document",
        "description": "Salva/aggiorna i metadati (header) del documento in elaborazione: tipo, data, emittente, importo, classificazione fiscale, attribuzione e stato.",
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_type": {"type": "string", "enum": _DOC_TYPE},
                "doc_date": {"type": "string", "description": "AAAA-MM-GG"},
                "issuer": {"type": "string"},
                "total_amount": {"type": "number"},
                "payment_method": {"type": "string"},
                "document_number": {"type": "string"},
                "fiscal_year": {"type": "integer"},
                "fiscal_classification": {"type": "string", "enum": _FISCAL},
                "scope": {"type": "string", "enum": _SCOPE},
                "payer": {"type": "string", "description": "nome o id del soggetto pagante"},
                "beneficiary": {"type": "string", "description": "nome o id del beneficiario"},
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
                            "line_amount": {"type": "number"},
                            "discount": {"type": "number"},
                            "fiscal_classification": {"type": "string", "enum": _FISCAL},
                            "scope": {"type": "string", "enum": _SCOPE},
                            "payer": {"type": "string"},
                            "beneficiary": {"type": "string"},
                            "fiscal_year": {"type": "integer"},
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
                "line_amount": {"type": "number"},
                "discount": {"type": "number"},
                "fiscal_classification": {"type": "string", "enum": _FISCAL},
                "scope": {"type": "string", "enum": _SCOPE},
                "payer": {"type": "string", "description": "nome o id del soggetto pagante"},
                "beneficiary": {"type": "string", "description": "nome o id del beneficiario"},
                "fiscal_year": {"type": "integer"},
                "reliability_note": {"type": "string"},
            },
            "required": ["line_amount"],
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
            doc.total_amount = to_decimal(tool_input.get("total_amount")) or doc.total_amount
            doc.payment_method = tool_input.get("payment_method", doc.payment_method)
            doc.document_number = tool_input.get("document_number", doc.document_number)
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
                    line_amount=amount,
                    discount=to_decimal(line.get("discount")),
                    fiscal_classification=FiscalClassification(
                        line.get("fiscal_classification", FiscalClassification.NON_RILEVANTE.value)
                    ),
                    scope=ExpenseScope(line.get("scope", ExpenseScope.FAMILIARE.value)),
                    fiscal_year=fyear,
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
                line_amount=amount,
                discount=to_decimal(tool_input.get("discount")),
                fiscal_classification=FiscalClassification(
                    tool_input.get("fiscal_classification", FiscalClassification.NON_RILEVANTE.value)
                ),
                scope=ExpenseScope(tool_input.get("scope", ExpenseScope.FAMILIARE.value)),
                fiscal_year=fyear,
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
