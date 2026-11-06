"""security pack, deeper Improve (rounds, population, quick check) and leases

Revision ID: f3a9c1d27b84
Revises: e1a5c7d93b20
Create Date: 2026-11-07 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a9c1d27b84"
down_revision: str | None = "7c2d9e41ab63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # datasets: the security pack's approved cases live in their own dataset, never mixed with the quality set
    op.add_column("datasets", sa.Column("kind", sa.String(length=16), server_default="quality", nullable=False))

    # leases: a worker's claim on running work, renewed by a heartbeat and swept when it runs out (ADR 0037)
    op.add_column("dataset_versions", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evaluation_runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_test_case_runs_running_lease",
        "test_case_runs",
        ["lease_expires_at"],
        postgresql_where=sa.text("status = 'running'"),
    )

    # Improve sessions: rounds, population, quick check, focus, spend cap, the round's starting point
    op.add_column(
        "optimization_sessions", sa.Column("focus", sa.String(length=16), server_default="quality", nullable=False)
    )
    op.add_column("optimization_sessions", sa.Column("focus_ref", sa.Uuid(), nullable=True))
    op.add_column("optimization_sessions", sa.Column("round_limit", sa.Integer(), server_default="1", nullable=False))
    op.add_column("optimization_sessions", sa.Column("current_round", sa.Integer(), server_default="1", nullable=False))
    op.add_column("optimization_sessions", sa.Column("population", sa.Integer(), server_default="3", nullable=False))
    op.add_column(
        "optimization_sessions", sa.Column("quick_check", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("optimization_sessions", sa.Column("target_effect", sa.Float(), nullable=True))
    op.add_column("optimization_sessions", sa.Column("budget_cap", sa.Numeric(18, 8), nullable=True))
    op.add_column("optimization_sessions", sa.Column("round_prompt_id", sa.Uuid(), nullable=True))
    op.add_column("optimization_sessions", sa.Column("round_opt_exp_id", sa.Uuid(), nullable=True))
    op.add_column("optimization_sessions", sa.Column("round_hold_exp_id", sa.Uuid(), nullable=True))
    op.add_column("optimization_sessions", sa.Column("summary", JSONB, nullable=True))
    op.add_column("optimization_sessions", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_optimization_sessions_round_prompt_id_prompt_versions",
        "optimization_sessions",
        "prompt_versions",
        ["round_prompt_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_optimization_sessions_round_opt_exp_id_experiments",
        "optimization_sessions",
        "experiments",
        ["round_opt_exp_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_optimization_sessions_round_hold_exp_id_experiments",
        "optimization_sessions",
        "experiments",
        ["round_hold_exp_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # candidates: the tree (round, parent), quick check, winner, Pareto metrics, rejections kept in the backend
    op.alter_column("prompt_candidates", "prompt_version_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("prompt_candidates", sa.Column("round", sa.Integer(), server_default="1", nullable=False))
    op.add_column("prompt_candidates", sa.Column("parent_candidate_id", sa.Uuid(), nullable=True))
    op.add_column("prompt_candidates", sa.Column("quick_experiment_id", sa.Uuid(), nullable=True))
    op.add_column("prompt_candidates", sa.Column("is_winner", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("prompt_candidates", sa.Column("metrics", JSONB, nullable=True))
    op.add_column("prompt_candidates", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("prompt_candidates", sa.Column("rejected_draft", JSONB, nullable=True))
    op.create_foreign_key(
        "fk_prompt_candidates_parent_candidate_id_prompt_candidates",
        "prompt_candidates",
        "prompt_candidates",
        ["parent_candidate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_prompt_candidates_quick_experiment_id_experiments",
        "prompt_candidates",
        "experiments",
        ["quick_experiment_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "security_packs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("canary", sa.String(length=64), nullable=False),
        sa.Column("categories", JSONB, nullable=False),
        sa.Column("per_category", sa.Integer(), nullable=False),
        sa.Column("tool_app", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("generator", JSONB, nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("dataset_version_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["prompt_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_packs_project_id_id", "security_packs", ["project_id", "id"])
    op.create_table(
        "security_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pack_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("attack", sa.Text(), nullable=False),
        sa.Column("inputs", JSONB, nullable=False),
        sa.Column("safe_behaviour", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pack_id"], ["security_packs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_cases_pack_id_id", "security_cases", ["pack_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_security_cases_pack_id_id", table_name="security_cases")
    op.drop_table("security_cases")
    op.drop_index("ix_security_packs_project_id_id", table_name="security_packs")
    op.drop_table("security_packs")
    op.drop_constraint("fk_prompt_candidates_quick_experiment_id_experiments", "prompt_candidates", type_="foreignkey")
    op.drop_constraint(
        "fk_prompt_candidates_parent_candidate_id_prompt_candidates", "prompt_candidates", type_="foreignkey"
    )
    for column in (
        "rejected_draft",
        "rejection_reason",
        "metrics",
        "is_winner",
        "quick_experiment_id",
        "parent_candidate_id",
        "round",
    ):
        op.drop_column("prompt_candidates", column)
    op.execute("DELETE FROM prompt_candidates WHERE prompt_version_id IS NULL")
    op.alter_column("prompt_candidates", "prompt_version_id", existing_type=sa.Uuid(), nullable=False)
    for name in (
        "fk_optimization_sessions_round_hold_exp_id_experiments",
        "fk_optimization_sessions_round_opt_exp_id_experiments",
        "fk_optimization_sessions_round_prompt_id_prompt_versions",
    ):
        op.drop_constraint(name, "optimization_sessions", type_="foreignkey")
    for column in (
        "lease_expires_at",
        "summary",
        "round_hold_exp_id",
        "round_opt_exp_id",
        "round_prompt_id",
        "budget_cap",
        "target_effect",
        "quick_check",
        "population",
        "current_round",
        "round_limit",
        "focus_ref",
        "focus",
    ):
        op.drop_column("optimization_sessions", column)
    op.drop_index("ix_test_case_runs_running_lease", table_name="test_case_runs")
    op.drop_column("evaluation_runs", "lease_expires_at")
    op.drop_column("dataset_versions", "lease_expires_at")
    op.drop_column("datasets", "kind")
