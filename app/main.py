import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    auth,
    bills,
    chat,
    documents,
    expenses,
    household,
    review,
    stats,
    storage_browser,
)
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5.5s [%(name)s] %(message)s",
)
logger = logging.getLogger("app")

STATIC_DIR = Path(__file__).resolve().parent / "static"


async def _orchestrator_scheduler() -> None:
    """Loop periodico opzionale (off di default): esegue la revisione di tutti i
    nuclei ogni `orchestrator_schedule_hours` ore. Usa un semplice loop asyncio
    interno per non introdurre dipendenze esterne (Celery/cron). La fase LLM è
    disattivata in modalità schedulata per contenere i costi: si limita alle
    verifiche deterministiche dei dati."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models.household import Household
    from app.services import orchestrator

    interval = max(1, settings.orchestrator_schedule_hours) * 3600
    while True:
        try:
            await asyncio.sleep(interval)
            async with SessionLocal() as db:
                ids = list((await db.execute(select(Household.id))).scalars())
            for hid in ids:
                async with SessionLocal() as db:
                    try:
                        await orchestrator.run_orchestration(db, hid, use_llm=False)
                    except Exception:
                        await db.rollback()
            logger.info("Revisione periodica completata su %d nuclei", len(ids))
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Errore nel loop di revisione periodica")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    logger.info(
        "Applicazione avviata (env=%s, storage=%s, static=%s)",
        settings.app_env,
        settings.storage_dir,
        "presente" if STATIC_DIR.is_dir() else "assente",
    )
    scheduler_task = None
    if settings.enable_orchestrator and settings.orchestrator_schedule_hours > 0:
        scheduler_task = asyncio.create_task(_orchestrator_scheduler())
        logger.info(
            "Revisione periodica attiva ogni %d ore", settings.orchestrator_schedule_hours
        )
    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()


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
app.include_router(review.router)
app.include_router(storage_browser.router)

# Interfaccia web (SPA). Montata per ultima così le route API hanno la
# precedenza; html=True serve index.html per le rotte client-side.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="web")
