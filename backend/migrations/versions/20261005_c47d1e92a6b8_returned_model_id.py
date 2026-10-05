"""the model id each provider reported for a call: llm_calls and test_case_runs

Revision ID: c47d1e92a6b8
Revises: 8e41b7d2c9a0
Create Date: 2026-10-05 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c47d1e92a6b8"
down_revision: str | None = "8e41b7d2c9a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_calls", sa.Column("response_model", sa.String(length=400), nullable=True))
    op.add_column("test_case_runs", sa.Column("response_model", sa.String(length=400), nullable=True))


def downgrade() -> None:
    op.drop_column("test_case_runs", "response_model")
    op.drop_column("llm_calls", "response_model")
