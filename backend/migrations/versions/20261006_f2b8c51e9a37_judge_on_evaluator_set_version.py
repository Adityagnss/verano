"""the judge model belongs to the evaluator-set version

Revision ID: f2b8c51e9a37
Revises: e1a9b4c70d52
Create Date: 2026-10-06 11:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2b8c51e9a37"
down_revision: str | None = "e1a9b4c70d52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evaluator_set_versions", sa.Column("judge", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluator_set_versions", "judge")
