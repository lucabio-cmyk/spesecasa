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
  `process_document` legge il file (blocco image/document base64; i fogli Excel
  .xls/.xlsx sono convertiti in testo da `app/services/spreadsheets.py` e passati
  come documento di testo) → loop tool-use
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
  per evitare doppi conteggi e abilitare l'analisi dedicata. Nella dashboard le
  **spese condominiali** (`utility_type=condominio`) sono tenute distinte dalle
  **bollette delle utenze**: `bills_service.overview` espone totali separati
  (`utilities_total`/`condo_total`) e `stats.by_category` le mostra come due
  categorie ("Bollette / utenze" e "Spese condominiali").
- **Condominio, verbali di assemblea e unità immobiliari**
  (`app/models/property_unit.py`, sezione CONDOMINIO del system prompt, tool
  `list_property_units`): il nucleo configura le proprie unità immobiliari
  (nome, indirizzo, alias di riconoscimento — interno/scala/subalterno/codice
  condòmino/intestatario —, condominio, millesimi, unità principale). L'agente
  le legge con `list_property_units` per attribuire le spese di condominio
  all'unità corretta. Per i verbali (`doc_type=verbale_assemblea`) fa un'analisi
  approfondita (deliberazioni, riparto, lavori, fondo, rate e scadenze) salvando
  i dettagli in `Bill.details` e collegando l'unità (`Bill.property_unit_id`).
  Se il documento cita più unità ed è ambiguo: in chat chiede a quale unità
  riferirsi; in upload (no domande) marca `da_verificare` e annota. Le
  rate/quote a carico dell'unità diventano `Bill` (utility_type=condominio) con
  scadenza → scadenzario. `query_bills`/`bills_service` filtrano per unità.
- **Addestramento dell'agente** (`Household.agent_instructions`, runner
  `_household_context`): istruzioni libere del nucleo + elenco unità immobiliari
  vengono iniettate nel system prompt a ogni run, così l'agente impara le
  convenzioni del nucleo (es. nome/alias dell'unità di condominio) senza toccare
  il codice. Configurabili dalla GUI (Impostazioni → Addestramento assistente).
- **Multi-utente**: ogni utente appartiene a un `Household`; tutti i dati sono
  scoping per `household_id`. Auth JWT (`app/deps.py`, `app/services/security.py`).
- **Storage** (`app/services/storage.py`): `LocalStorage` su volume; S3 da fare.
- **Ricerca semantica** (`app/services/embeddings.py`, `app/services/search.py`):
  l'embedding del documento (header + sintesi + voci) è calcolato a fine pipeline
  (`index_document`) e salvato nella colonna `embedding` (pgvector, indice HNSW
  cosine). `search_documents` cerca per similarità coseno con **fallback
  automatico alle parole chiave** se la feature è off, il provider non è
  configurato o nessun documento è ancora indicizzato. Esposta via endpoint
  `GET /documents/search?q=` (header `X-Search-Mode`) e via tool agente
  `search_documents`. Attivazione con `ENABLE_SEMANTIC_SEARCH=true` +
  `VOYAGE_API_KEY` (off di default).

## Modello dati (`app/models`)
- `Household`(id, name, agent_instructions) 1—N `User`, 1—N `PropertyUnit`.
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
- `Bill`(household_id, document_id?, payer_user_id, property_unit_id?,
  utility_type, supplier, service_id (POD/PDR/cliente), bill_number,
  period_start/end, issue_date, due_date, total_amount + scomposizione
  (energy_cost/fixed_cost/taxes), consumption_quantity/unit, status, paid_date,
  payment_method, fiscal_year, notes, details (JSONB libero)). Per le
  bollette/spese di casa ricorrenti.
- `PropertyUnit`(household_id, name, address, aliases, owner_name,
  condominium_name, millesimi, is_primary, notes, details (JSONB)). Unità
  immobiliari del nucleo per la gestione del condominio e l'attribuzione delle
  spese (una sola `is_primary` per nucleo).
- Enum salvati come VARCHAR (vedi `app/models/base.py:enum_col`).
- Categorie merceologiche stabili in `app/enums.py:MERCHANDISE_CATEGORIES`;
  tipi utenza/stato bolletta in `UtilityType`/`BillStatus`.

## Superficie API (`app/api`)
- `auth`: `/auth/register` (nuovo nucleo+admin), `/auth/join`, `/auth/login`,
  `/auth/me`, `POST /auth/password-reset` (recupero password self-service via GUI
  senza email: verifica l'identità con email + **codice fiscale** dell'utente
  **oppure** il **codice di recupero** del deploy `ADMIN_RECOVERY_KEY` — utile se
  l'admin è chiuso fuori e non ha CF; confronto a tempo costante, errore generico
  per non rivelare email/CF esistenti. In alternativa l'admin reimposta la
  password dalla modifica membro, o si usa lo script `scripts/reset_password.py`).
- `household`: `GET /household` (info + addestramento), `PATCH /household`
  (nome + `agent_instructions`, admin), `GET/POST /household/members`,
  `PATCH /household/members/{id}` (modifica dati membro post-creazione, es.
  codice fiscale: admin su tutti, ciascun membro su se stesso; il ruolo solo
  admin), `DELETE /household/members/{id}`, `GET/POST /household/units`,
  `PATCH/DELETE /household/units/{id}` (unità immobiliari, gestione admin).
- `documents`: `POST /documents` (upload+process in background), `GET /documents`
  (filtri), `GET /documents/search?q=` (ricerca semantica + fallback keyword),
  `GET /documents/{id}`, `GET /documents/{id}/file`,
  `POST /documents/{id}/reprocess`.
- `expenses`: `GET/POST /expenses`, `PATCH /expenses/{id}` (correzione/verifica).
- `bills`: `GET/POST /bills`, `GET/PATCH/DELETE /bills/{id}`,
  `POST /bills/{id}/pay`, `/bills/overview|analysis|trend|upcoming|export.csv`.
  Le bollette possono essere collegate a una `PropertyUnit` (`property_unit_id`).
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
6. ~~**Ricerca semantica**: calcolo embedding e endpoint `GET /documents/search?q=`
   (pgvector cosine + indice HNSW).~~ FATTO (vedi Architettura). Da estendere:
   embedding anche a livello di `Expense`/`Bill`, provider alternativi, re-index
   batch dei documenti storici.
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
