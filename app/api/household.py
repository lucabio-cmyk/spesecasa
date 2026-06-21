import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, CurrentUser
from app.enums import UserRole
from app.models.category import ExpenseCategory
from app.models.household import Household
from app.models.property_unit import PropertyUnit
from app.models.user import User
from app.schemas.auth import MemberInvite, MemberUpdate, UserOut
from app.schemas.category import CategoryCreate, CategoryOut, CategoryUpdate, KnownCategory
from app.schemas.property_unit import (
    HouseholdSettingsUpdate,
    PropertyUnitCreate,
    PropertyUnitOut,
    PropertyUnitUpdate,
)
from app.services import categories as categories_service
from app.services.security import hash_password

router = APIRouter(prefix="/household", tags=["household"])


@router.get("", response_model=dict)
async def household_info(user: CurrentUser, db: DB):
    """Info sul nucleo familiare corrente (nome, membri, addestramento agente)."""
    household = await db.get(Household, user.household_id)
    res = await db.execute(select(User).where(User.household_id == user.household_id))
    members = list(res.scalars())
    return {
        "id": str(user.household_id),
        "name": household.name if household else "",
        "members_count": len(members),
        "agent_instructions": household.agent_instructions if household else None,
    }


@router.patch("", response_model=dict)
async def update_household(body: HouseholdSettingsUpdate, user: CurrentUser, db: DB):
    """Aggiorna nome e istruzioni di addestramento dell'agente (solo admin)."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Solo l'amministratore del nucleo può modificare le impostazioni",
        )
    household = await db.get(Household, user.household_id)
    if not household:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nucleo non trovato")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        household.name = data["name"]
    if "agent_instructions" in data:
        household.agent_instructions = data["agent_instructions"] or None
    await db.commit()
    await db.refresh(household)
    return {
        "id": str(household.id),
        "name": household.name,
        "agent_instructions": household.agent_instructions,
    }


@router.get("/members", response_model=list[UserOut])
async def list_members(user: CurrentUser, db: DB):
    """Elenco dei membri del nucleo. Usato dalla GUI per mostrare i nomi di
    soggetto pagante e beneficiario e per i filtri."""
    res = await db.execute(
        select(User).where(User.household_id == user.household_id).order_by(User.full_name)
    )
    return list(res.scalars())


@router.post("/members", response_model=UserOut, status_code=201)
async def add_member(body: MemberInvite, user: CurrentUser, db: DB):
    """Aggiunge un membro al nucleo (solo admin).

    Se sono indicati email e password viene creato un accesso (login) e l'admin
    comunica la password al familiare; altrimenti il familiare è un semplice
    **soggetto senza accesso**, usato solo per attribuire spese e documenti."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo l'amministratore del nucleo può aggiungere membri")
    if body.email:
        exists = await db.execute(select(User).where(User.email == body.email))
        if exists.scalars().first():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email già registrata")
    member = User(
        household_id=user.household_id,
        email=body.email,
        hashed_password=hash_password(body.password) if body.password else None,
        full_name=body.full_name,
        codice_fiscale=body.codice_fiscale,
        role=UserRole.MEMBER,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.patch("/members/{member_id}", response_model=UserOut)
async def update_member(
    member_id: uuid.UUID, body: MemberUpdate, user: CurrentUser, db: DB
):
    """Modifica un membro dopo la creazione (es. aggiunta del codice fiscale).

    L'amministratore può modificare qualsiasi membro del nucleo; un membro può
    modificare solo i propri dati e non può cambiare il proprio ruolo."""
    is_admin = user.role == UserRole.ADMIN
    if not is_admin and member_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Puoi modificare solo i tuoi dati",
        )
    member = await db.get(User, member_id)
    if not member or member.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membro non trovato")

    data = body.model_dump(exclude_unset=True)

    if "role" in data and data["role"] is not None:
        if not is_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Solo l'amministratore può cambiare i ruoli"
            )
        # Non lasciare il nucleo senza amministratori.
        if member.role == UserRole.ADMIN and data["role"] != UserRole.ADMIN:
            res = await db.execute(
                select(User).where(
                    User.household_id == user.household_id, User.role == UserRole.ADMIN
                )
            )
            admins = list(res.scalars())
            if len(admins) <= 1:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Il nucleo deve avere almeno un amministratore",
                )
        member.role = data["role"]

    if "email" in data and data["email"] is not None:
        if data["email"] != member.email:
            exists = await db.execute(select(User).where(User.email == data["email"]))
            if exists.scalars().first():
                raise HTTPException(status.HTTP_409_CONFLICT, "Email già registrata")
            member.email = data["email"]

    if "full_name" in data and data["full_name"]:
        member.full_name = data["full_name"]

    if "codice_fiscale" in data:
        cf = data["codice_fiscale"]
        member.codice_fiscale = (cf.strip().upper() or None) if cf else None

    if "password" in data and data["password"]:
        member.hashed_password = hash_password(data["password"])

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email già registrata")
    await db.refresh(member)
    return member


@router.delete("/members/{member_id}", status_code=204)
async def remove_member(member_id: uuid.UUID, user: CurrentUser, db: DB):
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo l'amministratore può rimuovere membri")
    if member_id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Non puoi rimuovere te stesso")
    member = await db.get(User, member_id)
    if not member or member.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membro non trovato")
    try:
        await db.delete(member)
        await db.commit()
    except IntegrityError:
        # Il membro ha documenti o spese collegati (vincoli FK).
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Impossibile rimuovere il membro: ha documenti o spese collegati nel nucleo.",
        )


# --- Unità immobiliari (immobili del nucleo) -------------------------------
@router.get("/units", response_model=list[PropertyUnitOut])
async def list_units(user: CurrentUser, db: DB):
    """Elenco delle unità immobiliari del nucleo. Usate per la gestione del
    condominio e per addestrare l'agente all'attribuzione corretta."""
    res = await db.execute(
        select(PropertyUnit)
        .where(PropertyUnit.household_id == user.household_id)
        .order_by(PropertyUnit.is_primary.desc(), PropertyUnit.name)
    )
    return list(res.scalars())


@router.post("/units", response_model=PropertyUnitOut, status_code=201)
async def create_unit(body: PropertyUnitCreate, user: CurrentUser, db: DB):
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Solo l'amministratore può gestire le unità"
        )
    unit = PropertyUnit(household_id=user.household_id, **body.model_dump(exclude_none=True))
    # Azzera le altre principali PRIMA di aggiungere la nuova unità: così la
    # query in _unset_other_primary (con il suo autoflush) non include questa
    # unità e non ne resetta subito il flag is_primary appena impostato.
    if unit.is_primary:
        await _unset_other_primary(db, user.household_id, keep=None)
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return unit


@router.patch("/units/{unit_id}", response_model=PropertyUnitOut)
async def update_unit(
    unit_id: uuid.UUID, body: PropertyUnitUpdate, user: CurrentUser, db: DB
):
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Solo l'amministratore può gestire le unità"
        )
    unit = await db.get(PropertyUnit, unit_id)
    if not unit or unit.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unità non trovata")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(unit, key, value)
    if unit.is_primary:
        await _unset_other_primary(db, user.household_id, keep=unit.id)
    await db.commit()
    await db.refresh(unit)
    return unit


@router.delete("/units/{unit_id}", status_code=204)
async def delete_unit(unit_id: uuid.UUID, user: CurrentUser, db: DB):
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Solo l'amministratore può gestire le unità"
        )
    unit = await db.get(PropertyUnit, unit_id)
    if not unit or unit.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unità non trovata")
    # Le bollette collegate restano (FK ondelete=SET NULL).
    await db.delete(unit)
    await db.commit()


async def _unset_other_primary(db: DB, household_id, keep) -> None:
    """Una sola unità principale per nucleo: azzera il flag sulle altre."""
    res = await db.execute(
        select(PropertyUnit).where(
            PropertyUnit.household_id == household_id, PropertyUnit.is_primary.is_(True)
        )
    )
    for other in res.scalars():
        if keep is None or other.id != keep:
            other.is_primary = False


# --- Categorie merceologiche (di base + personalizzate del nucleo) ---------
@router.get("/categories", response_model=list[KnownCategory])
async def list_categories(user: CurrentUser, db: DB):
    """Tutte le categorie note al nucleo: quelle di base più quelle
    personalizzate (create dall'assistente o dall'utente). La GUI le usa per i
    menù di classificazione e per la gestione."""
    return await categories_service.known_categories(db, user.household_id)


@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(body: CategoryCreate, user: CurrentUser, db: DB):
    """Crea una categoria personalizzata per il nucleo. Idempotente: se il nome
    coincide con una categoria esistente (di base o personalizzata) non la
    duplica."""
    result = await categories_service.create_category(
        db,
        user.household_id,
        name=body.name,
        description=body.description,
        examples=body.examples,
        source="user",
    )
    if result.get("error"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result["error"])
    if result.get("builtin"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            result.get("message", "Categoria già esistente tra quelle di base"),
        )
    cat_id = result["category"].get("id")
    category = await db.get(ExpenseCategory, cat_id) if cat_id else None
    if not category:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Impossibile creare la categoria")
    return category


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID, body: CategoryUpdate, user: CurrentUser, db: DB
):
    """Modifica una categoria personalizzata (nome, descrizione, esempi, stato).
    Le categorie di base non sono modificabili."""
    category = await db.get(ExpenseCategory, category_id)
    if not category or category.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoria non trovata")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        norm, error = categories_service.validate_name(data["name"])
        if error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
        if categories_service.is_builtin(norm):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Esiste già una categoria di base con questo nome"
            )
        category.name = norm
    if "description" in data:
        category.description = (data["description"] or None)
    if "examples" in data:
        category.examples = categories_service._clean_examples(data["examples"])
    if "active" in data and data["active"] is not None:
        category.active = data["active"]
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Categoria già esistente")
    await db.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: uuid.UUID, user: CurrentUser, db: DB):
    """Elimina una categoria personalizzata. Le spese già classificate con quel
    nome restano invariate nello storico (la categoria è una stringa libera)."""
    category = await db.get(ExpenseCategory, category_id)
    if not category or category.household_id != user.household_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Categoria non trovata")
    await db.delete(category)
    await db.commit()
