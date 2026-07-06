"""Rate limiting in-memory (per processo).

Difesa leggera e senza dipendenze esterne contro il brute force sulle
credenziali (login, recupero password) e contro l'abuso degli endpoint che
innescano chiamate all'AI (chat, upload). Usa una finestra scorrevole per
chiave: gli eventi più vecchi della finestra vengono scartati.

Limiti: il conteggio è locale al singolo processo. In un deploy multi-worker
(più uvicorn/gunicorn) ogni worker ha il proprio contatore, quindi il tetto
effettivo è ~N volte quello configurato. È una prima barriera, non una
garanzia: per limiti robusti e condivisi serve uno store esterno (es. Redis).
"""

from __future__ import annotations

import asyncio
import time
from collections import deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    """Finestra scorrevole per chiave, protetta da un lock asyncio."""

    def __init__(self) -> None:
        # Per ogni chiave conserviamo gli eventi E la sua finestra: chiavi diverse
        # (login, chat, upload) hanno finestre molto diverse, quindi la scadenza
        # va valutata per chiave e non con un cutoff globale.
        self._events: dict[str, tuple[deque[float], float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str, limit: int, window: float) -> bool:
        """True se la richiesta rientra nel limite; registra l'evento se sì."""
        now = time.monotonic()
        async with self._lock:
            events, _ = self._events.get(key) or (deque(), window)
            # Aggiorna sempre la finestra associata alla chiave (di norma stabile,
            # ma resta corretto se la configurazione cambia a runtime).
            self._events[key] = (events, window)
            cutoff = now - window
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            # Pulizia opportunistica per non far crescere la mappa senza limiti
            # (es. molti IP/utenti diversi nel tempo). Ogni chiave è valutata con
            # la PROPRIA finestra, così una chiave "corta" non azzera quelle
            # "lunghe" ancora attive.
            if len(self._events) > 10_000:
                self._gc(now)
            return True

    def _gc(self, now: float) -> None:
        stale = [
            k
            for k, (dq, win) in self._events.items()
            if not dq or dq[-1] < now - win
        ]
        for k in stale:
            del self._events[k]


_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    """IP del client per il conteggio anonimo (login/recupero password).

    Dietro un proxy affidabile si potrebbe leggere X-Forwarded-For; qui si usa
    l'host della connessione per non fidarsi di header falsificabili.
    """
    return request.client.host if request.client else "unknown"


async def enforce(key: str, limit: int, window: float) -> None:
    """Applica il limite; solleva 429 con Retry-After se superato."""
    if not await _limiter.allow(key, limit, window):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Troppe richieste: attendi qualche istante e riprova.",
            headers={"Retry-After": str(int(window))},
        )
