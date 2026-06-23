"""Resilienza alle chiamate verso l'API Anthropic.

L'SDK ritenta già internamente gli errori transitori (429 rate limit, 5xx,
529 ``overloaded_error``), ma con i pochi tentativi di default un sovraccarico
prolungato dell'API fa comunque fallire l'elaborazione di un documento
(``Error code: 529 - Overloaded``). Questo strato aggiunge un ulteriore livello
di retry con backoff esponenziale e jitter attorno a ``messages.create``, usato
sia dalla pipeline documentale sia dall'agente di orchestrazione.
"""

import asyncio
import logging
import random

from app.config import settings

logger = logging.getLogger(__name__)

# Codici HTTP transitori per cui ha senso ritentare: sovraccarico (529 =
# overloaded_error di Anthropic), rate limit (429) ed errori server temporanei.
_RETRY_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504, 529}

# Eccezioni dell'SDK senza status_code (problemi di rete/timeout) che vanno
# comunque ritentate. Riconosciute per nome così questo modulo non deve
# importare ``anthropic`` (import pesante e non sempre presente nei test).
_RETRY_EXC_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "APIConnectionTimeoutError",
    "InternalServerError",
    "OverloadedError",
}


def is_overloaded(exc: Exception) -> bool:
    """True se l'errore è un sovraccarico dell'API (529 / overloaded_error)."""
    if getattr(exc, "status_code", None) == 529:
        return True
    # Si scorre l'MRO così il controllo regge anche con sottoclassi/wrapper.
    return any(cls.__name__ == "OverloadedError" for cls in type(exc).__mro__)


def is_retryable(exc: Exception) -> bool:
    """True per gli errori transitori dell'API che conviene ritentare."""
    if getattr(exc, "status_code", None) in _RETRY_STATUS_CODES:
        return True
    return any(cls.__name__ in _RETRY_EXC_NAMES for cls in type(exc).__mro__)


async def create_message(client, **kwargs):
    """``client.messages.create(**kwargs)`` con backoff esponenziale sui transitori.

    Ritenta fino a ``settings.anthropic_retry_attempts`` volte; gli errori non
    transitori (es. 400/401) vengono rilanciati subito.
    """
    attempts = max(1, settings.anthropic_retry_attempts)
    for attempt in range(attempts):
        try:
            return await client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 — si filtra con is_retryable
            if attempt >= attempts - 1 or not is_retryable(exc):
                raise
            delay = min(
                settings.anthropic_retry_base_delay * (2 ** attempt),
                settings.anthropic_retry_max_delay,
            )
            delay += random.uniform(0, delay * 0.25)  # jitter anti-thundering herd
            logger.warning(
                "Anthropic API transitorio (%s): nuovo tentativo %d/%d tra %.1fs",
                exc,
                attempt + 2,
                attempts,
                delay,
            )
            await asyncio.sleep(delay)
