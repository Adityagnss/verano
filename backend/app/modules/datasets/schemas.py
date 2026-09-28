"""
Dataset schemas: uploaded input files and their journey into test cases.

An upload goes `uploaded → profiling → ready` (columns, sheets, encoding and sample rows
are known), then, once the user confirms a column mapping, `validating → validated` (the
validation report with row numbers exists), then `importing → imported` (valid rows are
dataset items). Reference documents go `uploaded → extracting → extracted`. Any stage can
end in `failed`, always with a message that says what to do.
A file is a golden set when its mapping includes an expected output or a rubric;
otherwise its rows are raw inputs whose answers will be drafted (DEVELOPMENT.md 2.2).
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class InputFileKind(StrEnum):
    GOLDEN_SET = "golden_set"
    RAW_INPUTS = "raw_inputs"
    REFERENCE_DOCUMENT = "reference_document"


class UploadPurpose(StrEnum):
    ROWS = "rows"
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
    inputs: dict[str, str] = {}
    expected_output: str | None = None
    rubric: str | None = None
    category: str | None = None
    tags: str | None = None
    ignored: list[str] = []

    def assigned(self) -> list[tuple[str, str]]:
        targets = [
            ("expected_output", self.expected_output),
            ("rubric", self.rubric),
            ("category", self.category),
            ("tags", self.tags),
        ]
        return [(f"input:{name}", column) for name, column in self.inputs.items()] + [
            (target, column) for target, column in targets if column is not None
        ]

    @property
    def has_answers(self) -> bool:
        return self.expected_output is not None or self.rubric is not None


class MappingSuggestion(BaseModel):
    prompt_version_id: uuid.UUID
    required_inputs: list[str]
    mapping: ColumnMapping
    unmapped_inputs: list[str]
    kind: InputFileKind


class SheetRequest(BaseModel):
    sheet: str


class MappingRequest(BaseModel):
    prompt_version_id: uuid.UUID
    mapping: ColumnMapping


class IssueKind(StrEnum):
    MISSING_VALUE = "missing_value"
    MISSING_ANSWER = "missing_answer"
    DUPLICATE = "duplicate"
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
    duplicates_removed: int
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
