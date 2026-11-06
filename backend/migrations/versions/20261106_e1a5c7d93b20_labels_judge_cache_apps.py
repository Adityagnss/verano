"""human labels, the judge cache, stored-answer flags and the apps under test

Revision ID: e1a5c7d93b20
Revises: d8b3f1c62a47
Create Date: 2026-11-06 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1a5c7d93b20"
down_revision: str | None = "d8b3f1c62a47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "test_case_runs", sa.Column("output_truncated", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("test_case_runs", sa.Column("retrieved_chunks", JSONB, nullable=True))
    op.add_column("test_case_runs", sa.Column("tool_calls", JSONB, nullable=True))

    op.create_table(
        "human_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("test_case_run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["experiment_id", "test_case_run_id"],
            ["test_case_runs.experiment_id", "test_case_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_human_labels_experiment_id_test_case_run_id_user_id",
        "human_labels",
        ["experiment_id", "test_case_run_id", "user_id"],
        unique=True,
    )
    op.create_index("ix_human_labels_experiment_id", "human_labels", ["experiment_id"])

    op.create_table(
        "judge_cache",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("evaluator_name", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("hits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "app_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.Uuid(), nullable=False),
        sa.Column("model_profile_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("method", sa.String(length=8), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("request_template", sa.Text(), nullable=False),
        sa.Column("answer_path", sa.String(length=500), nullable=False),
        sa.Column("chunks_path", sa.String(length=500), nullable=True),
        sa.Column("tool_calls_path", sa.String(length=500), nullable=True),
        sa.Column("cost_path", sa.String(length=500), nullable=True),
        sa.Column("auth_kind", sa.String(length=16), nullable=False),
        sa.Column("header_names", JSONB, nullable=False),
        sa.Column("timeout_s", sa.Float(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["credential_id"], ["provider_credentials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["model_profile_id"], ["model_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_targets_project_id_id", "app_targets", ["project_id", "id"])
    op.create_index("ix_app_targets_credential_id", "app_targets", ["credential_id"], unique=True)

    op.create_table(
        "app_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("test_case_run_id", sa.Uuid(), nullable=False),
        sa.Column("app_target_id", sa.Uuid(), nullable=False),
        sa.Column("turn", sa.Integer(), server_default="0", nullable=False),
        sa.Column("request_body", sa.Text(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("truncated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["app_target_id"], ["app_targets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_calls_experiment_id_test_case_run_id", "app_calls", ["experiment_id", "test_case_run_id"])


def downgrade() -> None:
    op.drop_table("app_calls")
    op.drop_table("app_targets")
    op.drop_table("judge_cache")
    op.drop_table("human_labels")
    op.drop_column("test_case_runs", "tool_calls")
    op.drop_column("test_case_runs", "retrieved_chunks")
    op.drop_column("test_case_runs", "output_truncated")
