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


# Categorie merceologiche STABILI per le statistiche domestiche sugli scontrini.
# Estendibili nel tempo, ma mantenerle stabili per non rompere lo storico.
MERCHANDISE_CATEGORIES: list[str] = [
    "frutta e verdura",
    "carne e pesce",
    "latticini e uova",
    "pane, forno e colazione",
    "pasta, riso e dispensa",
    "bevande",
    "surgelati",
    "infanzia",
    "igiene personale",
    "pulizia casa",
    "animali",
    "farmaci",
    "parafarmacia da supermercato",
    "casa e cucina",
    "altre spese supermercato",
]

# Descrizione sintetica delle categorie merceologiche stabili: guida l'agente
# nella classificazione e documenta lo storico (mostrata anche in GUI). Non ha
# valore fiscale vincolante.
MERCHANDISE_CATEGORY_INFO: dict[str, str] = {
    "frutta e verdura": "ortofrutta fresca, legumi e frutta secca",
    "carne e pesce": "carni, salumi, pesce e prodotti ittici",
    "latticini e uova": "latte, formaggi, yogurt, burro, uova",
    "pane, forno e colazione": "pane, prodotti da forno, biscotti, cereali, caffè",
    "pasta, riso e dispensa": "pasta, riso, farine, conserve, condimenti, dispensa secca",
    "bevande": "acqua, bibite, succhi, vino, birra, alcolici",
    "surgelati": "prodotti surgelati e gelati",
    "infanzia": "pannolini, latte e omogeneizzati, prodotti per neonati",
    "igiene personale": "cura della persona: detergenti, dentifricio, carta igienica",
    "pulizia casa": "detersivi, prodotti e accessori per la pulizia della casa",
    "animali": "cibo e accessori per animali domestici",
    "farmaci": "medicinali con codice del farmaco (AIC/minsan) — dato sanitario",
    "parafarmacia da supermercato": "integratori generici, cerotti, igiene non medicinale",
    "casa e cucina": "stoviglie, utensili, piccoli articoli per la casa",
    "altre spese supermercato": "voci non classificabili nelle altre categorie",
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
