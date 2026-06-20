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
    "parafarmacia da supermercato",
    "casa e cucina",
    "altre spese supermercato",
]

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
