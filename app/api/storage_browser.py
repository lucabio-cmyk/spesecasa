"""Navigazione dell'archivio file su disco — riservata agli amministratori.

Espone in sola lettura l'albero dei file salvati dallo storage locale, ma
SOLO entro la radice del proprio nucleo (`{storage_dir}/{household_id}`): un
admin non può vedere i file di altri household. Tutti i percorsi sono
risolti e validati contro la radice per impedire path traversal (`..`).
"""

import mimetypes
import stat
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.deps import AdminUser

router = APIRouter(prefix="/storage", tags=["storage"])


def _root(household_id: uuid.UUID) -> Path:
    """Radice dello storage del nucleo: l'ambito massimo visibile all'admin."""
    return (Path(settings.storage_dir) / str(household_id)).resolve()


def _safe_target(household_id: uuid.UUID, rel: str) -> Path:
    """Risolve `rel` sotto la radice del nucleo, rifiutando i percorsi che ne
    escono (path traversal). Restituisce un path assoluto risolto."""
    root = _root(household_id)
    target = (root / rel).resolve() if rel else root
    if target != root and root not in target.parents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Percorso non valido")
    return target


class StorageEntry(BaseModel):
    name: str
    path: str  # relativo alla radice del nucleo
    is_dir: bool
    size: int | None = None  # byte, solo per i file
    modified: float | None = None  # epoch secondi


class StorageListing(BaseModel):
    path: str  # cartella corrente (relativa alla radice; "" = radice)
    parent: str | None  # cartella superiore (None se già alla radice)
    entries: list[StorageEntry]


@router.get("/browse", response_model=StorageListing)
async def browse(user: AdminUser, path: str = ""):
    """Elenca cartelle e file dell'archivio del nucleo a partire da `path`
    (relativo alla radice del nucleo). Le cartelle precedono i file."""
    root = _root(user.household_id)
    if not root.is_dir():
        # Nessun file ancora archiviato per questo nucleo.
        return StorageListing(path="", parent=None, entries=[])
    target = _safe_target(user.household_id, path)
    if not target.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cartella non trovata")

    # Una sola stat() per voce: ricaviamo da lì sia il tipo (S_ISDIR) sia
    # dimensione/mtime, evitando syscall ridondanti su cartelle affollate.
    raw: list[tuple[Path, object]] = []
    for child in target.iterdir():
        try:
            raw.append((child, child.stat()))
        except OSError:
            continue
    # Ordine: prima le cartelle, poi i file, entrambi per nome case-insensitive.
    raw.sort(key=lambda x: (not stat.S_ISDIR(x[1].st_mode), x[0].name.lower()))

    entries: list[StorageEntry] = []
    for child, st in raw:
        is_dir = stat.S_ISDIR(st.st_mode)
        entries.append(
            StorageEntry(
                name=child.name,
                path=child.relative_to(root).as_posix(),
                is_dir=is_dir,
                size=None if is_dir else st.st_size,
                modified=st.st_mtime,
            )
        )

    rel_path = "" if target == root else target.relative_to(root).as_posix()
    parent: str | None = None
    if rel_path:
        parent = Path(rel_path).parent.as_posix()
        if parent == ".":
            parent = ""
    return StorageListing(path=rel_path, parent=parent, entries=entries)


@router.get("/file")
async def get_file(user: AdminUser, path: str, download: bool = False):
    """Restituisce un file dell'archivio del nucleo per anteprima o download."""
    target = _safe_target(user.household_id, path)
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File non trovato")
    mime, _ = mimetypes.guess_type(target.name)
    # FileResponse trasmette il file a chunk (no caricamento integrale in
    # memoria) e codifica correttamente il filename (RFC 5987).
    return FileResponse(
        path=target,
        media_type=mime or "application/octet-stream",
        filename=target.name,
        content_disposition_type="attachment" if download else "inline",
    )
