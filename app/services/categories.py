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
    MERCHANDISE_CATEGORY_GROUP,
    MERCHANDISE_CATEGORY_INFO,
    MERCHANDISE_GROUP_INFO,
    RESERVED_GROUP_SYNONYMS,
    SENSITIVE_CATEGORIES,
)
from app.models.category import ExpenseCategory

_BUILTIN_NAMES = frozenset(MERCHANDISE_CATEGORIES)
_BUILTIN_GROUPS = frozenset(MERCHANDISE_GROUP_INFO)
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


def is_group(name: str | None) -> bool:
    """True se il nome è una macro-categoria (gruppo) di base, es. 'spesa
    supermercato'. I gruppi non vanno usati direttamente come `merch_category`."""
    return normalize_name(name) in _BUILTIN_GROUPS


def reserved_redirect(name: str | None) -> str | None:
    """Se `name` è un sinonimo generico del supermercato o il nome di un gruppo,
    restituisce la sottocategoria di base da usare al suo posto (così non si
    creano doppioni del gruppo); altrimenti None."""
    norm = normalize_name(name)
    if norm in RESERVED_GROUP_SYNONYMS:
        return RESERVED_GROUP_SYNONYMS[norm]
    return None


def builtin_groups() -> list[dict]:
    """Le macro-categorie (gruppi) di base, con la relativa descrizione."""
    return [
        {"name": name, "description": desc}
        for name, desc in MERCHANDISE_GROUP_INFO.items()
    ]


def builtin_categories() -> list[dict]:
    """Le categorie di base (foglie), con descrizione, gruppo e sensibilità."""
    return [
        {
            "name": name,
            "parent": MERCHANDISE_CATEGORY_GROUP.get(name),
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
        "parent": c.parent,
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


async def known_groups(db: AsyncSession, household_id: uuid.UUID) -> set[str]:
    """Macro-categorie note al nucleo: i gruppi di base più i `parent` usati
    dalle categorie personalizzate (così l'agente può riusarli)."""
    customs = await list_custom(db, household_id)
    groups = set(_BUILTIN_GROUPS)
    groups.update(c.parent for c in customs if c.parent)
    return groups


async def leaf_to_group(db: AsyncSession, household_id: uuid.UUID) -> dict[str, str]:
    """Mappa categoria-foglia → macro-categoria (gruppo) per il roll-up nelle
    statistiche. Le foglie senza padre (es. 'farmaci' o le macro personalizzate)
    sono mappate su se stesse. Include base + personalizzate."""
    mapping: dict[str, str] = {}
    for name, grp in MERCHANDISE_CATEGORY_GROUP.items():
        mapping[name] = grp or name
    for c in await list_custom(db, household_id, include_inactive=True):
        mapping[c.name] = c.parent or c.name
    return mapping


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
    parent: str | None = None,
    source: str = "agent",
) -> dict:
    """Crea (o riusa) una categoria personalizzata. Idempotente e anti-duplicato:
    se il nome coincide con una categoria di base o con una personalizzata già
    esistente, NON la duplica e segnala lo stato. `parent` colloca la categoria
    sotto una macro-categoria (gruppo) per mantenere la gerarchia coerente."""
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

    # Anti-doppione: i sinonimi generici del supermercato (e i nomi dei gruppi)
    # non diventano nuove categorie, ma rimandano alla sottocategoria di base.
    redirect = reserved_redirect(norm)
    if redirect:
        return {
            "created": False,
            "builtin": True,
            "category": {"name": redirect, "builtin": True},
            "message": (
                f"'{norm}' è troppo generico (è di fatto il gruppo «spesa "
                f"supermercato»): usa la categoria di base '{redirect}' o una "
                "sottocategoria di reparto più precisa, non creare un doppione."
            ),
        }

    # Normalizza/valida il gruppo: ammessi solo i gruppi di base noti.
    parent_norm = normalize_name(parent) or None
    if parent_norm and parent_norm not in _BUILTIN_GROUPS:
        parent_norm = None

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
        if parent_norm and not existing.parent:
            existing.parent = parent_norm
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
        parent=parent_norm,
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
        # Non registrare doppioni del gruppo supermercato (sinonimi generici):
        # restano fuori dal catalogo per non frammentare/duplicare.
        if reserved_redirect(norm):
            continue
        db.add(
            ExpenseCategory(
                household_id=household_id, name=norm, source="agent", active=True
            )
        )
        known.add(norm)
        created.append(norm)
    return created
