"""gestione condominio: unità immobiliari, addestramento agente, link bollette

Revision ID: 0005_condo_units
Revises: 0004_semantic_index
Create Date: 2026-06-20 14:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_condo_units"
down_revision = "0004_semantic_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unità immobiliari del nucleo (per gestione condominio e addestramento agente).
    op.create_table(
        "property_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("household_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(400), nullable=True),
        sa.Column("aliases", sa.String(500), nullable=True),
        sa.Column("owner_name", sa.String(300), nullable=True),
        sa.Column("condominium_name", sa.String(300), nullable=True),
        sa.Column("millesimi", sa.Numeric(10, 3), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    # Addestramento dell'agente a livello di nucleo.
    op.add_column("households", sa.Column("agent_instructions", sa.Text(), nullable=True))

    # Collegamento bolletta → unità immobiliare + dettagli liberi (analisi verbale).
    op.add_column(
        "bills",
        sa.Column(
            "property_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("property_units.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_bills_property_unit_id", "bills", ["property_unit_id"])
    op.add_column("bills", sa.Column("details", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("bills", "details")
    op.drop_index("ix_bills_property_unit_id", table_name="bills")
    op.drop_column("bills", "property_unit_id")
    op.drop_column("households", "agent_instructions")
    op.drop_table("property_units")
