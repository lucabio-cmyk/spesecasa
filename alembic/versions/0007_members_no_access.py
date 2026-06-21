"""familiari senza accesso: email e password opzionali sugli utenti

Permette di creare familiari come semplici soggetti (per attribuire spese e
documenti) senza un accesso all'app: email e hashed_password diventano
nullable. L'indice unico sull'email resta valido (Postgres ammette più NULL).

Revision ID: 0007_members_no_access
Revises: 0006_custom_categories
Create Date: 2026-06-21 13:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_members_no_access"
down_revision = "0006_custom_categories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=True)
    op.alter_column(
        "users", "hashed_password", existing_type=sa.String(255), nullable=True
    )


def downgrade() -> None:
    # Per tornare indietro servono valori non nulli: i soggetti senza accesso
    # vanno gestiti prima del downgrade (assegnando email/password o rimossi).
    op.alter_column(
        "users", "hashed_password", existing_type=sa.String(255), nullable=False
    )
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=False)
