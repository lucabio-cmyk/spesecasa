"""metodi di pagamento per utente (carta/bancomat/...) e collegamento a documenti, spese e bollette

Crea la tabella `payment_methods` (uno strumento di pagamento intestato a un
membro del nucleo) e aggiunge la colonna `payment_method_id` a `documents`,
`expenses` e `bills` per collegare la spesa allo strumento con cui è stata pagata.

Revision ID: 0009_payment_methods
Revises: 0008_review_items
Create Date: 2026-06-21 14:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_payment_methods"
down_revision = "0008_review_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_methods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("method_type", sa.String(50), nullable=False, server_default="altro"),
        sa.Column("provider", sa.String(120), nullable=True),
        sa.Column("last4", sa.String(8), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    for table in ("documents", "expenses", "bills"):
        op.add_column(
            table,
            sa.Column(
                "payment_method_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("payment_methods.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    for table in ("documents", "expenses", "bills"):
        op.drop_column(table, "payment_method_id")
    op.drop_table("payment_methods")
