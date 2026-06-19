"""schema iniziale: households, users, documents, expenses (+ pgvector)

Revision ID: 0001_initial
Revises:
Create Date: 2026-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "households",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("household_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("codice_fiscale", sa.String(16), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("household_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payer_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("beneficiary_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("doc_type", sa.String(50), nullable=False, server_default="altro"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending", index=True),
        sa.Column("fiscal_classification", sa.String(50), nullable=False, server_default="da_verificare"),
        sa.Column("scope", sa.String(50), nullable=False, server_default="familiare"),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False, index=True),
        sa.Column("doc_date", sa.Date(), nullable=True),
        sa.Column("issuer", sa.String(300), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("payment_method", sa.String(100), nullable=True),
        sa.Column("document_number", sa.String(100), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True, index=True),
        sa.Column("reliability_note", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("retention_note", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("household_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("payer_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("beneficiary_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True, index=True),
        sa.Column("merchant", sa.String(300), nullable=True),
        sa.Column("description_original", sa.Text(), nullable=True),
        sa.Column("description_normalized", sa.Text(), nullable=True),
        sa.Column("merch_category", sa.String(100), nullable=True, index=True),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=True),
        sa.Column("line_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount", sa.Numeric(12, 2), nullable=True),
        sa.Column("fiscal_classification", sa.String(50), nullable=False, server_default="non_rilevante"),
        sa.Column("scope", sa.String(50), nullable=False, server_default="familiare"),
        sa.Column("fiscal_year", sa.Integer(), nullable=True, index=True),
        sa.Column("reliability_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("expenses")
    op.drop_table("documents")
    op.drop_table("users")
    op.drop_table("households")
