"""scores can be unscored: a judge that failed is recorded, not skipped

Revision ID: e1a9b4c70d52
Revises: d58e2fa3b7c9
Create Date: 2026-10-06 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1a9b4c70d52"
down_revision: str | None = "d58e2fa3b7c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scores", sa.Column("status", sa.String(length=16), server_default="scored", nullable=False))


def downgrade() -> None:
    op.drop_column("scores", "status")
