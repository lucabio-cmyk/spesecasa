"""gerarchia categorie: colonna parent (macro-categoria) sulle categorie personalizzate

Revision ID: 0010_category_parent
Revises: 0009_payment_methods
Create Date: 2026-06-22 12:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_category_parent"
down_revision = "0009_payment_methods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expense_categories",
        sa.Column("parent", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("expense_categories", "parent")
