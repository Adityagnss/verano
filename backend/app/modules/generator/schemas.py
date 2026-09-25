"""
The Task Spec contract (DEVELOPMENT.md 2.3 Step A).

One LLM call reads the prompt(s), sample rows and document summaries and must return JSON
that validates as `TaskSpec`; the user confirms or edits it before anything else is
generated. Evaluator selection (`evaluation/config/catalog.yaml`), case generation and
failure analysis all read it, which is why it is a strict, versioned schema.
"""

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
        return self
