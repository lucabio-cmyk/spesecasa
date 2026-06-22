"""canonicalizza le categorie 'farmaci' già archiviate (varianti/casing → 'farmaci')

Le righe di farmacia salvate con un nome non allineato alla foglia canonica
('Farmaci' con maiuscola, 'farmaco', 'medicinali', 'farmacia', ...) non
corrispondevano al confronto esatto "farmaci" usato da vista riservata, aggregati
e filtro di riservatezza del dato sanitario: di fatto sparivano dalla sezione
Farmaci. D'ora in poi il salvataggio canonicalizza la categoria (vedi
app/services/categories.canonical_category); questa migrazione allinea lo storico.

Revision ID: 0011_canonicalize_farmaci
Revises: 0010_category_parent
Create Date: 2026-06-22 13:00:00
"""
from alembic import op

revision = "0011_canonicalize_farmaci"
down_revision = "0010_category_parent"
branch_labels = None
depends_on = None

# Varianti ricondotte alla foglia canonica 'farmaci' (incluso 'farmaci' stesso per
# normalizzare casing/spazi). Tenuto allineato a MERCHANDISE_CATEGORY_ALIASES.
_FARMACI_VARIANTS = (
    "farmaci",
    "farmaco",
    "medicinale",
    "medicinali",
    "medicina",
    "medicine",
    "farmacia",
    "farmaco da banco",
    "farmaci da banco",
    "medicinali da banco",
    "medicinale da banco",
)


def upgrade() -> None:
    placeholders = ", ".join(f"'{v}'" for v in _FARMACI_VARIANTS)
    # lower(trim(...)) cattura differenze di maiuscole/spazi; aggiorna solo le
    # righe non già canoniche per non toccare inutilmente lo storico.
    op.execute(
        f"""
        UPDATE expenses
        SET merch_category = 'farmaci'
        WHERE merch_category IS NOT NULL
          AND lower(btrim(merch_category)) IN ({placeholders})
          AND merch_category <> 'farmaci'
        """
    )


def downgrade() -> None:
    # Non reversibile: i nomi originali (varianti) non sono ricostruibili.
    pass
