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
# Segreto JWT di default: sicuro solo in sviluppo. In produzione DEVE essere
# sovrascritto da JWT_SECRET, altrimenti chiunque può forgiare token validi.
DEFAULT_JWT_SECRET = "cambia-questa-stringa"


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
    # Modello per SUPERFICIE (ottimizzazione costi): l'estrazione documenti (vision
    # + classificazione fiscale multi-step) resta sul modello principale, ma chat
    # e proposte dell'agente di orchestrazione possono girare su un modello più
    # economico (es. claude-haiku-4-5, ~1/3 del costo) senza perdere qualità sui
    # compiti più semplici. Vuoto = usa `anthropic_model` (nessun cambio di default).
    anthropic_model_chat: str = ""
    anthropic_model_orchestrator: str = ""
    # Durata della cache di prompt sul PREFISSO STATICO (strumenti + system prompt),
    # identico per ogni nucleo/richiesta. "1h" lo mantiene caldo tra upload/chat
    # distanti nel tempo (traffico a raffiche): la scrittura costa 2× ma la lettura
    # 0,1×, quindi conviene già da 3 riutilizzi nell'ora. "5m" = cache standard.
    anthropic_cache_ttl: str = "1h"
    # Budget generoso: scontrini multipagina e verifiche fiscali richiedono spazio.
    agent_max_tokens: int = 8192
    agent_max_tool_iterations: int = 24
    # Ricerca web dell'agente per affinare/verificare le regole fiscali aggiornate.
    # `web_search_max_uses` limita le ricerche per elaborazione: ogni ricerca ha un
    # costo (fee + risultati iniettati in contesto), quindi un tetto basso frena i
    # costi sui documenti (es. farmacia) senza disattivare la funzione.
    enable_web_search: bool = True
    web_search_max_uses: int = 3
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
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    # Upload documenti: dimensione massima del file accettato (MB). Protegge
    # dalla saturazione di memoria (il file viene letto in RAM) e da costi API
    # incontrollati su documenti giganteschi.
    max_upload_mb: int = 20

    # Rate limiting (in-memory, per processo): tetti prudenti per frenare brute
    # force sulle credenziali e abusi/costi sugli endpoint che chiamano l'AI.
    # `*_window` è la finestra in secondi. In deploy multi-worker il conteggio
    # non è condiviso tra i processi: è una prima difesa, non una garanzia.
    rate_limit_login: int = 10
    rate_limit_login_window: int = 300
    rate_limit_chat: int = 30
    rate_limit_chat_window: int = 60
    rate_limit_upload: int = 60
    rate_limit_upload_window: int = 3600
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

    @property
    def model_for_chat(self) -> str:
        """Modello per l'agente conversazionale (fallback al modello principale)."""
        return self.anthropic_model_chat.strip() or self.anthropic_model

    @property
    def model_for_orchestrator(self) -> str:
        """Modello per la fase LLM dell'orchestratore (fallback al principale)."""
        return self.anthropic_model_orchestrator.strip() or self.anthropic_model

    def validate_production_secrets(self) -> None:
        """Rifiuta l'avvio in produzione con segreti di default insicuri.

        Il JWT firma i token di sessione con HS256: se `JWT_SECRET` resta al
        valore di default, chiunque lo conosce (è nel repository) può forgiare
        token validi per qualunque utente. In sviluppo si tollera per comodità;
        in produzione è un fail-fast, come già avviene per il database.
        """
        if self.app_env == "development":
            return
        if self.jwt_secret == DEFAULT_JWT_SECRET or not self.jwt_secret.strip():
            raise RuntimeError(
                "JWT_SECRET non configurato: l'applicazione sta usando il segreto "
                "di default (presente nel codice) in ambiente "
                f"'{self.app_env}'. Chiunque lo conosca può forgiare token di "
                "sessione validi. Imposta JWT_SECRET a una stringa lunga e casuale."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
