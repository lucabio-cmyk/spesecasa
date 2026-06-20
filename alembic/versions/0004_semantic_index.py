"""ricerca semantica: indice ANN (HNSW, cosine) sull'embedding dei documenti

Revision ID: 0004_semantic_index
Revises: 0003_richer_extraction
Create Date: 2026-06-20 13:00:00
"""
from alembic import op

revision = "0004_semantic_index"
down_revision = "0003_richer_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Indice HNSW per la similarità coseno (operatore <=> / cosine_distance).
    # HNSW non richiede addestramento e dà buona recall su dati arbitrari;
    # richiede pgvector >= 0.5.0 (presente nell'immagine pgvector/pg16).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_documents_embedding_hnsw "
        "ON documents USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_documents_embedding_hnsw")
