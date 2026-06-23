import os
from functools import lru_cache
from urllib.parse import (
    parse_qsl,
    quote_plus,
    urlencode,
    urlsplit,
    urlunsplit,
)

from pydantic_settings import BaseSettings, SettingsConfigDict

# Default usato solo in locale: in deploy DEVE essere sovrascritto da DATABASE_URL
# (o dalle variabili PG* del servizio Postgres).
DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/spese"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}


def _database_url_from_pg_env() -> str | None:
    """Costruisce l'URL dalle variabili componente standard di Postgres.

    Railway (e l'immagine ufficiale Postgres) espongono PGHOST/PGPORT/PGUSER/
    PGPASSWORD/PGDATABASE: se DATABASE_URL non è impostato ma queste ci sono,
    usiamole invece di ripiegare ciecamente su localhost.
    """
    host = os.getenv("PGHOST")
    if not host:
        return None
    user = os.getenv("PGUSER", "postgres")
    password = os.getenv("PGPASSWORD", "")
    port = os.getenv("PGPORT", "5432")
    name = os.getenv("PGDATABASE", "postgres")
    cred = quote_plus(user)
    if password:
        cred = f"{cred}:{quote_plus(password)}"
    return f"postgresql+asyncpg://{cred}@{host}:{port}/{name}"


def _normalize_async_url(url: str) -> str:
    """Forza il driver asyncpg e ripulisce i parametri non supportati.

    - Railway fornisce schemi `postgresql://` / `postgres://`: li mappiamo su
      `postgresql+asyncpg://`.
    - asyncpg non accetta il parametro libpq `sslmode` come kwarg di connessione
      (lo riceve via SQLAlchemy e solleva TypeError): lo traduciamo nel parametro
      `ssl`, che asyncpg interpreta con gli stessi valori (require, verify-full…).
    """
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
            break

    parts = urlsplit(url)
    if parts.query:
        params = parse_qsl(parts.query, keep_blank_values=True)
        rebuilt: list[tuple[str, str]] = []
        for key, value in params:
            if key.lower() == "sslmode":
                # Evita parametri duplicati se sono presenti sia sslmode sia ssl.
                if not any(k.lower() == "ssl" for k, _ in params):
                    rebuilt.append(("ssl", value))
                continue
            rebuilt.append((key, value))
        url = urlunsplit(parts._replace(query=urlencode(rebuilt)))
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = DEFAULT_DATABASE_URL

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    # Budget generoso: scontrini multipagina e verifiche fiscali richiedono spazio.
    agent_max_tokens: int = 8192
    agent_max_tool_iterations: int = 24
    # Ricerca web dell'agente per affinare/verificare le regole fiscali aggiornate.
    enable_web_search: bool = True
    web_search_max_uses: int = 6
    web_search_country: str = "IT"
    # Resilienza alle chiamate Anthropic. L'SDK ritenta già gli errori
    # transitori (429/5xx/529 overloaded), ma in caso di sovraccarico prolungato
    # i pochi tentativi di default non bastano: `anthropic_max_retries` è passato
    # al client SDK, mentre `anthropic_retry_*` governa il nostro retry esterno
    # con backoff esponenziale (vedi app/services/llm.py).
    anthropic_max_retries: int = 4
    anthropic_retry_attempts: int = 5
    anthropic_retry_base_delay: float = 2.0
    anthropic_retry_max_delay: float = 30.0

    # Auth
    jwt_secret: str = "cambia-questa-stringa"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    # Codice di recupero per reimpostare via GUI la password di un account (utile
    # se l'admin è chiuso fuori e non ha un codice fiscale). Vuoto = funzione
    # disattivata. Impostalo come variabile d'ambiente del deploy.
    admin_recovery_key: str = ""

    # Agente di orchestrazione (revisione in background dell'archivio).
    # Verifica la coerenza dei dati (righe ↔ totali, classificazioni, duplicati),
    # segnala ciò che non è stato calcolato/gestito correttamente e propone
    # miglioramenti (categorie, riclassificazioni) da applicare previo consenso.
    enable_orchestrator: bool = True
    # Esegue automaticamente una revisione mirata al termine di ogni upload.
    orchestrator_run_after_upload: bool = True
    # Abilita la fase LLM (proposte intelligenti di categorie/riclassificazioni);
    # se disattiva o senza API key, restano le sole verifiche deterministiche.
    orchestrator_use_llm: bool = True
    orchestrator_max_tool_iterations: int = 12
    # Scheduler periodico (loop asyncio interno): off di default per non
    # introdurre costi/run a sorpresa. In ore; 0 = disattivato.
    orchestrator_schedule_hours: int = 0

    # Storage
    storage_backend: str = "local"
    storage_dir: str = "/data/documents"

    # Semantic search (optional)
    enable_semantic_search: bool = False
    embedding_provider: str = "voyage"
    embedding_model: str = "voyage-3"
    embedding_dim: int = 1024
    voyage_api_key: str = ""

    # App
    app_env: str = "development"
    cors_origins: str = "*"

    def _resolve_database_url(self) -> str:
        """URL effettivo (normalizzato asyncpg), con fallback alle PG*.

        Precedenza: DATABASE_URL esplicito → variabili PG* → default locale.
        """
        url = self.database_url
        if url == DEFAULT_DATABASE_URL:
            assembled = _database_url_from_pg_env()
            if assembled:
                url = assembled
        return _normalize_async_url(url)

    @property
    def async_database_url(self) -> str:
        url = self._resolve_database_url()
        host = urlsplit(url).hostname or ""
        if host in _LOCAL_HOSTS and self.app_env != "development":
            raise RuntimeError(
                "Database non configurato: l'applicazione sta puntando al "
                f"Postgres locale di default (host '{host or 'localhost'}') in "
                f"ambiente '{self.app_env}'. Imposta DATABASE_URL — su Railway "
                "collega il servizio Postgres, es. "
                "DATABASE_URL=${{Postgres.DATABASE_URL}} — oppure fornisci le "
                "variabili PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE."
            )
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
