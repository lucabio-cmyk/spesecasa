from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class DocumentType(StrEnum):
    SCONTRINO = "scontrino"
    FATTURA = "fattura"
    RICEVUTA = "ricevuta"
    RICEVUTA_SANITARIA = "ricevuta_sanitaria"
    BOLLETTA = "bolletta"
    VERBALE_ASSEMBLEA = "verbale_assemblea"  # verbale di assemblea condominiale
    F24 = "f24"
    BONIFICO = "bonifico"
    CONTRATTO = "contratto"
    POLIZZA = "polizza"
    ALTRO = "altro"


class UtilityType(StrEnum):
    """Tipo di utenza/spesa domestica ricorrente di una bolletta."""

    ENERGIA_ELETTRICA = "energia_elettrica"
    GAS = "gas"
    ACQUA = "acqua"
    RIFIUTI = "rifiuti"  # TARI / tassa rifiuti
    INTERNET_TELEFONO = "internet_telefono"
    RISCALDAMENTO = "riscaldamento"  # teleriscaldamento / centralizzato
    CONDOMINIO = "condominio"
    ASSICURAZIONE_CASA = "assicurazione_casa"
    MANUTENZIONE = "manutenzione"  # caldaia, ascensore, interventi
    ALTRO = "altro"


class BillStatus(StrEnum):
    """Stato amministrativo di pagamento di una bolletta."""

    DA_PAGARE = "da_pagare"
    PAGATA = "pagata"
    SCADUTA = "scaduta"  # non pagata oltre la scadenza
    RATEIZZATA = "rateizzata"


class PaymentMethodType(StrEnum):
    """Tipo di strumento di pagamento di un metodo di pagamento del nucleo.

    Ogni metodo (es. "Carta Visa di Mario", "Bancomat conto cointestato") è
    intestato a un membro e descrive con quale strumento è stata pagata una
    spesa/bolletta/documento."""

    CARTA_CREDITO = "carta_credito"
    CARTA_DEBITO = "carta_debito"
    BANCOMAT = "bancomat"  # carta di debito su circuito nazionale
    PREPAGATA = "prepagata"
    CONTANTI = "contanti"
    BONIFICO = "bonifico"
    ADDEBITO_DIRETTO = "addebito_diretto"  # RID/SDD/domiciliazione
    ASSEGNO = "assegno"
    PAYPAL = "paypal"  # o altri wallet digitali
    ALTRO = "altro"


# Etichetta leggibile dei tipi di metodo di pagamento (GUI e prompt).
PAYMENT_METHOD_TYPE_INFO: dict[str, str] = {
    "carta_credito": "Carta di credito",
    "carta_debito": "Carta di debito",
    "bancomat": "Bancomat / carta di debito nazionale",
    "prepagata": "Carta prepagata",
    "contanti": "Contanti",
    "bonifico": "Bonifico bancario",
    "addebito_diretto": "Addebito diretto (RID/SDD/domiciliazione)",
    "assegno": "Assegno",
    "paypal": "PayPal / wallet digitale",
    "altro": "Altro",
}

# Gli strumenti tracciabili (non contanti): rilevante per la detraibilità fiscale
# di alcune spese, che spesso richiede pagamento tracciato.
TRACEABLE_PAYMENT_TYPES: frozenset[str] = frozenset(
    {
        "carta_credito",
        "carta_debito",
        "bancomat",
        "prepagata",
        "bonifico",
        "addebito_diretto",
        "assegno",
        "paypal",
    }
)


class ReviewSeverity(StrEnum):
    """Gravità di un avviso/proposta dell'agente di orchestrazione."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ReviewStatus(StrEnum):
    """Stato di una voce di revisione prodotta dall'agente di orchestrazione."""

    PENDING = "pending"  # in attesa di decisione dell'utente
    APPROVED = "approved"  # accettata (proposta applicata, vedi `applied`)
    APPLIED = "applied"  # proposta accettata e modifica eseguita
    REJECTED = "rejected"  # proposta rifiutata
    DISMISSED = "dismissed"  # avviso ignorato/archiviato senza azione
    FAILED = "failed"  # tentativo di applicazione fallito


class ReviewKind(StrEnum):
    """Tipo di voce di revisione. Determina come si applica un'eventuale azione
    (payload) quando l'utente dà il consenso."""

    RECONCILIATION = "reconciliation"  # somma righe != totale documento
    MISSING_LINES = "missing_lines"  # documento con importo ma senza righe
    SKIPPED_LINE = "skipped_line"  # riga non calcolata/illeggibile
    MISSING_CLASSIFICATION = "missing_classification"  # classificazione da verificare
    MISSING_ATTRIBUTION = "missing_attribution"  # manca pagante/beneficiario
    POSSIBLE_DUPLICATE = "possible_duplicate"  # documento forse duplicato
    PROCESSING_FAILED = "processing_failed"  # elaborazione non riuscita
    RELIABILITY = "reliability"  # nota di affidabilità da rivedere
    CATEGORY_PROPOSAL = "category_proposal"  # proposta di nuova categoria (consenso)
    RECLASSIFICATION = "reclassification"  # proposta di riclassificazione (consenso)
    ATTRIBUTION = "attribution"  # proposta di attribuzione soggetto (consenso)
    INSIGHT = "insight"  # osservazione/anomalia informativa


# Le voci che rappresentano una PROPOSTA con un'azione applicabile previo
# consenso dell'utente (le altre sono avvisi informativi da prendere in carico).
REVIEW_PROPOSAL_KINDS: frozenset[str] = frozenset(
    {
        ReviewKind.CATEGORY_PROPOSAL.value,
        ReviewKind.RECLASSIFICATION.value,
        ReviewKind.ATTRIBUTION.value,
    }
)


class FiscalClassification(StrEnum):
    DETRAIBILE = "detraibile"
    DEDUCIBILE = "deducibile"
    NON_RILEVANTE = "non_rilevante"
    DA_VERIFICARE = "da_verificare"


class ExpenseScope(StrEnum):
    PERSONALE = "personale"
    FAMILIARE = "familiare"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


# Categorie merceologiche STABILI per le statistiche domestiche, organizzate in
# DUE LIVELLI (macro-categoria → sottocategoria) per restare coerenti ed evitare
# doppioni. La spesa del supermercato è per natura suddivisa per reparto: le sue
# voci sono SOTTOCATEGORIE del gruppo "spesa supermercato". Le altre categorie di
# base (es. "farmaci") sono macro-categorie a sé (foglie di primo livello, senza
# padre). Ogni nucleo può aggiungere proprie macro-categorie o sottocategorie
# personalizzate (tabella `expense_categories`).
#
# IMPORTANTE: la spesa resta classificata sulla FOGLIA (sottocategoria o
# macro-categoria-foglia) in `Expense.merch_category`; il gruppo si deriva dal
# catalogo (qui sotto / dal `parent` delle categorie personalizzate), senza
# duplicare l'informazione su ogni riga.

# Macro-categoria del supermercato (parent delle voci di reparto).
SUPERMARKET_GROUP = "spesa supermercato"

# Descrizione delle macro-categorie (gruppi) di base.
MERCHANDISE_GROUP_INFO: dict[str, str] = {
    SUPERMARKET_GROUP: "spesa quotidiana al supermercato/alimentari, suddivisa per reparto",
}

# Definizione delle categorie merceologiche di base: (nome, descrizione, gruppo).
# gruppo=None ⇒ macro-categoria di primo livello (foglia senza padre).
# L'ORDINE è stabile: non cambiarlo per non confondere lo storico e le viste.
_MERCHANDISE_DEF: list[tuple[str, str, str | None]] = [
    ("frutta e verdura", "ortofrutta fresca, legumi e frutta secca", SUPERMARKET_GROUP),
    ("carne e pesce", "carni, salumi, pesce e prodotti ittici", SUPERMARKET_GROUP),
    ("latticini e uova", "latte, formaggi, yogurt, burro, uova", SUPERMARKET_GROUP),
    ("pane, forno e colazione", "pane, prodotti da forno, biscotti, cereali, caffè", SUPERMARKET_GROUP),
    ("pasta, riso e dispensa", "pasta, riso, farine, conserve, condimenti, dispensa secca", SUPERMARKET_GROUP),
    ("bevande", "acqua, bibite, succhi, vino, birra, alcolici", SUPERMARKET_GROUP),
    ("surgelati", "prodotti surgelati e gelati", SUPERMARKET_GROUP),
    ("infanzia", "pannolini, latte e omogeneizzati, prodotti per neonati", SUPERMARKET_GROUP),
    ("igiene personale", "cura della persona: detergenti, dentifricio, carta igienica", SUPERMARKET_GROUP),
    ("pulizia casa", "detersivi, prodotti e accessori per la pulizia della casa", SUPERMARKET_GROUP),
    ("animali", "cibo e accessori per animali domestici", SUPERMARKET_GROUP),
    ("farmaci", "medicinali con codice del farmaco (AIC/minsan) — dato sanitario", None),
    ("parafarmacia da supermercato", "integratori generici, cerotti, igiene non medicinale", SUPERMARKET_GROUP),
    ("casa e cucina", "stoviglie, utensili, piccoli articoli per la casa", SUPERMARKET_GROUP),
    ("altre spese supermercato", "spesa generica al supermercato non attribuibile a un reparto specifico", SUPERMARKET_GROUP),
]

# Elenco piatto delle categorie di base (foglie), retro-compatibile.
MERCHANDISE_CATEGORIES: list[str] = [name for name, _d, _g in _MERCHANDISE_DEF]

# Descrizione sintetica delle categorie di base: guida l'agente nella
# classificazione e documenta lo storico (mostrata anche in GUI). Non ha valore
# fiscale vincolante.
MERCHANDISE_CATEGORY_INFO: dict[str, str] = {
    name: desc for name, desc, _g in _MERCHANDISE_DEF
}

# Mappa foglia → macro-categoria (gruppo) di base. None ⇒ la foglia è già una
# macro-categoria di primo livello (es. "farmaci").
MERCHANDISE_CATEGORY_GROUP: dict[str, str | None] = {
    name: grp for name, _d, grp in _MERCHANDISE_DEF
}

# Nomi che indicano GENERICAMENTE "la spesa al supermercato": NON vanno creati
# come nuove categorie (sarebbero doppioni del gruppo `spesa supermercato`). Una
# spesa generica del supermercato senza dettaglio di reparto va in "altre spese
# supermercato"; una voce di reparto va nella sottocategoria adatta. La mappa
# associa il sinonimo alla sottocategoria di ripiego del gruppo.
RESERVED_GROUP_SYNONYMS: dict[str, str] = {
    "spesa supermercato": "altre spese supermercato",
    "supermercato": "altre spese supermercato",
    "supermarket": "altre spese supermercato",
    "spesa": "altre spese supermercato",
    "spesa alimentare": "altre spese supermercato",
    "alimentari": "altre spese supermercato",
    "alimentare": "altre spese supermercato",
    "generi alimentari": "altre spese supermercato",
    "drogheria": "altre spese supermercato",
}

# Categorie merceologiche che contengono dati sanitari sensibili: i FARMACI
# (es. dallo "scontrino parlante" della farmacia, con codice AIC/minsan) sono
# dati relativi alla salute. La visualizzazione di DETTAGLIO di queste spese è
# riservata agli amministratori del nucleo; per i non-amministratori le righe e
# gli aggregati di queste categorie vengono nascosti. Distinta da
# "parafarmacia da supermercato", che raccoglie articoli non-medicinali.
SENSITIVE_CATEGORIES: frozenset[str] = frozenset({"farmaci"})

# Unità di misura tipica del consumo per tipo di utenza (per i costi unitari,
# es. €/kWh, €/Smc). Indicativa: l'unità reale resta letta dalla bolletta.
UTILITY_DEFAULT_UNIT: dict[str, str] = {
    "energia_elettrica": "kWh",
    "gas": "Smc",
    "acqua": "m³",
    "riscaldamento": "kWh",
    "rifiuti": "",
    "internet_telefono": "",
    "condominio": "",
    "assicurazione_casa": "",
    "manutenzione": "",
    "altro": "",
}
