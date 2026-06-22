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


def _mark_last_block(message: dict) -> None:
    content = message.get("content")
    if isinstance(content, str):
        if not content:
            return
        content = [{"type": "text", "text": content}]
        message["content"] = content
    if isinstance(content, list) and content and isinstance(content[-1], dict):
        content[-1]["cache_control"] = dict(_EPHEMERAL)


def mark_messages_cache(messages: list[dict]) -> None:
    """Posiziona i breakpoint di cache sulla cronologia, in place.

    Prima ripulisce eventuali breakpoint precedenti (così non si superano i 4 per
    richiesta), poi marca l'ultimo blocco del PRIMO messaggio — pinna il contesto
    iniziale, tipicamente il file base64 dell'upload — e dell'ULTIMO messaggio —
    breakpoint mobile che fa riusare dalla cache la cronologia che cresce ad ogni
    iterazione del loop. I blocchi del turno assistant sono oggetti dell'SDK (non
    dict) e vengono ignorati senza errori."""
    if not settings.enable_prompt_caching or not messages:
        return
    for m in messages:
        content = m.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block.pop("cache_control", None)
    # dict per de-duplicare quando primo e ultimo messaggio coincidono.
    for m in {id(messages[0]): messages[0], id(messages[-1]): messages[-1]}.values():
        _mark_last_block(m)
