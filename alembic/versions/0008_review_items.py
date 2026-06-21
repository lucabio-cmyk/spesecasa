"""voci di revisione dell'agente di orchestrazione (avvisi + proposte con consenso)

Revision ID: 0008_review_items
Revises: 0007_members_no_access
Create Date: 2026-06-21 13:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_review_items"
down_revision = "0007_members_no_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False, server_default="info"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("signature", sa.String(200), nullable=True),
        sa.Column("target_type", sa.String(20), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_review_items_household_id", "review_items", ["household_id"])
    op.create_index("ix_review_items_kind", "review_items", ["kind"])
    op.create_index("ix_review_items_severity", "review_items", ["severity"])
    op.create_index("ix_review_items_status", "review_items", ["status"])
    op.create_index("ix_review_items_signature", "review_items", ["signature"])
    op.create_index("ix_review_items_fiscal_year", "review_items", ["fiscal_year"])


def downgrade() -> None:
    op.drop_index("ix_review_items_fiscal_year", table_name="review_items")
    op.drop_index("ix_review_items_signature", table_name="review_items")
    op.drop_index("ix_review_items_status", table_name="review_items")
    op.drop_index("ix_review_items_severity", table_name="review_items")
    op.drop_index("ix_review_items_kind", table_name="review_items")
    op.drop_index("ix_review_items_household_id", table_name="review_items")
    op.drop_table("review_items")
