"""an improvement session can name the model that writes the candidates

Revision ID: c4e2a7f91d36
Revises: b7d1e4a20c55
Create Date: 2026-10-09 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e2a7f91d36"
down_revision: str | None = "b7d1e4a20c55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("optimization_sessions", sa.Column("writer", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("optimization_sessions", "writer")
