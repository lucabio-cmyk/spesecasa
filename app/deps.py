import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.enums import UserRole
from app.models.user import User

_bearer = HTTPBearer()


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    try:
        payload = jwt.decode(
            creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("sub mancante")
        user_uuid = uuid.UUID(str(user_id))
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token non valido")

    user = await db.get(User, user_uuid)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Utente non trovato")
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Consente l'accesso solo agli amministratori del nucleo. Usato per le
    sezioni che mostrano dati sensibili (es. il dettaglio dei farmaci)."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Operazione riservata all'amministratore del nucleo",
        )
    return user


# Alias riutilizzabili nelle route
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DB = Annotated[AsyncSession, Depends(get_db)]
