"""an improvement candidate keeps the evidence behind its verdict

Revision ID: a3c9d62f1b84
Revises: f2b8c51e9a37
Create Date: 2026-10-07 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3c9d62f1b84"
down_revision: str | None = "f2b8c51e9a37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("prompt_candidates", sa.Column("verdict", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("prompt_candidates", "verdict")
