"""eval generator and review: generation state and frozen evaluator set on dataset versions

Revision ID: 5d2a7c41e9b3
Revises: bcf9f8e01576
Create Date: 2026-09-28 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5d2a7c41e9b3"
down_revision: str | None = "bcf9f8e01576"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = "fk_dataset_versions_evaluator_set_version_id_evaluator_set_versions"


def upgrade() -> None:
    op.add_column("dataset_versions", sa.Column("generation", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("dataset_versions", sa.Column("evaluator_set_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f(FK),
        "dataset_versions",
        "evaluator_set_versions",
        ["evaluator_set_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f(FK), "dataset_versions", type_="foreignkey")
    op.drop_column("dataset_versions", "evaluator_set_version_id")
    op.drop_column("dataset_versions", "generation")
