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
