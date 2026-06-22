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
  spesa da chat), `save_bill`/`record_bill` (bollette di casa), `query_expenses`
  (aggregati + opzioni `include_monthly`/`include_top_merchants`/`include_comparison`),
  `query_bills` (costi/andamento/scadenzario + `include_monthly`),
  `get_yearly_summary`, `get_insights` (osservazioni automatiche sull'anno),
  `create_expense_category` (crea una categoria merceologica nuova quando nessuna
  di quelle note è adatta). Il dispatcher risolve i nomi soggetto→id e
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
- **Categorie merceologiche a due livelli ed estensibili**
  (`enums.MERCHANDISE_CATEGORIES`/`MERCHANDISE_CATEGORY_INFO`/
  `MERCHANDISE_CATEGORY_GROUP`/`MERCHANDISE_GROUP_INFO`/`SUPERMARKET_GROUP`/
  `RESERVED_GROUP_SYNONYMS`, `app/models/category.py:ExpenseCategory`,
  `app/services/categories.py`, tool `create_expense_category`): le categorie
  sono organizzate in una **gerarchia a due livelli** (macro-categoria →
  sottocategoria) per restare coerenti ed evitare doppioni. La spesa al
  supermercato è la macro-categoria «spesa supermercato», suddivisa per reparto
  nelle SOTTOCATEGORIE di base (frutta e verdura, carne e pesce, bevande, …);
  `farmaci` e le macro create dal nucleo sono di primo livello. La spesa resta
  classificata sulla **foglia** (la più specifica) in `Expense.merch_category`;
  il gruppo si deriva dal catalogo (`MERCHANDISE_CATEGORY_GROUP` per le di base,
  `ExpenseCategory.parent` per le personalizzate) senza duplicare l'info su ogni
  riga. Oltre alle categorie "di base" ogni nucleo può avere categorie
  PERSONALIZZATE (tabella `expense_categories`, scoping per nucleo, con
  `parent`/descrizione/esempi/origine). L'agente le crea quando nessuna categoria
  nota descrive bene una spesa (di norma una macro di primo livello; `parent` per
  una nuova sottocategoria di un gruppo) e le riusa: a ogni run il runner inietta
  nel system prompt le **categorie note** raggruppate via `_categories_context`;
  `merch_category` è stringa libera e `add_expenses`/`record_expense`
  auto-registrano (`categories_service.ensure_categories`) le categorie usate non
  ancora note. **Anti-doppione**: i sinonimi generici del supermercato
  (`RESERVED_GROUP_SYNONYMS`: supermercato/spesa/alimentari/…) non diventano nuove
  categorie ma rimandano a `altre spese supermercato` (vedi
  `categories_service.reserved_redirect`). I medicinali restano nella categoria di
  base `farmaci` (l'agente non crea categorie per dati sanitari). `stats.by_category`
  fa il **roll-up alle macro-categorie** con il dettaglio delle sottocategorie
  (`subcategories`); `GET /expenses?group=` filtra tutte le foglie di un gruppo
  (drill-down dalla dashboard). Gestibili da GUI (Impostazioni → Categorie, con
  selettore del gruppo) e via API `GET/POST /household/categories`,
  `PATCH/DELETE /household/categories/{id}`, `GET /household/category-groups`.
- **Farmaci (categoria + codici + riservatezza admin)** (`enums.SENSITIVE_CATEGORIES`,
  sezione FARMACI del system prompt, `deps.require_admin`/`AdminUser`): i
  medicinali hanno una categoria merceologica dedicata `farmaci` (distinta da
  `parafarmacia da supermercato`). Dallo "scontrino parlante"/ricevuta sanitaria
  l'agente estrae il codice del farmaco (AIC/minsan) e lo cerca online con
  `web_search` su fonti autorevoli (banca dati AIFA) per identificare nome
  commerciale, principio attivo e ATC, salvandoli in `Expense.details`
  (`codice_aic`, `minsan`, `farmaco`, `principio_attivo`, `atc`). Essendo dati
  sanitari sensibili, la **visualizzazione di dettaglio dei farmaci è riservata
  agli amministratori**: `GET /expenses/farmaci` (solo admin) alimenta la vista
  "Farmaci" della GUI (nel menu solo per gli admin); `GET /expenses` e
  `GET /stats/by-category` nascondono la categoria ai non-admin; l'agente di chat
  riceve `is_admin` (`AgentContext.is_admin`) e per i non-admin esclude i farmaci
  da `find_expenses`/`query_expenses` e rifiuta di rivelarne il dettaglio.
- **Addestramento dell'agente** (`Household.agent_instructions`, runner
  `_household_context`): istruzioni libere del nucleo + elenco unità immobiliari
  vengono iniettate nel system prompt a ogni run, così l'agente impara le
  convenzioni del nucleo (es. nome/alias dell'unità di condominio) senza toccare
  il codice. Configurabili dalla GUI (Impostazioni → Addestramento assistente).
- **Pagante di default = utente loggato + Metodi di pagamento per utente**
  (`app/models/payment_method.py:PaymentMethod`, `enums.PaymentMethodType`,
  `app/schemas/payment_method.py`, tool `list_payment_methods`,
  `resolvers.resolve_payment_method_id`): salvo evidenze contrarie il **pagante è
  l'utente che opera**. In upload il documento nasce con `payer_user_id` =
  utente che carica (`app/api/documents.py`); l'agente lo conferma/corregge solo
  se dal documento emerge un altro soggetto (`save_document` usa `resolve_member_id
  or payer esistente`). Le spese da chat (`record_expense`) e le bollette
  (`save_bill`/`record_bill`) ricadono sull'utente corrente; anche le POST REST
  `/expenses` e `/bills` impostano il pagante mancante sull'utente. Inoltre ogni
  membro può avere **metodi di pagamento** (carta credito/debito, bancomat,
  prepagata, contanti, bonifico, addebito diretto/RID, PayPal, ...) intestati a sé
  (`PaymentMethod.user_id`, `label`, `method_type`, `provider`, `last4` — mai il
  PAN completo —, `is_default`, `active`, `details`). `Document`/`Expense`/`Bill`
  hanno `payment_method_id` (FK SET NULL) per collegare la spesa allo strumento
  (e quindi all'intestatario). L'agente legge i metodi con `list_payment_methods`
  e, quando dallo scontrino/estratto riconosce tipo e ultime 4 cifre, passa
  `payment_method_id` ai tool di salvataggio (resolver con preferenza al pagante).
  API `GET/POST /household/payment-methods` + `PATCH/DELETE
  /household/payment-methods/{id}` (admin gestisce tutti, ogni membro i propri);
  GUI in Impostazioni → Metodi di pagamento e selettore nel form bolletta.
- **Multi-utente**: ogni utente appartiene a un `Household`; tutti i dati sono
  scoping per `household_id`. Auth JWT (`app/deps.py`, `app/services/security.py`).
  **Familiari senza accesso**: un membro può esistere come semplice *soggetto*
  (per attribuire spese/documenti/bollette come pagante o beneficiario) **senza
  accesso all'app**: `User.email`/`User.hashed_password` sono nullable e l'admin
  crea il familiare senza credenziali (`POST /household/members` con solo
  `full_name`). Email e password vanno fornite insieme per dare l'accesso (login);
  `UserOut.has_access` indica se il membro può accedere. L'accesso può essere
  aggiunto in seguito da `PATCH /household/members/{id}`. Il login rifiuta gli
  utenti senza password.
- **Agente di orchestrazione / Revisione** (`app/services/orchestrator.py`,
  `app/api/review.py`, `app/models/review.py:ReviewItem`, sezione "Revisione"
  della GUI): un agente in background che (1) con **verifiche deterministiche**
  controlla la coerenza dei dati già archiviati e segnala ciò che NON è stato
  calcolato/gestito correttamente — somma righe ≠ totale documento
  (`reconciliation`), documenti con importo ma senza righe (`missing_lines`),
  righe non calcolate/illeggibili (`skipped_line`, alimentato anche da
  `add_expenses` che annota nella `reliability_note` le righe senza importo),
  classificazioni `da_verificare`, attribuzioni mancanti, possibili duplicati
  (stesso emittente+data+totale), elaborazioni fallite, note di affidabilità; e
  (2) con una **fase LLM** opzionale (`orchestrator_use_llm`) PROPONE
  miglioramenti — nuove categorie/accorpamenti, riclassificazioni, osservazioni
  — tramite tool `propose_category`/`propose_reclassification`/`flag_insight`.
  Ogni esito è una `ReviewItem` (kind/severity/status/payload) deduplicata per
  `signature` (una decisione già presa dall'utente non viene riproposta). Le
  **proposte si applicano SOLO previo consenso** (`POST /review/{id}/approve` →
  `orchestrator.apply_review_item`: crea la categoria ed eventualmente sposta le
  spese, oppure riclassifica/attribuisce). Esecuzione: su richiesta
  (`POST /review/run`), automatica dopo ogni upload
  (`orchestrator_run_after_upload`, scope sul singolo documento, senza LLM) e
  scheduler periodico interno opzionale (`orchestrator_schedule_hours`, loop
  asyncio in `app/main.py`, off di default). Config in `app/config.py`.
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
- `ExpenseCategory`(household_id, name (normalizzato, unico per nucleo),
  parent (macro-categoria/gruppo; None = primo livello), description,
  examples (JSONB), source `agent`/`user`, active). Categorie merceologiche
  PERSONALIZZATE del nucleo, oltre a quelle di base.
- `PaymentMethod`(household_id, user_id (intestatario), label, method_type
  (`PaymentMethodType`), provider, last4, is_default, active, notes,
  details (JSONB)). Strumenti di pagamento dei membri (carte, bancomat, ...).
  `Document`/`Expense`/`Bill` hanno `payment_method_id` (FK SET NULL).
- `ReviewItem`(household_id, kind, severity, status, title, detail, signature,
  target_type/target_id, fiscal_year, payload (JSONB: azione applicabile su
  consenso), source, resolved_at/by, resolution_note). Avvisi e proposte
  dell'agente di orchestrazione (vedi Architettura → Revisione).
- Enum salvati come VARCHAR (vedi `app/models/base.py:enum_col`).
- Categorie merceologiche di base in `app/enums.py:MERCHANDISE_CATEGORIES`
  (descrizioni in `MERCHANDISE_CATEGORY_INFO`), estendibili per nucleo via
  `ExpenseCategory`/`app/services/categories.py`; tipi utenza/stato bolletta in
  `UtilityType`/`BillStatus`.

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
  `PATCH/DELETE /household/units/{id}` (unità immobiliari, gestione admin),
  `GET/POST /household/categories` + `PATCH/DELETE /household/categories/{id}`
  (categorie merceologiche note: di base + personalizzate del nucleo),
  `GET/POST /household/payment-methods` (filtro `user_id`) + `PATCH/DELETE
  /household/payment-methods/{id}` (metodi di pagamento dei membri: admin su
  tutti, ciascun membro sui propri).
- `documents`: `POST /documents` (upload+process in background), `GET /documents`
  (filtri), `GET /documents/search?q=` (ricerca semantica + fallback keyword),
  `GET /documents/{id}`, `GET /documents/{id}/file`,
  `POST /documents/{id}/reprocess`.
- `expenses`: `GET/POST /expenses`, `PATCH /expenses/{id}` (correzione/verifica),
  `GET /expenses/farmaci` (catalogo medicinali, **solo admin**). `GET /expenses`
  nasconde la categoria `farmaci` ai non-admin (dato sanitario sensibile).
- `bills`: `GET/POST /bills`, `GET/PATCH/DELETE /bills/{id}`,
  `POST /bills/{id}/pay`, `/bills/overview|analysis|trend|upcoming|export.csv`.
  Le bollette possono essere collegate a una `PropertyUnit` (`property_unit_id`).
- `stats`: `/stats/overview|by-category|by-member|by-scope|yearly|fiscal-summary|
  fiscal-by-member|export.csv`. **Analisi avanzate** (`app/services/stats.py`):
  `/stats/monthly` (andamento mese per mese di spese+bollette), `/stats/top-merchants`
  (esercenti su cui si spende di più), `/stats/compare` (confronto con l'anno
  precedente per categoria), `/stats/insights` (osservazioni automatiche:
  variazioni, voci principali/in crescita, potenziale fiscale, spese da
  verificare, documenti da rivedere, scadenze). Gli endpoint per-anno usano
  l'anno corrente come default; `top-merchants`/`compare`/`insights` rispettano
  la riservatezza dei farmaci per i non-admin. Lato bollette: `/bills/monthly`
  e `/bills/analysis` (ora con confronto anno-su-anno: spesa, consumo e costo
  unitario). Nella GUI la sezione **Analisi** (`viewAnalisi`) mostra insight,
  andamento mensile, top esercenti e tabella di confronto tra anni. La sezione
  **Esplora** (`viewEsplora`) è una vista interattiva in stile BI: carica una
  volta i movimenti di spesa dell'anno (`GET /expenses?fiscal_year=`) e calcola
  tutti gli aggregati lato client; cliccando un elemento di un qualsiasi grafico
  (mese, categoria, pagante, ambito, classifica fiscale) si attiva un filtro a
  **livello di pagina** che ricalcola gli altri grafici, i KPI e la tabella
  (cross-filtering "escludi te stesso"); i filtri attivi sono "slicer"
  rimovibili e "Apri nelle Spese" porta i filtri nella vista Spese.
- `chat`: `POST /chat` (agente conversazionale sullo storico).
- `review`: `POST /review/run` (avvia la revisione), `GET /review` (voci, filtro
  per stato/gravità/anno; default `pending`), `GET /review/summary` (conteggi per
  il badge), `POST /review/{id}/approve|reject|dismiss` (consenso: applica la
  proposta / rifiuta / archivia l'avviso). Voci prodotte dall'agente di
  orchestrazione (`ReviewItem`).

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
