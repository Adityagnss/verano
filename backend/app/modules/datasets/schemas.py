"""
Dataset schemas: uploaded input files and their journey into test cases.

An upload goes `uploaded → profiling → ready` (columns, sheets, encoding and sample rows
are known), then, once the user confirms a column mapping, `validating → validated` (the
validation report with row numbers exists), then `importing → imported` (valid rows are
dataset items). Reference documents go `uploaded → extracting → extracted`. Any stage can
end in `failed`, always with a message that says what to do.
A file is a golden set when its mapping includes an expected output or a rubric;
otherwise its rows are raw inputs whose answers will be drafted (DEVELOPMENT.md 2.2).
The review schemas (items, filters, bulk approval, the version summary) serve the Review &
Approve step (DEVELOPMENT.md 2.4).
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InputFileKind(StrEnum):
    GOLDEN_SET = "golden_set"
    RAW_INPUTS = "raw_inputs"
    REFERENCE_DOCUMENT = "reference_document"


class UploadPurpose(StrEnum):
    INPUT = "input"
    GOLDEN = "golden"
    DOCUMENT = "document"


class FileFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    JSON = "json"
    JSONL = "jsonl"
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MD = "md"


class InputFileStatus(StrEnum):
    UPLOADED = "uploaded"
    PROFILING = "profiling"
    READY = "ready"
    VALIDATING = "validating"
    VALIDATED = "validated"
    IMPORTING = "importing"
    IMPORTED = "imported"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED = "failed"


class DatasetVersionStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class ItemSource(StrEnum):
    GOLDEN = "golden"
    INPUT_FILE = "input_file"
    GENERATED = "generated"


class ReviewStatus(StrEnum):
    TRUSTED = "trusted"
    DRAFT = "draft"
    APPROVED = "approved"


class Split(StrEnum):
    OPTIMIZE = "optimize"
    HOLDOUT = "holdout"


class FileProfile(BaseModel):
    format: FileFormat
    columns: list[str]
    sheets: list[str] = []
    sheet: str | None = None
    encoding: str | None = None
    delimiter: str | None = None
    row_count: int
    sample_rows: list[dict[str, Any]]
    warnings: list[str] = []


class ColumnMapping(BaseModel):
    expected_output: str | None = None
    rubric: str | None = None
    category: str | None = None
    tags: str | None = None
    input_file: str | None = None
    ignored: list[str] = []

    def assigned(self) -> list[tuple[str, str]]:
        targets = [
            ("expected_output", self.expected_output),
            ("rubric", self.rubric),
            ("category", self.category),
            ("tags", self.tags),
            ("input_file", self.input_file),
        ]
        return [(target, column) for target, column in targets if column is not None]


class MappingSuggestion(BaseModel):
    mapping: ColumnMapping


class SheetRequest(BaseModel):
    sheet: str


class MappingRequest(BaseModel):
    mapping: ColumnMapping


class IssueKind(StrEnum):
    MISSING_ANSWER = "missing_answer"
    UNPAIRED = "unpaired"
    INVALID_ROW = "invalid_row"


class ValidationIssue(BaseModel):
    kind: IssueKind
    field: str | None
    message: str
    count: int
    rows: list[int]


class ValidationReport(BaseModel):
    kind: InputFileKind
    format: FileFormat
    encoding: str | None
    sheet: str | None
    total_rows: int
    valid_rows: int
    skipped_rows: int
    issues: list[ValidationIssue]
    warnings: list[str]


class InputFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    kind: InputFileKind
    status: InputFileStatus
    format: FileFormat
    filename: str
    size_bytes: int
    row_count: int | None
    profile: FileProfile | None
    column_mapping: ColumnMapping | None
    validation_report: ValidationReport | None
    imported_rows: int | None
    section_count: int | None
    prompt_version_id: uuid.UUID | None
    dataset_version_id: uuid.UUID | None
    error_message: str | None
    created_at: datetime


class StoredFile(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    format: FileFormat
    storage_key: str
    filename: str


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_version_id: uuid.UUID
    inputs: dict[str, Any]
    expected_output: str | None
    rubric: list[Any] | None
    category: str
    tags: list[Any]
    source: ItemSource
    review_status: ReviewStatus
    split: Split | None
    input_file_id: uuid.UUID | None
    source_row: int | None
    context: list[Any]
    extra: dict[str, Any]
    position: int


class ItemFilter(BaseModel):
    source: ItemSource | None = None
    category: str | None = None
    review_status: ReviewStatus | None = None
    split: Split | None = None


class ItemCreate(BaseModel):
    inputs: dict[str, Any]
    expected_output: str | None = None
    rubric: list[str] | None = None
    category: str = Field(default="happy_path", min_length=1, max_length=64)
    tags: list[str] = []


class ItemUpdate(BaseModel):
    inputs: dict[str, Any] | None = None
    expected_output: str | None = None
    rubric: list[str] | None = None
    category: str | None = Field(default=None, min_length=1, max_length=64)
    tags: list[str] | None = None


class BulkApprove(BaseModel):
    category: str | None = None
    source: ItemSource | None = None


class GroupCount(BaseModel):
    total: int = 0
    draft: int = 0
    without_answer: int = 0


class DatasetVersionOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    version: int
    status: DatasetVersionStatus
    task_spec_id: uuid.UUID | None
    evaluator_set_version_id: uuid.UUID | None
    generation: dict[str, Any] | None
    holdout_ratio: float | None
    split_seed: int | None
    approved_at: datetime | None
    item_count: int
    by_source: dict[str, GroupCount]
    by_category: dict[str, GroupCount]
    by_split: dict[str, int]
    warnings: list[str]
