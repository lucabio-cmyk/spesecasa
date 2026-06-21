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


class MemberUpdate(BaseModel):
    """Modifica i dati di un membro dopo la creazione (es. aggiunta del
    codice fiscale). Tutti i campi sono opzionali: si aggiorna solo ciò che
    viene inviato."""

    email: EmailStr | None = None
    full_name: str | None = None
    codice_fiscale: str | None = None
    role: UserRole | None = None
    password: str | None = Field(default=None, min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    """Recupero password self-service. In assenza di un servizio email, l'identità
    è verificata con un dato personale già noto al nucleo: il codice fiscale.
    Funziona solo se l'utente ha un codice fiscale impostato; altrimenti deve
    rivolgersi all'amministratore del nucleo."""

    email: EmailStr
    codice_fiscale: str
    new_password: str = Field(min_length=8)


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
