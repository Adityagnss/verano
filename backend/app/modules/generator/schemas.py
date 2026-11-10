"""
The Task Spec contract (DEVELOPMENT.md 2.3 Step A).

One LLM call reads the prompt(s), sample rows and document summaries and must return JSON
that validates as `TaskSpec`; the user confirms or edits it before anything else is
generated. Evaluator selection (`evaluation/config/catalog.yaml`), case generation and
failure analysis all read it, which is why it is a strict, versioned schema.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

TASK_SPEC_SCHEMA_VERSION = 1


class TaskType(StrEnum):
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    SUMMARIZATION = "summarization"
    QUESTION_ANSWERING = "question_answering"
    GENERATION = "generation"
    TRANSFORMATION = "transformation"
    CONVERSATION = "conversation"


class OutputFormat(StrEnum):
    SINGLE_LABEL = "single_label"
    MULTI_LABEL = "multi_label"
    JSON = "json"
    FREE_TEXT = "free_text"
    LIST = "list"


class TaskSpecStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: TaskType
    goal: str = Field(min_length=3, max_length=500)
    input_variables: list[str]
    output_format: OutputFormat
    allowed_outputs: list[str] | None = None
    output_schema: dict[str, object] | None = None
    constraints: list[str] = []
    risk_areas: list[str] = []

    @model_validator(mode="after")
    def _labels_for_classification(self) -> "TaskSpec":
        if self.task_type is TaskType.CLASSIFICATION and not self.allowed_outputs:
            raise ValueError("a classification task must list its allowed_outputs")
        if self.task_type is not TaskType.CLASSIFICATION:
            self.allowed_outputs = None  # labels mean nothing outside classification (a draft once listed JSON keys)
        return self


class CaseCategory(StrEnum):
    HAPPY_PATH = "happy_path"
    EDGE_CASE = "edge_case"
    TRICKY = "tricky"
    FORMAT_STRESS = "format_stress"
    ADVERSARIAL = "adversarial"


class GenerationStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"


class GeneratorModel(BaseModel):
    credential_id: uuid.UUID
    model: str


class GeneratorSuggestion(BaseModel):
    suggested: GeneratorModel | None
    candidates: list[GeneratorModel]


class TaskSpecDraftRequest(GeneratorModel):
    prompt_version_id: uuid.UUID


class TaskSpecUpdate(BaseModel):
    spec: TaskSpec


class ProvidedTaskSpec(BaseModel):
    """A Task Spec the user wrote (in `verano.yaml`, for example) instead of having a model draft it.
    The inputs always come from the prompt itself, so they are not part of it."""

    model_config = ConfigDict(extra="forbid")

    task_type: TaskType
    goal: str = Field(min_length=3, max_length=500)
    output_format: OutputFormat
    allowed_outputs: list[str] | None = None
    output_schema: dict[str, object] | None = None
    constraints: list[str] = []
    risk_areas: list[str] = []

    @model_validator(mode="after")
    def _labels_for_classification(self) -> "ProvidedTaskSpec":
        if self.task_type is TaskType.CLASSIFICATION and not self.allowed_outputs:
            raise ValueError("a classification task must list its allowed_outputs")
        return self


class TaskSpecProvide(BaseModel):
    spec: ProvidedTaskSpec
    judge: GeneratorModel | None = None


class TaskSpecOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    prompt_version_id: uuid.UUID
    spec: TaskSpec
    status: TaskSpecStatus
    generator_credential_id: uuid.UUID | None
    generator_model: str | None
    llm_call_id: uuid.UUID | None
    warnings: list[str] = []
    created_at: datetime
    confirmed_at: datetime | None


class GenerationRequest(BaseModel):
    task_spec_id: uuid.UUID
    target_size: int | None = Field(default=None, ge=5, le=1000)
    golden_only: bool = False
    budget_cap: Decimal | None = Field(default=None, gt=0)
    accept_cost: bool = False


class GenerationState(BaseModel):
    status: GenerationStatus
    task_spec_id: uuid.UUID
    target_size: int
    golden_only: bool
    budget_cap: Decimal | None = None
    spent: Decimal = Decimal(0)
    cancel_requested: bool = False
    embedding_model: str | None = None
    counts: dict[str, int] = {}
    dropped_duplicates: int = 0
    dropped_invalid: int = 0
    message: str | None = None
    # the category being regenerated, kept so a job handed to another worker repeats the same work
    regenerate: str | None = None


# What the generator model must return (validated by the gateway's complete_json).
class GeneratedCase(BaseModel):
    inputs: dict[str, str]
    section: int | None = None


class GeneratedBatch(BaseModel):
    cases: list[GeneratedCase]


class DraftAnswer(BaseModel):
    id: int
    expected_output: str | None = None
    rubric: list[str] | None = None


class DraftAnswers(BaseModel):
    answers: list[DraftAnswer]


class GenerationEstimate(BaseModel):
    cases_to_generate: int
    answers_to_draft: int
    calls: int
    input_tokens: int
    output_tokens: int
    cost: Decimal | None
    price_known: bool
    confirm_above: Decimal = Decimal(0)
    needs_confirmation: bool = False


class PromptDraftRequest(GeneratorModel):
    """Ask a model to write a first prompt from the project's documents and, optionally, an end goal."""

    goal: str | None = Field(default=None, max_length=1000)


class PromptDraft(BaseModel):
    system_template: str = Field(min_length=1, max_length=20000)
    user_template: str = Field(min_length=1, max_length=20000)
    variables: list[str] = Field(default_factory=list, max_length=20)
    reasons: list[str] = Field(default_factory=list, max_length=12)
