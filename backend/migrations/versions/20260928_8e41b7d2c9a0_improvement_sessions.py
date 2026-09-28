"""improvement sessions: candidate prompt versions, session baseline, stage and message

Revision ID: 8e41b7d2c9a0
Revises: 5d2a7c41e9b3
Create Date: 2026-09-28 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e41b7d2c9a0"
down_revision: str | None = "5d2a7c41e9b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = "fk_optimization_sessions_baseline_experiment_id_experiments"


def upgrade() -> None:
    op.add_column("prompt_versions", sa.Column("is_candidate", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("optimization_sessions", sa.Column("baseline_experiment_id", sa.Uuid(), nullable=True))
    op.add_column(
        "optimization_sessions",
        sa.Column("stage", sa.String(length=32), server_default="analyzing", nullable=False),
    )
    op.add_column("optimization_sessions", sa.Column("message", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f(FK), "optimization_sessions", "experiments", ["baseline_experiment_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint(op.f(FK), "optimization_sessions", type_="foreignkey")
    op.drop_column("optimization_sessions", "message")
    op.drop_column("optimization_sessions", "stage")
    op.drop_column("optimization_sessions", "baseline_experiment_id")
    op.drop_column("prompt_versions", "is_candidate")
