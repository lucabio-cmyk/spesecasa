"""bollette/spese di casa: tabella bills

Revision ID: 0002_bills
Revises: 0001_initial
Create Date: 2026-06-20 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_bills"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("household_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("payer_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("utility_type", sa.String(50), nullable=False, server_default="altro", index=True),
        sa.Column("supplier", sa.String(300), nullable=True),
        sa.Column("service_id", sa.String(100), nullable=True),
        sa.Column("bill_number", sa.String(100), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True, index=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("energy_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("fixed_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("taxes", sa.Numeric(12, 2), nullable=True),
        sa.Column("consumption_quantity", sa.Numeric(12, 3), nullable=True),
        sa.Column("consumption_unit", sa.String(20), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="da_pagare", index=True),
        sa.Column("paid_date", sa.Date(), nullable=True),
        sa.Column("payment_method", sa.String(100), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True, index=True),
        sa.Column("reliability_note", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("bills")
