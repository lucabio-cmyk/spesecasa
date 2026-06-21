"""Reset di emergenza della password di un utente, direttamente sul database.

Utile quando si è chiusi fuori (es. l'amministratore ha perso la password e non
ha un codice fiscale impostato per il recupero self-service da GUI).

Uso (in locale o in una shell del deploy, con DATABASE_URL configurato):

    # Reimposta la password di un utente per email
    python -m scripts.reset_password utente@esempio.it 'NuovaPasswordSicura'

    # Elenca gli account (per ritrovare l'email dell'admin)
    python -m scripts.reset_password --list

Su Railway: apri una shell/`railway run` sul servizio dell'app (così eredita
DATABASE_URL) ed esegui lo stesso comando.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.database import SessionLocal, engine
from app.models.user import User
from app.services.security import hash_password


async def list_users() -> None:
    async with SessionLocal() as db:
        res = await db.execute(select(User).order_by(User.role, User.email))
        users = list(res.scalars())
    if not users:
        print("Nessun utente nel database.")
        return
    print(f"{'EMAIL':<40} {'RUOLO':<8} {'CF IMPOSTATO':<12} NOME")
    print("-" * 80)
    for u in users:
        print(
            f"{u.email:<40} {u.role.value:<8} "
            f"{'sì' if u.codice_fiscale else 'no':<12} {u.full_name}"
        )


async def reset_password(email: str, new_password: str) -> int:
    if len(new_password) < 8:
        print("La password deve avere almeno 8 caratteri.", file=sys.stderr)
        return 2
    async with SessionLocal() as db:
        res = await db.execute(select(User).where(User.email == email))
        user = res.scalars().first()
        if not user:
            print(f"Nessun utente con email '{email}'.", file=sys.stderr)
            print("Usa --list per vedere gli account disponibili.", file=sys.stderr)
            return 1
        user.hashed_password = hash_password(new_password)
        await db.commit()
    print(f"Password aggiornata per {email} (ruolo: {user.role.value}).")
    print("Ora puoi accedere dalla schermata di login con la nuova password.")
    return 0


async def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset di emergenza della password di un utente."
    )
    parser.add_argument("email", nargs="?", help="Email dell'utente")
    parser.add_argument("new_password", nargs="?", help="Nuova password (min 8 caratteri)")
    parser.add_argument(
        "--list", action="store_true", help="Elenca gli account e termina"
    )
    args = parser.parse_args()

    try:
        if args.list:
            await list_users()
            return 0
        if not args.email or not args.new_password:
            parser.error("specifica EMAIL e NUOVA_PASSWORD, oppure usa --list")
        return await reset_password(args.email, args.new_password)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
