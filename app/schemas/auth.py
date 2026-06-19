import uuid

from pydantic import BaseModel, EmailStr, Field

from app.enums import UserRole


class RegisterRequest(BaseModel):
    """Crea un nuovo nucleo familiare e il primo utente (admin)."""

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    household_name: str
    codice_fiscale: str | None = None


class JoinRequest(BaseModel):
    """Aggiunge un utente a un nucleo esistente."""

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    household_id: uuid.UUID
    codice_fiscale: str | None = None


class MemberInvite(BaseModel):
    """L'admin crea l'accesso di un familiare nel proprio nucleo."""

    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    codice_fiscale: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    household_id: uuid.UUID
    codice_fiscale: str | None = None

    model_config = {"from_attributes": True}
