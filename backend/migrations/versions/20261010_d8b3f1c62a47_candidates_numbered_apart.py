"""Improve's candidate prompt versions are numbered -1, -2, ... so they never use up visible numbers

Revision ID: d8b3f1c62a47
Revises: c4e2a7f91d36
Create Date: 2026-10-10 09:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d8b3f1c62a47"
down_revision: str | None = "c4e2a7f91d36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE prompt_versions AS v
        SET version = -ranked.n
        FROM (
            SELECT id, row_number() OVER (PARTITION BY prompt_id ORDER BY version) AS n
            FROM prompt_versions WHERE is_candidate AND version > 0
        ) AS ranked
        WHERE v.id = ranked.id
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE prompt_versions AS v
        SET version = ranked.top + ranked.n
        FROM (
            SELECT c.id, row_number() OVER (PARTITION BY c.prompt_id ORDER BY c.version DESC) AS n,
                   (SELECT max(version) FROM prompt_versions p WHERE p.prompt_id = c.prompt_id) AS top
            FROM prompt_versions c WHERE c.is_candidate AND c.version < 0
        ) AS ranked
        WHERE v.id = ranked.id
        """
    )
