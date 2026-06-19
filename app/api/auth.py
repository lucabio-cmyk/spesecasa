from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DB, CurrentUser
from app.enums import UserRole
from app.models.household import Household
from app.models.user import User
from app.schemas.auth import JoinRequest, LoginRequest, RegisterRequest, Token, UserOut
from app.services.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=201)
async def register(body: RegisterRequest, db: DB):
    """Crea un nuovo nucleo familiare e il primo utente (admin)."""
    exists = await db.execute(select(User).where(User.email == body.email))
    if exists.scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email gia registrata")

    household = Household(name=body.household_name)
    db.add(household)
    await db.flush()

    user = User(
        household_id=household.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        codice_fiscale=body.codice_fiscale,
        role=UserRole.ADMIN,
    )
    db.add(user)
    await db.commit()
    return Token(access_token=create_access_token(str(user.id)))


@router.post("/join", response_model=Token, status_code=201)
async def join(body: JoinRequest, db: DB):
    """Aggiunge un utente a un nucleo esistente.
    TODO(claude-code): sostituire household_id libero con un sistema di inviti."""
    household = await db.get(Household, body.household_id)
    if not household:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nucleo non trovato")
    exists = await db.execute(select(User).where(User.email == body.email))
    if exists.scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email gia registrata")

    user = User(
        household_id=household.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        codice_fiscale=body.codice_fiscale,
        role=UserRole.MEMBER,
    )
    db.add(user)
    await db.commit()
    return Token(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=Token)
async def login(body: LoginRequest, db: DB):
    res = await db.execute(select(User).where(User.email == body.email))
    user = res.scalars().first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenziali non valide")
    return Token(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
