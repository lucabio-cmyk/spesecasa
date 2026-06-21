"""Gestione delle categorie merceologiche del nucleo.

Le categorie di base ("stabili") vivono in `app.enums.MERCHANDISE_CATEGORIES`
con la relativa descrizione in `MERCHANDISE_CATEGORY_INFO`. Oltre a queste, il
nucleo può avere categorie PERSONALIZZATE (tabella `expense_categories`), create
dall'agente quando nessuna di quelle esistenti descrive bene una spesa, o
dall'utente dalla GUI. Questo modulo unifica le due fonti ("categorie note") e
gestisce creazione/normalizzazione con anti-duplicazione.
"""

import re
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import (
    MERCHANDISE_CATEGORIES,
    MERCHANDISE_CATEGORY_INFO,
    SENSITIVE_CATEGORIES,
)
from app.models.category import ExpenseCategory

_BUILTIN_NAMES = frozenset(MERCHANDISE_CATEGORIES)
_MAX_NAME_LEN = 100
_MIN_NAME_LEN = 2


def normalize_name(name: str | None) -> str:
    """Normalizza un nome categoria: minuscolo, spazi ridotti, senza margini.
    Così "Abbigliamento  Bimbi" e "abbigliamento bimbi" sono la stessa cosa."""
    if not name:
        return ""
    return re.sub(r"\s+", " ", str(name).strip()).lower()[:_MAX_NAME_LEN]


def is_builtin(name: str | None) -> bool:
    return normalize_name(name) in _BUILTIN_NAMES


def builtin_categories() -> list[dict]:
    """Le categorie di base, con descrizione e flag di sensibilità."""
    return [
        {
            "name": name,
            "description": MERCHANDISE_CATEGORY_INFO.get(name),
            "examples": None,
            "builtin": True,
            "sensitive": name in SENSITIVE_CATEGORIES,
            "id": None,
            "source": "builtin",
        }
        for name in MERCHANDISE_CATEGORIES
    ]


def _custom_to_dict(c: ExpenseCategory) -> dict:
    return {
        "name": c.name,
        "description": c.description,
        "examples": c.examples,
        "builtin": False,
        "sensitive": False,
        "id": c.id,
        "source": c.source,
    }


async def list_custom(
    db: AsyncSession, household_id: uuid.UUID, include_inactive: bool = False
) -> list[ExpenseCategory]:
    stmt = select(ExpenseCategory).where(ExpenseCategory.household_id == household_id)
    if not include_inactive:
        stmt = stmt.where(ExpenseCategory.active.is_(True))
    stmt = stmt.order_by(ExpenseCategory.name)
    return list((await db.execute(stmt)).scalars())


async def known_categories(db: AsyncSession, household_id: uuid.UUID) -> list[dict]:
    """Tutte le categorie note al nucleo: di base + personalizzate attive."""
    customs = await list_custom(db, household_id)
    return builtin_categories() + [_custom_to_dict(c) for c in customs]


async def known_names(db: AsyncSession, household_id: uuid.UUID) -> set[str]:
    customs = await list_custom(db, household_id, include_inactive=True)
    return set(_BUILTIN_NAMES) | {c.name for c in customs}


def validate_name(name: str | None) -> tuple[str, str | None]:
    """Restituisce (nome_normalizzato, errore). errore=None se valido."""
    norm = normalize_name(name)
    if len(norm) < _MIN_NAME_LEN:
        return norm, "il nome della categoria è troppo corto"
    if not re.search(r"[a-zàèéìòù]", norm):
        return norm, "il nome della categoria deve contenere lettere"
    return norm, None


async def create_category(
    db: AsyncSession,
    household_id: uuid.UUID,
    name: str,
    description: str | None = None,
    examples: list[str] | None = None,
    source: str = "agent",
) -> dict:
    """Crea (o riusa) una categoria personalizzata. Idempotente e anti-duplicato:
    se il nome coincide con una categoria di base o con una personalizzata già
    esistente, NON la duplica e segnala lo stato."""
    norm, error = validate_name(name)
    if error:
        return {"created": False, "error": error}

    if norm in _BUILTIN_NAMES:
        return {
            "created": False,
            "builtin": True,
            "category": {"name": norm, "builtin": True},
            "message": f"'{norm}' è già una categoria di base: usala direttamente, non serve crearla.",
        }

    existing = (
        await db.execute(
            select(ExpenseCategory).where(
                ExpenseCategory.household_id == household_id,
                ExpenseCategory.name == norm,
            )
        )
    ).scalar_one_or_none()
    if existing:
        # Riattiva e arricchisce se mancano descrizione/esempi.
        changed = False
        if not existing.active:
            existing.active = True
            changed = True
        if description and not existing.description:
            existing.description = description.strip()
            changed = True
        if examples and not existing.examples:
            existing.examples = _clean_examples(examples)
            changed = True
        if changed:
            await db.commit()
            await db.refresh(existing)
        return {
            "created": False,
            "existing": True,
            "category": _custom_to_dict(existing),
            "message": f"la categoria '{norm}' esiste già: la riuso.",
        }

    category = ExpenseCategory(
        household_id=household_id,
        name=norm,
        description=description.strip() if description else None,
        examples=_clean_examples(examples),
        source=source if source in ("agent", "user") else "agent",
        active=True,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return {"created": True, "category": _custom_to_dict(category)}


def _clean_examples(examples: list[str] | None) -> list[str] | None:
    if not examples:
        return None
    cleaned = [str(e).strip() for e in examples if str(e).strip()]
    return cleaned[:20] or None


async def ensure_categories(
    db: AsyncSession, household_id: uuid.UUID, names: Iterable[str | None]
) -> list[str]:
    """Registra come personalizzate le categorie usate in una spesa che non sono
    né di base né già note. Mantiene il catalogo allineato a ciò che viene
    realmente archiviato. NON esegue commit: lo fa il chiamante (stessa
    transazione dell'inserimento spese). Ritorna i nomi appena registrati."""
    known = await known_names(db, household_id)
    created: list[str] = []
    for raw in names:
        norm = normalize_name(raw)
        if not norm or norm in known:
            continue
        valid, error = validate_name(norm)
        if error:
            continue
        db.add(
            ExpenseCategory(
                household_id=household_id, name=norm, source="agent", active=True
            )
        )
        known.add(norm)
        created.append(norm)
    return created
