"""Dataset enums shared by the datasets module's tables and API (Phase 2)."""

from enum import StrEnum


class InputFileKind(StrEnum):
    GOLDEN_SET = "golden_set"
    RAW_INPUTS = "raw_inputs"
    REFERENCE_DOCUMENT = "reference_document"


class InputFileStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSED = "parsed"
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
