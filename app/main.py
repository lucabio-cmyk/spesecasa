import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import auth, bills, chat, documents, expenses, household, stats
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5.5s [%(name)s] %(message)s",
)
logger = logging.getLogger("app")

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    logger.info(
        "Applicazione avviata (env=%s, storage=%s, static=%s)",
        settings.app_env,
        settings.storage_dir,
        "presente" if STATIC_DIR.is_dir() else "assente",
    )
    yield


app = FastAPI(
    title="Gestione Spese Familiari & Archivio Documenti",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(household.router)
app.include_router(documents.router)
app.include_router(expenses.router)
app.include_router(bills.router)
app.include_router(stats.router)
app.include_router(chat.router)

# Interfaccia web (SPA). Montata per ultima così le route API hanno la
# precedenza; html=True serve index.html per le rotte client-side.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="web")
