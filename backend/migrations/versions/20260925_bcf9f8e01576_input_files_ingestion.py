"""input files ingestion: format, profile, mapping target, import and extraction outcome

Revision ID: bcf9f8e01576
Revises: 36e52cff3959
Create Date: 2026-09-25 19:20:20.601798
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "bcf9f8e01576"
down_revision: str | None = "36e52cff3959"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


STATUSES_BEFORE = ("uploaded", "parsed", "failed")
STATUSES_AFTER = (
    "uploaded",
    "profiling",
    "ready",
    "validating",
    "validated",
    "importing",
    "imported",
    "extracting",
    "extracted",
    "failed",
)
FORMATS = ("csv", "xlsx", "json", "jsonl", "pdf", "docx", "txt", "md")
FORMAT_FROM_NAME = """
    CASE lower(substring(filename from '\\.([^.]+)$'))
        WHEN 'tsv' THEN 'csv' WHEN 'ndjson' THEN 'jsonl' WHEN 'markdown' THEN 'md'
        ELSE lower(substring(filename from '\\.([^.]+)$'))
    END
"""


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    op.create_index(op.f("ix_dataset_items_input_file_id"), "dataset_items", ["input_file_id"], unique=False)
    op.add_column("input_files", sa.Column("format", sa.String(length=32), nullable=True))
    op.execute(f"UPDATE input_files SET format = {FORMAT_FROM_NAME}")
    op.alter_column("input_files", "format", nullable=False)
    op.create_check_constraint(op.f("ck_input_files_file_format"), "input_files", f"format IN ({_in(FORMATS)})")
    op.add_column("input_files", sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("input_files", sa.Column("prompt_version_id", sa.Uuid(), nullable=True))
    op.add_column("input_files", sa.Column("dataset_version_id", sa.Uuid(), nullable=True))
    op.add_column("input_files", sa.Column("imported_rows", sa.Integer(), nullable=True))
    op.add_column("input_files", sa.Column("section_count", sa.Integer(), nullable=True))
    op.add_column("input_files", sa.Column("error_message", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_input_files_dataset_version_id_dataset_versions"),
        "input_files",
        "dataset_versions",
        ["dataset_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_input_files_prompt_version_id_prompt_versions"),
        "input_files",
        "prompt_versions",
        ["prompt_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(op.f("ck_input_files_input_file_status"), "input_files", type_="check")
    op.execute("UPDATE input_files SET status = 'extracted' WHERE status = 'parsed'")
    op.create_check_constraint(
        op.f("ck_input_files_input_file_status"), "input_files", f"status IN ({_in(STATUSES_AFTER)})"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_input_files_input_file_status"), "input_files", type_="check")
    op.execute(
        "UPDATE input_files SET status = CASE WHEN status IN ('extracted', 'imported') THEN 'parsed' "
        "WHEN status = 'failed' THEN 'failed' ELSE 'uploaded' END"
    )
    op.create_check_constraint(
        op.f("ck_input_files_input_file_status"), "input_files", f"status IN ({_in(STATUSES_BEFORE)})"
    )
    op.drop_constraint(op.f("fk_input_files_prompt_version_id_prompt_versions"), "input_files", type_="foreignkey")
    op.drop_constraint(op.f("fk_input_files_dataset_version_id_dataset_versions"), "input_files", type_="foreignkey")
    op.drop_column("input_files", "error_message")
    op.drop_column("input_files", "section_count")
    op.drop_column("input_files", "imported_rows")
    op.drop_column("input_files", "dataset_version_id")
    op.drop_column("input_files", "prompt_version_id")
    op.drop_column("input_files", "profile")
    op.drop_constraint(op.f("ck_input_files_file_format"), "input_files", type_="check")
    op.drop_column("input_files", "format")
    op.drop_index(op.f("ix_dataset_items_input_file_id"), table_name="dataset_items")
