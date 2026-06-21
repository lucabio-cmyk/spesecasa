from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

# bcrypt ignora i byte oltre i 72: tronchiamo esplicitamente (come faceva passlib)
# per evitare ValueError su password lunghe e mantenere comportamento e hash
# compatibili con quelli già salvati ($2b$...).
_MAX_BCRYPT_BYTES = 72


def _to_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_MAX_BCRYPT_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bytes(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
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
