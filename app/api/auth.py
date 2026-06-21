import hmac

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.deps import DB, CurrentUser
from app.enums import UserRole
from app.models.household import Household
from app.models.user import User
from app.schemas.auth import (
    JoinRequest,
    LoginRequest,
    PasswordResetRequest,
    RegisterRequest,
    Token,
    UserOut,
)
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
    # I soggetti senza accesso non hanno password: non possono autenticarsi.
    if not user or not user.hashed_password or not verify_password(
        body.password, user.hashed_password
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenziali non valide")
    return Token(access_token=create_access_token(str(user.id)))


@router.post("/password-reset", response_model=Token)
async def password_reset(body: PasswordResetRequest, db: DB):
    """Recupero password self-service via GUI, senza email. Verifica l'identità,
    in alternativa, con il codice fiscale dell'utente o con il codice di recupero
    del deploy (`ADMIN_RECOVERY_KEY`), poi imposta la nuova password e restituisce
    un token (accesso immediato).

    Per non rivelare quali email/codici fiscali esistano, ogni fallimento
    restituisce lo stesso errore generico."""
    generic_error = HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "Dati non corrispondenti o recupero non disponibile. "
        "Contatta l'amministratore del nucleo.",
    )
    res = await db.execute(select(User).where(User.email == body.email))
    user = res.scalars().first()
    if not user:
        raise generic_error

    verified = False
    # Fattore 1: codice di recupero del deploy (attivo solo se configurato).
    if body.recovery_key and settings.admin_recovery_key:
        if hmac.compare_digest(body.recovery_key, settings.admin_recovery_key):
            verified = True
    # Fattore 2: codice fiscale dell'utente (se impostato).
    if not verified and body.codice_fiscale and user.codice_fiscale:
        if hmac.compare_digest(
            body.codice_fiscale.strip().upper(), user.codice_fiscale.strip().upper()
        ):
            verified = True

    if not verified:
        raise generic_error

    user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return Token(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
