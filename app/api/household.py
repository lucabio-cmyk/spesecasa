import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import DB, CurrentUser
from app.enums import UserRole
from app.models.household import Household
from app.models.user import User
from app.schemas.auth import MemberInvite, UserOut
from app.services.security import hash_password

router = APIRouter(prefix="/household", tags=["household"])


@router.get("", response_model=dict)
async def household_info(user: CurrentUser, db: DB):
    """Info sul nucleo familiare corrente (nome + numero membri)."""
    household = await db.get(Household, user.household_id)
    res = await db.execute(select(User).where(User.household_id == user.household_id))
    members = list(res.scalars())
    return {
        "id": str(user.household_id),
        "name": household.name if household else "",
        "members_count": len(members),
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
