# Gestione Spese Familiari & Archivio Documenti

App web (FastAPI + interfaccia SPA) multi-utente per tracciare le spese annuali
di un nucleo familiare e costruire un archivio documentale ordinato in ottica
fiscale italiana (730 / Redditi PF). I documenti (scontrini, fatture, ricevute)
vengono caricati, letti da un agente AI (Claude con vision + tool use) che estrae
i dati, li classifica fiscalmente, li attribuisce al soggetto corretto e li
archivia.

## Interfaccia web (GUI)

L'app serve una **single-page application** (nessun build step, nessuna
dipendenza esterna) su `/`. Aprendo `http://localhost:8000/` trovi:

- **Login / Registrazione**: crea un nuovo nucleo o accedi; "Unisciti" per
  entrare in un nucleo esistente con il suo ID.
- **Dashboard**: KPI (totale speso, potenzialmente agevolabile, documenti, da
  rivedere) e grafici per categoria, classificazione fiscale, membro, ambito e
  andamento annuale. Filtro per anno.
- **Carica documento**: drag & drop multi-file con elaborazione in background e
  aggiornamento automatico dello stato.
- **Archivio**: tutti i documenti con ricerca e filtri, dettaglio a comparsa con
  anteprima del file, righe collegate, rielaborazione ed eliminazione.
- **Spese**: tabella dei movimenti con **correzione inline** di categoria,
  classificazione fiscale, ambito e soggetto pagante; eliminazione riga.
- **Casa & Bollette**: riconoscimento delle bollette domestiche (luce, gas,
  acqua, rifiuti/TARI, internet, condominio, ...), **valutazione costi**
  (importo medio, consumi, costo unitario €/kWh·Smc·m³, andamento) e
  **amministrazione** con scadenzario (bollette scadute e in arrivo), stato di
  pagamento e export CSV. Inserimento manuale e modifica di una bolletta.
- **Assistente**: chat in linguaggio naturale sullo storico ("quanto ho speso in
  farmaci nel 2025?", "quanto spendo di luce?", "quali bollette devo pagare?").
- **Impostazioni**: gestione membri del nucleo ed **export CSV** per il
  commercialista (riepilogo per soggetto e classificazione fiscale).
- Tema chiaro/scuro, layout responsive (desktop e mobile), notifiche e stati di
  caricamento/vuoto curati.

> L'API REST resta disponibile e documentata su `/docs`.

## Stack
- Python 3.12, FastAPI, Uvicorn
- SQLAlchemy 2.0 async + Alembic
- PostgreSQL 16 + pgvector
- Pydantic v2 / pydantic-settings
- Anthropic SDK (agente di estrazione/classificazione)
- Auth JWT, storage su volume (locale; S3 predisposto)

## Avvio in locale
```bash
# 1) dipendenze
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2) Postgres con pgvector (esempio Docker)
docker run -d --name spese-pg -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=spese pgvector/pgvector:pg16

# 3) configurazione
cp .env.example .env   # imposta ANTHROPIC_API_KEY e JWT_SECRET

# 4) migrazioni + avvio
alembic upgrade head
uvicorn app.main:app --reload
```
Docs interattive: http://localhost:8000/docs

## Flusso d'uso
1. `POST /auth/register` crea nucleo + utente admin, ritorna il token.
2. `POST /documents` (multipart, campo `file`) carica un documento; l'agente lo
   elabora in background.
3. `GET /documents/{id}` per stato e dati estratti; `GET /documents/{id}/file`
   per scaricare l'originale.
4. `GET /stats/*` per le statistiche; `POST /chat` per interrogare lo storico
   ("quanto ho speso in farmaci nel 2025?").
5. `GET /bills/*` per le bollette di casa: `/bills/analysis` (costi per utenza),
   `/bills/trend` (andamento), `/bills/upcoming` (scadenzario),
   `POST /bills/{id}/pay` (segna pagata), `/bills/export.csv`.

## Deploy su Railway
1. Crea un nuovo progetto da questo repo (usa il `Dockerfile`).
2. Aggiungi il plugin **PostgreSQL**; abilita pgvector (`CREATE EXTENSION vector`,
   gestito comunque dalla migrazione iniziale).
3. Aggiungi un **Volume** persistente montato sul path di `STORAGE_DIR`
   (default `/data/documents`).
4. Variabili d'ambiente: `ANTHROPIC_API_KEY`, `JWT_SECRET`, `APP_ENV=production`
   (e opzionali per la ricerca semantica). **Collega esplicitamente il database**:
   aggiungi al servizio dell'app la variabile
   `DATABASE_URL=${{Postgres.DATABASE_URL}}` (in alternativa l'app sa ricostruire
   l'URL dalle variabili `PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE`). Senza
   questa configurazione l'app fallisce all'avvio con un messaggio esplicito
   invece di tentare una connessione a `localhost`.
5. Lo start command esegue `alembic upgrade head` e poi avvia Uvicorn.

Vedi `CLAUDE.md` per il brief di sviluppo e il backlog.
