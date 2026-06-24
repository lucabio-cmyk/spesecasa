import hashlib
from pathlib import Path

from app.config import settings


class LocalStorage:
    """Backend di archiviazione su filesystem (volume montato su STORAGE_DIR).
    Su Railway: collega un Volume persistente al path STORAGE_DIR."""

    def __init__(self, base_dir: str):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def save(self, rel_path: str, data: bytes) -> str:
        dest = self.base / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return str(dest)

    def read(self, abs_path: str) -> bytes:
        return Path(abs_path).read_bytes()

    def move(self, abs_path: str, rel_path: str) -> str:
        """Sposta/rinomina un file già archiviato in una nuova posizione
        relativa (riorganizzazione dell'archivio dopo l'estrazione). Crea le
        directory necessarie, evita di sovrascrivere un file diverso e rimuove
        le directory rimaste vuote. Restituisce il nuovo percorso assoluto."""
        src = Path(abs_path)
        dest = self.base / rel_path
        if src.resolve() == dest.resolve():
            return str(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Se per qualche motivo la destinazione è occupata da un altro file,
        # disambigua aggiungendo un suffisso progressivo per non perdere dati.
        if dest.exists():
            stem, suffix = dest.stem, dest.suffix
            n = 2
            while dest.exists():
                dest = dest.parent / f"{stem}-{n}{suffix}"
                n += 1
        src.replace(dest)
        # Pulizia best-effort delle directory rimaste vuote dopo lo spostamento.
        parent = src.parent
        while (
            parent != self.base
            and parent.is_relative_to(self.base)
            and parent.is_dir()
        ):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        return str(dest)

    def delete(self, abs_path: str) -> None:
        Path(abs_path).unlink(missing_ok=True)


def get_storage():
    # TODO(claude-code): aggiungere S3Storage quando settings.storage_backend == "s3"
    return LocalStorage(settings.storage_dir)


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
