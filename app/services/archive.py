"""Riorganizzazione dell'archivio: dopo l'estrazione, il file caricato (salvato
con un nome opaco basato sull'hash) viene RINOMINATO con un nome parlante e
SPOSTATO in una struttura di directory ordinata, così l'archivio resta navigabile
anche dal filesystem (utile per backup, ispezione, consegna al commercialista).

Struttura: ``{household_id}/{anno}/{tipo_documento}/{nome_parlante}``
Nome parlante: ``{data}_{emittente}_{importo}_{hash8}{estensione}``

La rinomina avviene a valle della pipeline (in `process_document`), quando i
metadati estratti (tipo, data, emittente, importo, anno fiscale) sono disponibili.
È idempotente: rieseguita su un documento già ordinato non cambia nulla; dopo una
rielaborazione che cambia i metadati, il file viene spostato nella nuova posizione.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.document import Document

# Lunghezza massima di ciascun segmento "parlante" del nome file, per non
# generare percorsi troppo lunghi su filesystem con limiti stringenti.
_MAX_SEGMENT = 48


def slugify(text: str | None, *, max_len: int = _MAX_SEGMENT) -> str:
    """Riduce un testo libero a un segmento sicuro per nomi file/cartelle:
    minuscolo, senza accenti, solo ``[a-z0-9-]``, parole unite da trattino."""
    if not text:
        return ""
    # Rimuove gli accenti (es. "società" → "societa") mantenendo le lettere base.
    normalized = unicodedata.normalize("NFKD", str(text))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug


def _extension(document: Document) -> str:
    """Estensione del file da conservare: dal nome originale, con fallback al MIME."""
    suffix = Path(document.original_filename or "").suffix.lower()
    if suffix and len(suffix) <= 10:
        return suffix
    return {
        "application/pdf": ".pdf",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/heic": ".heic",
        "image/webp": ".webp",
        "image/tiff": ".tiff",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xls",
    }.get((document.mime_type or "").lower(), "")


def _amount_segment(document: Document) -> str:
    """Importo come segmento di nome file: ``84-50eur`` (la virgola diventa
    trattino, niente separatori delle migliaia)."""
    if document.total_amount is None:
        return ""
    amount = f"{document.total_amount:.2f}".replace(".", "-")
    currency = (document.currency or "eur").lower()
    currency = re.sub(r"[^a-z]", "", currency)[:3] or "eur"
    return f"{amount}{currency}"


def _year_folder(document: Document) -> str:
    """Cartella dell'anno: anno fiscale, con fallback alla data del documento."""
    if document.fiscal_year:
        return str(document.fiscal_year)
    if document.doc_date:
        return str(document.doc_date.year)
    return "senza-anno"


def archive_relpath(document: Document) -> str:
    """Percorso relativo ordinato e nome parlante per un documento elaborato.

    Es. ``<household>/2025/bolletta/2025-03-15_enel-energia_84-50eur_a1b2c3d4.pdf``"""
    year = _year_folder(document)
    doc_type = slugify(getattr(document.doc_type, "value", document.doc_type)) or "altro"

    date_part = document.doc_date.isoformat() if document.doc_date else "data-ignota"
    issuer_part = slugify(document.issuer)
    amount_part = _amount_segment(document)
    hash_part = (document.file_hash or "")[:8] or "nohash"

    # Compone il nome scartando i segmenti vuoti per non lasciare doppi trattini.
    name_bits = [b for b in (date_part, issuer_part, amount_part, hash_part) if b]
    filename = "_".join(name_bits) + _extension(document)

    return f"{document.household_id}/{year}/{doc_type}/{filename}"


def organize_document(document: Document, storage) -> bool:
    """Rinomina e sposta il file del documento nella struttura ordinata.

    Aggiorna ``document.storage_path`` in place. Restituisce ``True`` se il file
    è stato spostato (così il chiamante può fare commit), ``False`` se era già al
    posto giusto o se non c'è un percorso da spostare. Best-effort: in caso di
    errore di I/O non solleva (l'archivio resta consultabile dal vecchio path)."""
    if not document.storage_path:
        return False
    new_rel = archive_relpath(document)
    try:
        new_abs = storage.move(document.storage_path, new_rel)
    except Exception:
        return False
    if new_abs == document.storage_path:
        return False
    document.storage_path = new_abs
    return True
