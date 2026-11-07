"""traffic: imported and received traces, ingest tokens, online scores, alert channels, rules and incidents

Revision ID: 7b3e91c4a2d8
Revises: e1a5c7d93b20
Create Date: 2026-11-07 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7b3e91c4a2d8"
down_revision: str | None = "a8c4e1f7d203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
NOW = sa.text("now()")


def _project() -> sa.Column[sa.Uuid]:
    return sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)


SOURCES = ("golden", "input_file", "generated")
CHECK = "ck_dataset_items_item_source"


def _item_sources(values: tuple[str, ...]) -> None:
    """Replaces the allowed values of a test case's source (a text column with a check, not a database enum)."""
    op.drop_constraint(op.f(CHECK), "dataset_items", type_="check")
    listed = ", ".join(f"'{value}'" for value in values)
    op.create_check_constraint(op.f(CHECK), "dataset_items", f"source IN ({listed})")


def upgrade() -> None:
    _item_sources((*SOURCES, "traffic"))
    op.create_table(
        "traffic_configs",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("scrub_pii", sa.Boolean(), nullable=False),
        sa.Column("scrub_emails", sa.Boolean(), nullable=False),
        sa.Column("scrub_phones", sa.Boolean(), nullable=False),
        sa.Column("scrub_cards", sa.Boolean(), nullable=False),
        sa.Column("scrub_patterns", JSONB, nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("scoring_enabled", sa.Boolean(), nullable=False),
        sa.Column("rule_sample_rate", sa.Float(), nullable=False),
        sa.Column("judge_sample_rate", sa.Float(), nullable=False),
        sa.Column("judge_monthly_limit", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )

    op.create_table(
        "traffic_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        _project(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_traffic_tokens_project_id_id", "traffic_tokens", ["project_id", "id"])
    op.create_index("ix_traffic_tokens_token_hash", "traffic_tokens", ["token_hash"], unique=True)

    op.create_table(
        "traffic_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        _project(),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("input_truncated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("output_truncated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("meta", JSONB, nullable=False),
        sa.Column("scrubbed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("topic_hash", sa.String(length=12), nullable=False),
        sa.Column("case_made_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score_state", sa.String(length=16), server_default="new", nullable=False),
        sa.Column("judge_sampled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("judged", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("judged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quality", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_traffic_traces_project_id_id", "traffic_traces", ["project_id", "id"])
    op.create_index("ix_traffic_traces_project_id_started_at", "traffic_traces", ["project_id", "started_at"])
    op.create_index(
        "ix_traffic_traces_project_id_topic_hash_started_at",
        "traffic_traces",
        ["project_id", "topic_hash", "started_at"],
    )
    op.create_index(
        "ix_traffic_traces_project_id_source_external_id",
        "traffic_traces",
        ["project_id", "source", "external_id"],
        unique=True,
    )
    op.create_index(
        "ix_traffic_traces_project_id_score_state_id", "traffic_traces", ["project_id", "score_state", "id"]
    )
    op.create_index("ix_traffic_traces_project_id_created_at", "traffic_traces", ["project_id", "created_at"])

    op.create_table(
        "traffic_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trace_id", sa.Uuid(), sa.ForeignKey("traffic_traces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evaluator_name", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("judged", sa.Boolean(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_traffic_scores_trace_id", "traffic_scores", ["trace_id"])

    op.create_table(
        "traffic_ingest_days",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("accepted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("ignored", sa.Integer(), server_default="0", nullable=False),
        sa.Column("dropped_rate", sa.Integer(), server_default="0", nullable=False),
        sa.Column("dropped_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_requests", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "day"),
    )

    op.create_table(
        "traffic_alert_channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        _project(),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("target_secret", sa.LargeBinary(), nullable=False),
        sa.Column("target_hint", sa.String(length=300), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_traffic_alert_channels_project_id_id", "traffic_alert_channels", ["project_id", "id"])

    op.create_table(
        "traffic_alert_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        _project(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("metric", sa.String(length=16), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("margin", sa.Float(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("baseline_days", sa.Integer(), nullable=False),
        sa.Column("min_samples", sa.Integer(), nullable=False),
        sa.Column("min_bad_days", sa.Integer(), nullable=False),
        sa.Column("channel_ids", JSONB, nullable=False),
        sa.Column("quiet_start_hour", sa.Integer(), nullable=True),
        sa.Column("quiet_end_hour", sa.Integer(), nullable=True),
        sa.Column("quiet_utc_offset_min", sa.Integer(), server_default="0", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_traffic_alert_rules_project_id_id", "traffic_alert_rules", ["project_id", "id"])

    op.create_table(
        "traffic_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        _project(),
        sa.Column("rule_id", sa.Uuid(), sa.ForeignKey("traffic_alert_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("detail", JSONB, nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notify_results", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_traffic_alerts_project_id_id", "traffic_alerts", ["project_id", "id"])
    op.create_index(
        "ix_traffic_alerts_rule_id",
        "traffic_alerts",
        ["rule_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM dataset_items WHERE source = 'traffic'")
    _item_sources(SOURCES)
    for table in (
        "traffic_alerts",
        "traffic_alert_rules",
        "traffic_alert_channels",
        "traffic_ingest_days",
        "traffic_scores",
        "traffic_traces",
        "traffic_tokens",
        "traffic_configs",
    ):
        op.drop_table(table)
