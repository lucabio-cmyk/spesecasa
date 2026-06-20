"""estrazione più ricca: nuovi campi documenti e righe spesa

Revision ID: 0003_richer_extraction
Revises: 0002_bills
Create Date: 2026-06-20 12:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_richer_extraction"
down_revision = "0002_bills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # documents: metadati estratti aggiuntivi per un archivio più ricco
    op.add_column("documents", sa.Column("issuer_vat", sa.String(32), nullable=True))
    op.add_column("documents", sa.Column("recipient_name", sa.String(300), nullable=True))
    op.add_column("documents", sa.Column("recipient_fiscal_code", sa.String(16), nullable=True))
    op.add_column("documents", sa.Column("taxable_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("documents", sa.Column("vat_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("documents", sa.Column("currency", sa.String(3), nullable=True))
    op.add_column("documents", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("documents", sa.Column("payment_traceability", sa.Text(), nullable=True))
    op.add_column("documents", sa.Column("tags", sa.String(500), nullable=True))
    op.add_column("documents", sa.Column("details", postgresql.JSONB(), nullable=True))

    # expenses: prezzo unitario e dati strutturati liberi della riga
    op.add_column("expenses", sa.Column("unit_price", sa.Numeric(12, 4), nullable=True))
    op.add_column("expenses", sa.Column("details", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("expenses", "details")
    op.drop_column("expenses", "unit_price")

    op.drop_column("documents", "details")
    op.drop_column("documents", "tags")
    op.drop_column("documents", "payment_traceability")
    op.drop_column("documents", "due_date")
    op.drop_column("documents", "currency")
    op.drop_column("documents", "vat_amount")
    op.drop_column("documents", "taxable_amount")
    op.drop_column("documents", "recipient_fiscal_code")
    op.drop_column("documents", "recipient_name")
    op.drop_column("documents", "issuer_vat")
