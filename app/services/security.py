from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

# bcrypt opera su un massimo di 72 byte: troncare esplicitamente evita il
# ValueError sollevato da bcrypt>=4 ed è coerente fra hash e verifica.
_BCRYPT_MAX_BYTES = 72


def _to_secret(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_secret(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_secret(password), hashed.encode("utf-8"))
    except ValueError:
        # Hash malformato/non bcrypt: trattalo come non valido invece di crashare.
        return False


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": subject, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
