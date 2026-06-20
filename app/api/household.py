import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, CurrentUser
from app.enums import UserRole
from app.models.household import Household
from app.models.property_unit import PropertyUnit
from app.models.user import User
from app.schemas.auth import MemberInvite, UserOut
from app.schemas.property_unit import (
    HouseholdSettingsUpdate,
    PropertyUnitCreate,
    PropertyUnitOut,
    PropertyUnitUpdate,
)
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
    """Aggiunge un membro al nucleo (solo admin). Utile finché non c'è il flusso
    a inviti: l'admin crea l'accesso e comunica la password al familiare."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo l'amministratore del nucleo può aggiungere membri")
    exists = await db.execute(select(User).where(User.email == body.email))
    if exists.scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email già registrata")
    member = User(
        household_id=user.household_id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        codice_fiscale=body.codice_fiscale,
        role=UserRole.MEMBER,
    )
    db.add(member)
    await db.commit()
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
    db.add(unit)
    if unit.is_primary:
        await _unset_other_primary(db, user.household_id, keep=None)
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
