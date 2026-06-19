"""Smoke test minimo. Richiede le dipendenze installate.
TODO(claude-code): aggiungere test su auth, upload, dispatcher tool (con DB di test)."""


def test_import_app():
    from app.main import app

    assert app is not None


def test_async_db_url_coercion():
    from app.config import Settings

    s = Settings(database_url="postgresql://u:p@host:5432/db")
    assert s.async_database_url.startswith("postgresql+asyncpg://")
