"""prompt labels, their history, and API token scopes

Revision ID: a8c4e1f7d203
Revises: e1a5c7d93b20
Create Date: 2026-11-07 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8c4e1f7d203"
down_revision: str | None = "e1a5c7d93b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("prompts", sa.Column("accept_moves_label", sa.String(length=48), nullable=True))
    op.add_column("api_tokens", sa.Column("scope", sa.String(length=16), server_default="full", nullable=False))
    op.add_column("api_tokens", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_api_tokens_project_id_projects", "api_tokens", "projects", ["project_id"], ["id"], ondelete="CASCADE"
    )

    op.create_table(
        "prompt_labels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prompt_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("prompt_version_id", sa.Uuid(), nullable=False),
        sa.Column("moved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["prompt_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_labels_prompt_id_name", "prompt_labels", ["prompt_id", "name"], unique=True)
    op.create_index("ix_prompt_labels_prompt_version_id", "prompt_labels", ["prompt_version_id"])

    op.create_table(
        "prompt_label_moves",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("prompt_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=48), nullable=False),
        sa.Column("from_version_id", sa.Uuid(), nullable=True),
        sa.Column("to_version_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=16), nullable=False),
        sa.Column("moved_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_version_id"], ["prompt_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_version_id"], ["prompt_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["moved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_label_moves_prompt_id_id", "prompt_label_moves", ["prompt_id", "id"])


def downgrade() -> None:
    op.drop_table("prompt_label_moves")
    op.drop_table("prompt_labels")
    op.drop_constraint("fk_api_tokens_project_id_projects", "api_tokens", type_="foreignkey")
    op.drop_column("api_tokens", "project_id")
    op.drop_column("api_tokens", "scope")
    op.drop_column("prompts", "accept_moves_label")
