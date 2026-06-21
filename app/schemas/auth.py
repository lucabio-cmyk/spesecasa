import uuid

from pydantic import BaseModel, EmailStr, Field, model_validator

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
    """Recupero password self-service via GUI, senza servizio email. L'identità è
    verificata in alternativa con:
    - il codice fiscale dell'utente (se impostato), oppure
    - il codice di recupero del deploy (`ADMIN_RECOVERY_KEY`), utile quando
      l'amministratore è chiuso fuori e non ha un codice fiscale.
    Va fornito almeno uno dei due."""

    email: EmailStr
    new_password: str = Field(min_length=8)
    codice_fiscale: str | None = None
    recovery_key: str | None = None

    @model_validator(mode="after")
    def _at_least_one_factor(self) -> "PasswordResetRequest":
        if not (self.codice_fiscale or self.recovery_key):
            raise ValueError(
                "Fornisci il codice fiscale oppure il codice di recupero"
            )
        return self


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
