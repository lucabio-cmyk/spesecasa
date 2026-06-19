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

    def delete(self, abs_path: str) -> None:
        Path(abs_path).unlink(missing_ok=True)


def get_storage():
    # TODO(claude-code): aggiungere S3Storage quando settings.storage_backend == "s3"
    return LocalStorage(settings.storage_dir)


def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
