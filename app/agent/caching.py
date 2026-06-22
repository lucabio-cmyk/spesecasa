"""Prompt caching Anthropic — risparmio di token (e costi) sulle chiamate al modello.

Il loop tool-use dell'agente (e ogni turno di chat) rispedisce a OGNI iterazione
l'intero prefisso `tools` → `system` → `messages`: gli schemi degli strumenti, il
system prompt fiscale (grande) e tutta la cronologia, compreso l'eventuale file
base64 dell'upload (PDF/immagine, pesante). Con il prompt caching quel prefisso
viene servito dalla cache (~10% del costo dei token in input) invece di essere
rielaborato da capo a ogni richiesta.

Il caching è un match di PREFISSO: basta un breakpoint (`cache_control`) sull'ultimo
blocco del system per cachare insieme tools + system, più un paio di breakpoint sui
messaggi per riusare la cronologia. Si tengono al massimo pochi breakpoint per
restare entro il limite di 4 per richiesta. Disattivabile con
`ENABLE_PROMPT_CACHING=false`.
"""
from app.config import settings

_EPHEMERAL = {"type": "ephemeral"}


def cached_system(text: str):
    """System prompt come blocco con breakpoint di cache (o stringa semplice se la
    cache è disattivata). Marcare il system cacha tools + system insieme, perché
    nell'ordine di render i tools precedono il system."""
    if not settings.enable_prompt_caching or not text:
        return text
    return [{"type": "text", "text": text, "cache_control": dict(_EPHEMERAL)}]


def _mark_last_block(message: dict) -> dict:
    """Restituisce una COPIA del messaggio con `cache_control` sull'ultimo blocco
    (convertendo l'eventuale contenuto stringa in un blocco testo). Copia-su-scrittura:
    non muta né il dict, né la lista `content`, né i blocchi originali — importante
    perché in chat la cronologia è condivisa per riferimento con il chiamante."""
    content = message.get("content")
    if isinstance(content, str):
        if not content:
            return message
        content = [{"type": "text", "text": content}]
    elif isinstance(content, list):
        content = list(content)
    else:
        return message
    if content and isinstance(content[-1], dict):
        content[-1] = {**content[-1], "cache_control": dict(_EPHEMERAL)}
    return {**message, "content": content}


def mark_messages_cache(messages: list[dict]) -> None:
    """Posiziona i breakpoint di cache sulla cronologia, aggiornando in place la
    lista `messages` (i singoli messaggi vengono sostituiti con copie, mai mutati).

    Prima ripulisce eventuali breakpoint precedenti (così non si superano i 4 per
    richiesta), poi marca l'ultimo blocco del PRIMO messaggio — pinna il contesto
    iniziale, tipicamente il file base64 dell'upload — e dell'ULTIMO messaggio —
    breakpoint mobile che fa riusare dalla cache la cronologia che cresce ad ogni
    iterazione del loop. I blocchi del turno assistant sono oggetti dell'SDK (non
    dict) e vengono ignorati senza errori. Copia-su-scrittura: non muta gli oggetti
    originali, che in chat sono condivisi con la cronologia del chiamante."""
    if not settings.enable_prompt_caching or not messages:
        return
    for i, m in enumerate(messages):
        content = m.get("content")
        if not isinstance(content, list):
            continue
        if any(isinstance(b, dict) and "cache_control" in b for b in content):
            messages[i] = {
                **m,
                "content": [
                    {k: v for k, v in b.items() if k != "cache_control"}
                    if isinstance(b, dict)
                    else b
                    for b in content
                ],
            }
    messages[0] = _mark_last_block(messages[0])
    if len(messages) > 1:
        messages[-1] = _mark_last_block(messages[-1])

