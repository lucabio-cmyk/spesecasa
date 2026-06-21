"""categorie merceologiche personalizzate del nucleo (create da agente/utente)

Revision ID: 0006_custom_categories
Revises: 0005_condo_units
Create Date: 2026-06-21 12:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_custom_categories"
down_revision = "0005_condo_units"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expense_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("examples", postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="agent"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint(
            "household_id", "name", name="uq_expense_category_household_name"
        ),
    )


def downgrade() -> None:
    op.drop_table("expense_categories")
