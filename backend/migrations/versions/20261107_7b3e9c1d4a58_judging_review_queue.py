"""review queue: assignments and final verdicts on disputed answers (ADR 0038)

Revision ID: 7b3e9c1d4a58
Revises: e1a5c7d93b20
Create Date: 2026-11-07 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b3e9c1d4a58"
down_revision: str | None = "e1a5c7d93b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("test_case_run_id", sa.Uuid(), nullable=False),
        sa.Column("assignee_user_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by", sa.Uuid(), nullable=True),
        sa.Column("blind", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("batch_label", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["experiment_id", "test_case_run_id"],
            ["test_case_runs.experiment_id", "test_case_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_review_assignments_run_assignee",
        "review_assignments",
        ["experiment_id", "test_case_run_id", "assignee_user_id"],
        unique=True,
    )
    op.create_index(
        "ix_review_assignments_project_id_assignee_user_id_id",
        "review_assignments",
        ["project_id", "assignee_user_id", "id"],
    )
    op.create_index("ix_review_assignments_experiment_id_id", "review_assignments", ["experiment_id", "id"])

    op.create_table(
        "review_resolutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("test_case_run_id", sa.Uuid(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["experiment_id", "test_case_run_id"],
            ["test_case_runs.experiment_id", "test_case_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_review_resolutions_experiment_id_test_case_run_id",
        "review_resolutions",
        ["experiment_id", "test_case_run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("review_resolutions")
    op.drop_table("review_assignments")
