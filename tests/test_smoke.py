"""Smoke test minimo. Richiede le dipendenze installate.
TODO(claude-code): aggiungere test su auth, upload, dispatcher tool (con DB di test)."""


def test_import_app():
    from app.main import app

    assert app is not None


def test_member_update_route_registered():
    """L'endpoint di modifica membro post-creazione deve essere esposto (PATCH)."""
    from app.api import household

    patch_member = any(
        getattr(r, "path", "") == "/household/members/{member_id}"
        and "PATCH" in getattr(r, "methods", set())
        for r in household.router.routes
    )
    assert patch_member, "PATCH /household/members/{member_id} non registrato"


def test_member_update_schema_allows_partial():
    """MemberUpdate consente l'aggiunta del solo codice fiscale dopo la creazione."""
    from app.schemas.auth import MemberUpdate

    body = MemberUpdate(codice_fiscale="RSSMRA80A01H501U")
    data = body.model_dump(exclude_unset=True)
    assert data == {"codice_fiscale": "RSSMRA80A01H501U"}


def test_async_db_url_coercion():
    from app.config import Settings

    s = Settings(database_url="postgresql://u:p@host:5432/db")
    assert s.async_database_url.startswith("postgresql+asyncpg://")


def test_async_db_url_sslmode_translated():
    """asyncpg non accetta `sslmode` come kwarg: va tradotto in `ssl`."""
    from app.config import Settings

    s = Settings(database_url="postgresql://u:p@host:5432/db?sslmode=require")
    url = s.async_database_url
    assert "sslmode" not in url
    assert "ssl=require" in url


def test_default_local_db_raises_in_production():
    """In deploy senza DATABASE_URL deve fallire con un errore chiaro."""
    import pytest

    from app.config import Settings

    s = Settings(app_env="production")
    with pytest.raises(RuntimeError, match="Database non configurato"):
        _ = s.async_database_url


def test_default_local_db_ok_in_development():
    from app.config import Settings

    s = Settings(app_env="development")
    assert s.async_database_url.startswith("postgresql+asyncpg://")


def test_database_url_from_pg_env(monkeypatch):
    """Senza DATABASE_URL, le variabili PG* del servizio Postgres bastano."""
    from app.config import Settings

    monkeypatch.setenv("PGHOST", "db.internal")
    monkeypatch.setenv("PGPORT", "5433")
    monkeypatch.setenv("PGUSER", "spese")
    monkeypatch.setenv("PGPASSWORD", "p@ss/word")
    monkeypatch.setenv("PGDATABASE", "spese")

    s = Settings(app_env="production")
    url = s.async_database_url
    assert url.startswith("postgresql+asyncpg://spese:")
    assert "@db.internal:5433/spese" in url
    # La password con caratteri speciali deve essere url-encoded.
    assert "p%40ss%2Fword" in url
