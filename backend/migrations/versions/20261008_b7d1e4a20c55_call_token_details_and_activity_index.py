"""calls keep cached and reasoning token counts; an index for the activity page

Revision ID: b7d1e4a20c55
Revises: a3c9d62f1b84
Create Date: 2026-10-08 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d1e4a20c55"
down_revision: str | None = "a3c9d62f1b84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_calls", sa.Column("cached_input_tokens", sa.Integer(), nullable=True))
    op.add_column("llm_calls", sa.Column("reasoning_tokens", sa.Integer(), nullable=True))
    op.create_index("ix_llm_calls_project_id_started_at", "llm_calls", ["project_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_calls_project_id_started_at", table_name="llm_calls")
    op.drop_column("llm_calls", "reasoning_tokens")
    op.drop_column("llm_calls", "cached_input_tokens")
