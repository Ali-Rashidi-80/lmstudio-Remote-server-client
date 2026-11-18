"""Deduplicate HNSW index, add audit_logs created_at index, and enforce ON DELETE CASCADE.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_rag_chunks_embedding_hnsw")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at)")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'messages_chat_id_fkey') THEN
            ALTER TABLE messages DROP CONSTRAINT messages_chat_id_fkey;
            ALTER TABLE messages
              ADD CONSTRAINT messages_chat_id_fkey
              FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chats_user_id_fkey') THEN
            ALTER TABLE chats DROP CONSTRAINT chats_user_id_fkey;
            ALTER TABLE chats
              ADD CONSTRAINT chats_user_id_fkey
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'refresh_tokens_user_id_fkey') THEN
            ALTER TABLE refresh_tokens DROP CONSTRAINT refresh_tokens_user_id_fkey;
            ALTER TABLE refresh_tokens
              ADD CONSTRAINT refresh_tokens_user_id_fkey
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'knowledge_docs_user_id_fkey') THEN
            ALTER TABLE knowledge_docs DROP CONSTRAINT knowledge_docs_user_id_fkey;
            ALTER TABLE knowledge_docs
              ADD CONSTRAINT knowledge_docs_user_id_fkey
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_created_at")
