from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class DocumentType(StrEnum):
    SCONTRINO = "scontrino"
    FATTURA = "fattura"
    RICEVUTA = "ricevuta"
    RICEVUTA_SANITARIA = "ricevuta_sanitaria"
    F24 = "f24"
    BONIFICO = "bonifico"
    CONTRATTO = "contratto"
    POLIZZA = "polizza"
    ALTRO = "altro"


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
