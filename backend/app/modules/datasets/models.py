"""
Dataset tables: input_files, datasets, dataset_versions, dataset_items.

An input file is the original upload (kept in Storage under `storage_key`) plus what was
learned about it: its profile, the confirmed column mapping, the validation report and the
outcome of its import or text extraction. Parsed rows become dataset items.
A dataset version is editable while `draft` and frozen once
`approved`; `generation` holds the Eval Generator's settings, progress outcome and the
embedding model behind its dedupe decisions, and `evaluator_set_version_id` the evaluator
set frozen with it. Approval assigns every item its `split` (optimize / holdout), stratified by
category and source. Each item records its `source` (golden / input_file / generated) and
`review_status`, so golden answers are distinguishable and never overwritten by generation.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, CreatedAtMixin, IdMixin, str_enum
from app.modules.datasets.schemas import (
    DatasetVersionStatus,
    FileFormat,
    InputFileKind,
    InputFileStatus,
    ItemSource,
    ReviewStatus,
    Split,
)


class InputFile(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "input_files"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[InputFileKind] = mapped_column(str_enum(InputFileKind, "input_file_kind"))
    status: Mapped[InputFileStatus] = mapped_column(str_enum(InputFileStatus, "input_file_status"))
    format: Mapped[FileFormat] = mapped_column(str_enum(FileFormat, "file_format"))
    filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(1000))
    sheet_name: Mapped[str | None] = mapped_column(String(200))
    row_count: Mapped[int | None]
    profile: Mapped[dict[str, Any] | None]
    column_mapping: Mapped[dict[str, Any] | None]
    validation_report: Mapped[dict[str, Any] | None]
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id", ondelete="SET NULL"))
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"))
    imported_rows: Mapped[int | None]
    section_count: Mapped[int | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Dataset(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (Index(None, "project_id", "id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    # "quality" is the project's own test set; "security" holds an approved attack pack and never mixes with it
    kind: Mapped[str] = mapped_column(String(16), default="quality", server_default="quality")


class DatasetVersion(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (Index(None, "dataset_id", "version", unique=True),)

    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    version: Mapped[int]
    status: Mapped[DatasetVersionStatus] = mapped_column(str_enum(DatasetVersionStatus, "dataset_version_status"))
    task_spec_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("task_specs.id", ondelete="SET NULL"))
    holdout_ratio: Mapped[float | None]
    split_seed: Mapped[int | None]
    generation: Mapped[dict[str, Any] | None]
    evaluator_set_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evaluator_set_versions.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None]
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    lease_expires_at: Mapped[datetime | None]  # a worker's claim on a running generation (ADR 0037)


class DatasetItem(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "dataset_items"
    __table_args__ = (
        Index(None, "dataset_version_id", "id"),
        Index(None, "dataset_version_id", "split"),
        Index(None, "dataset_version_id", "category"),
        Index(None, "input_file_id"),
    )

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"))
    inputs: Mapped[dict[str, Any]]
    expected_output: Mapped[str | None] = mapped_column(Text)
    rubric: Mapped[list[Any] | None]
    category: Mapped[str] = mapped_column(String(64))
    tags: Mapped[list[Any]]
    source: Mapped[ItemSource] = mapped_column(str_enum(ItemSource, "item_source"))
    review_status: Mapped[ReviewStatus] = mapped_column(str_enum(ReviewStatus, "review_status"))
    split: Mapped[Split | None] = mapped_column(str_enum(Split, "split"))
    input_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("input_files.id", ondelete="SET NULL"))
    source_row: Mapped[int | None]
    context: Mapped[list[Any]]
    extra: Mapped[dict[str, Any]]
    position: Mapped[int]
