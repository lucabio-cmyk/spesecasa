# Brief di sviluppo — Spese Familiari & Archivio Documenti

Questo file orienta lo sviluppo (es. con Claude Code). Lo scaffold è già
coerente e in larga parte funzionante: completa e rifinisci secondo il backlog.

## Obiettivo
App multi-utente (nucleo familiare) per: (1) tracciare le spese annuali; (2)
costruire un archivio documentale preciso e interrogabile in ottica fiscale
italiana (730/Redditi PF), utile anche al commercialista. Cuore del sistema:
un agente che legge i documenti, estrae, classifica fiscalmente, attribuisce al
soggetto e archivia.

## Stack e vincoli
- Python 3.12, FastAPI, SQLAlchemy 2.0 **async**, Alembic, Postgres 16 + pgvector,
  Pydantic v2, Anthropic SDK.
- Modello agente configurabile (`ANTHROPIC_MODEL`, default `claude-sonnet-4-6`).
- **Non** hardcodare soglie, percentuali o requisiti fiscali nel codice o nel
  prompt: sono variabili e vanno verificati con fonti aggiornate. Il dominio
  fiscale resta nel system prompt + revisione umana.

## Architettura
- **Pipeline documento** (`app/agent/runner.py`): upload → salvataggio file →
  `process_document` legge il file (blocco image/document base64) → loop tool-use
  con Claude → il modello chiama gli strumenti per persistere → salva la sintesi
  e aggiorna lo stato (`complete` / `needs_review` / `failed`).
- **Strumenti dell'agente** (`app/agent/tools.py`): `list_household_members`,
  `find_existing_document` (anti-duplicazione), `read_document` (rilegge il file
  originale archiviato — PDF/immagine — per analizzarlo di nuovo su richiesta),
  `save_document` (header), `add_expenses` (righe/movimenti), `record_expense`
  (spesa da chat), `find_expenses`/`delete_expense` (ricerca e cancellazione
  spesa da chat), `save_bill`/`record_bill` (bollette di casa), `query_expenses`,
  `query_bills`, `get_yearly_summary`. Il dispatcher risolve i nomi soggetto→id e
  calcola l'anno fiscale. `read_document` restituisce il file come blocco
  contenuto: il runner lo allega alla risposta dello strumento (chiave
  `_content_blocks`) così il modello può vederlo subito.
- **Bollette / spese di casa** (`app/models/bill.py`, `app/services/bills.py`,
  `app/api/bills.py`): riconoscimento bollette (luce, gas, acqua, rifiuti,
  internet, condominio, ...), valutazione costi (consumi, costo unitario,
  andamento) e amministrazione (scadenzario, stato pagamento). Quando un
  documento è una bolletta l'agente usa `save_bill` invece di `add_expenses`,
  per evitare doppi conteggi e abilitare l'analisi dedicata.
- **Multi-utente**: ogni utente appartiene a un `Household`; tutti i dati sono
  scoping per `household_id`. Auth JWT (`app/deps.py`, `app/services/security.py`).
- **Storage** (`app/services/storage.py`): `LocalStorage` su volume; S3 da fare.
- **Ricerca semantica**: colonna `embedding` (pgvector) predisposta, feature-flag
  `ENABLE_SEMANTIC_SEARCH` (off di default). Wiring lato query da completare.

## Modello dati (`app/models`)
- `Household`(id, name) 1—N `User`.
- `User`(household_id, email, hashed_password, full_name, codice_fiscale, role).
- `Document`(household_id, uploaded_by/payer/beneficiary_user_id, doc_type, status,
  fiscal_classification, scope, file: original_filename/mime_type/storage_path/
  file_hash, header: doc_date/issuer/total_amount/payment_method/document_number/
  fiscal_year, dettagli estesi: issuer_vat/recipient_name/recipient_fiscal_code/
  taxable_amount/vat_amount/currency/due_date/payment_traceability/tags/details
  (JSONB libero), reliability_note, summary, retention_note, embedding) 1—N `Expense`.
- `Expense`(household_id, document_id?, payer/beneficiary_user_id, purchase_date,
  merchant, description_original/normalized, merch_category, quantity, unit_price,
  line_amount, discount, fiscal_classification, scope, fiscal_year, details (JSONB
  libero), reliability_note).
- `Bill`(household_id, document_id?, payer_user_id, utility_type, supplier,
  service_id (POD/PDR/cliente), bill_number, period_start/end, issue_date,
  due_date, total_amount + scomposizione (energy_cost/fixed_cost/taxes),
  consumption_quantity/unit, status, paid_date, payment_method, fiscal_year,
  notes). Per le bollette/spese di casa ricorrenti.
- Enum salvati come VARCHAR (vedi `app/models/base.py:enum_col`).
- Categorie merceologiche stabili in `app/enums.py:MERCHANDISE_CATEGORIES`;
  tipi utenza/stato bolletta in `UtilityType`/`BillStatus`.

## Superficie API (`app/api`)
- `auth`: `/auth/register` (nuovo nucleo+admin), `/auth/join`, `/auth/login`,
  `/auth/me`.
- `documents`: `POST /documents` (upload+process in background), `GET /documents`
  (filtri), `GET /documents/{id}`, `GET /documents/{id}/file`,
  `POST /documents/{id}/reprocess`.
- `expenses`: `GET/POST /expenses`, `PATCH /expenses/{id}` (correzione/verifica).
- `bills`: `GET/POST /bills`, `GET/PATCH/DELETE /bills/{id}`,
  `POST /bills/{id}/pay`, `/bills/overview|analysis|trend|upcoming|export.csv`.
- `stats`: `/stats/by-category|by-member|by-scope|yearly|fiscal-summary`.
- `chat`: `POST /chat` (agente conversazionale sullo storico).

## Variabili d'ambiente
Vedi `.env.example`. Minime per girare: `DATABASE_URL`, `ANTHROPIC_API_KEY`,
`JWT_SECRET`, `STORAGE_DIR`.

## Esecuzione
- Locale: `alembic upgrade head` poi `uvicorn app.main:app --reload`.
- Railway: Dockerfile + Postgres + Volume su `STORAGE_DIR`; lo start esegue le
  migrazioni e avvia il server (vedi `README.md`).

## Backlog prioritizzato (cosa completare)
1. **Inviti nucleo**: sostituire `/auth/join` con household_id libero con un flusso
   a inviti (token monouso, scadenza, ruolo assegnato).
2. **Anti-duplicazione in upload**: se l'hash file esiste già, rispondere 200 con
   il documento esistente invece di ricrearlo.
3. **Ruoli e permessi**: admin vs member (chi può cancellare/modificare cosa).
4. **Refresh token** e logout; rotazione segreti.
5. **Backend S3** in `storage.py` (selezione via `STORAGE_BACKEND`).
6. **Ricerca semantica**: calcolo embedding su `summary`/`description_normalized`
   e endpoint `GET /documents/search?q=` (pgvector cosine + indice ivfflat/hnsw).
7. **Export per commercialista**: CSV/PDF riepilogo annuale per soggetto e per
   classificazione (potenziali detraibili/deducibili) — solo aggregazione dati,
   nessun calcolo d'imposta.
8. **Test**: auth, upload+pipeline (mock Anthropic), dispatcher tool con DB di test.
9. **Robustezza**: rate limiting, gestione file grandi/multipagina, retry agente,
   validazione MIME, logging strutturato.
10. **Edge scontrini**: righe illeggibili, sconti/quantità a peso, multi-pagina.

## Note
- L'inizializzazione del client Anthropic e gli import dell'agente sono lazy nelle
  route per non rallentare l'avvio e i test.
- La migrazione iniziale crea l'estensione `vector` e lo schema completo: se cambi
  i modelli, genera nuove revisioni con `alembic revision --autogenerate`.
