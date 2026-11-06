"""
The shape of `verano.yaml` (version 1).

One file lists the prompts of a codebase. Each entry becomes its own Verano project, because a
Verano project tests one prompt: its test cases, task, models and keys belong to it. Unknown
keys are refused (a typo must not silently do nothing), and API keys can only be named as
`env:NAME`, never written in the file, so a key can't end up in a repository.
"""

import re
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

SUPPORTED_VERSION = 1
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
ENV_REFERENCE = re.compile(r"^(?:env:([A-Za-z_][A-Za-z0-9_]*)|none)$")
VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
MAX_STOP_SEQUENCES = 4
MAX_RUNS = 5

TaskType = Literal[
    "classification",
    "extraction",
    "summarization",
    "question_answering",
    "generation",
    "transformation",
    "conversation",
]
OutputFormat = Literal["single_label", "multi_label", "json", "free_text", "list"]
DEFAULT_OUTPUT: dict[str, OutputFormat] = {
    "classification": "single_label",
    "extraction": "json",
    "summarization": "free_text",
    "question_answering": "free_text",
    "generation": "free_text",
    "transformation": "free_text",
    "conversation": "free_text",
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _number(value: Any) -> Any:
    if isinstance(value, bool | str):
        raise ValueError("must be a number")
    return value


Real = Annotated[float, BeforeValidator(_number), Field(allow_inf_nan=False)]
Whole = Annotated[int, BeforeValidator(_number)]


class Source(Strict):
    """Where the prompt came from in the code, so a later push can say what changed and where."""

    file: str = Field(min_length=1)
    line: int | None = Field(default=None, ge=1)


class Params(Strict):
    """Sampling settings, with the same limits the server applies."""

    temperature: Annotated[Real, Field(ge=0, le=2)] | None = None
    top_p: Annotated[Real, Field(ge=0, le=1)] | None = None
    top_k: Annotated[Whole, Field(ge=1)] | None = None
    max_tokens: Annotated[Whole, Field(ge=1)] | None = None
    seed: Annotated[Whole, Field(ge=0, le=2**31 - 1 - (MAX_RUNS - 1))] | None = None
    presence_penalty: Annotated[Real, Field(ge=-2, le=2)] | None = None
    frequency_penalty: Annotated[Real, Field(ge=-2, le=2)] | None = None
    stop: list[str] | None = None

    @field_validator("stop")
    @classmethod
    def _stop(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unique = sorted({s for s in value if s})
        if len(unique) > MAX_STOP_SEQUENCES:
            raise ValueError(f"at most {MAX_STOP_SEQUENCES} stop sequences")
        if any(len(s) > 100 for s in unique):
            raise ValueError("each stop sequence is at most 100 characters")
        return unique or None

    def given(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class Task(Strict):
    """What the prompt should do. Written here so no model has to be paid to guess it."""

    type: TaskType
    goal: str = Field(min_length=3, max_length=500)
    output: OutputFormat | None = None
    allowed_outputs: list[str] | None = None
    output_schema: dict[str, Any] | None = None
    constraints: list[str] = []
    risks: list[str] = []

    @model_validator(mode="after")
    def _labels_for_classification(self) -> "Task":
        if self.type == "classification" and not self.allowed_outputs:
            raise ValueError("a classification task must list its allowed_outputs")
        return self

    @property
    def output_format(self) -> OutputFormat:
        return self.output or DEFAULT_OUTPUT[self.type]


class Columns(Strict):
    """Which column of the golden file is which. Left out, Verano suggests a mapping."""

    expected_output: str | None = None
    rubric: str | None = None
    category: str | None = None
    tags: str | None = None
    input_file: str | None = None
    ignored: list[str] = []


class Cases(Strict):
    """One test case per row of a table: the easy way to bring your own examples.

    The CLI turns each row into an input file plus a golden row, which is how Verano stores real
    test cases. The `input` column is what the model is sent; `expected` (or `rubric`) is the answer."""

    file: str
    input: str
    expected: str | None = None
    rubric: str | None = None
    category: str | None = None
    tags: str | None = None

    @model_validator(mode="after")
    def _an_answer(self) -> "Cases":
        if self.expected is None and self.rubric is None:
            raise ValueError("name the column with the correct answer (`expected`) or with grading criteria (`rubric`)")
        return self


class Data(Strict):
    cases: Cases | None = None
    golden: str | None = None
    columns: Columns | None = None
    inputs: list[str] = []

    @model_validator(mode="after")
    def _one_way_to_give_data(self) -> "Data":
        if self.columns is not None and self.golden is None:
            raise ValueError("`columns` describes the golden file, so it needs `golden`")
        if self.cases is not None and (self.golden or self.inputs or self.columns):
            raise ValueError("use `cases` (one test case per row) or `inputs` with `golden`, not both")
        return self


class Gate(Strict):
    """What `verano run --ci` demands. Scores are fractions from 0 to 1 (0.8 = 80%)."""

    min_quality: Annotated[Real, Field(ge=0, le=1)] | None = None
    min_pass_rate: Annotated[Real, Field(ge=0, le=1)] | None = None
    max_drop: Annotated[Real, Field(ge=0, le=1)] | None = None

    @model_validator(mode="after")
    def _something_to_check(self) -> "Gate":
        if self.min_quality is None and self.min_pass_rate is None and self.max_drop is None:
            raise ValueError("set at least one of min_quality, min_pass_rate or max_drop")
        return self


class PromptEntry(Strict):
    name: str
    # Prompts with the same `group` share one Verano project (and its test cases); each stays its own prompt
    group: str | None = None
    source: Source | None = None
    system: str | None = None
    system_file: str | None = None
    user: str | None = None
    user_file: str | None = None
    params: Params = Params()
    task: Task
    data: Data = Data()
    models: list[str] = Field(min_length=1)
    judge: str | None = None
    runs: int = Field(default=1, ge=1, le=MAX_RUNS)
    budget: Decimal | None = Field(default=None, gt=0)
    gate: Gate | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not NAME.match(value):
            raise ValueError(
                "use letters, digits, '-', '_' or '.' (up to 64 characters, starting with a letter or digit)"
            )
        return value

    @field_validator("group")
    @classmethod
    def _group(cls, value: str | None) -> str | None:
        if value is not None and not NAME.match(value):
            raise ValueError(
                "use letters, digits, '-', '_' or '.' (up to 64 characters, starting with a letter or digit)"
            )
        return value

    @field_validator("models")
    @classmethod
    def _models(cls, value: list[str]) -> list[str]:
        cleaned = [m.strip() for m in value]
        if any(not m for m in cleaned):
            raise ValueError("a model name is empty")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("a model is listed twice")
        return cleaned

    @model_validator(mode="after")
    def _prompt_text(self) -> "PromptEntry":
        for part in ("system", "user"):
            if getattr(self, part) is not None and getattr(self, f"{part}_file") is not None:
                raise ValueError(f"give `{part}` or `{part}_file`, not both")
        if not any((self.system, self.system_file, self.user, self.user_file)):
            raise ValueError("write a prompt: `system`, `user`, or the same as `system_file` / `user_file`")
        return self


class VeranoFile(Strict):
    version: int
    project: str = Field(min_length=1, max_length=100)
    keys: dict[str, str] = {}
    prompts: list[PromptEntry] = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def _version(cls, value: int) -> int:
        if value != SUPPORTED_VERSION:
            raise ValueError(
                f"this file is version {value}; this CLI reads version {SUPPORTED_VERSION}. "
                "Upgrade the CLI if the file is newer."
            )
        return value

    @field_validator("keys")
    @classmethod
    def _keys(cls, value: dict[str, str]) -> dict[str, str]:
        for provider, reference in value.items():
            if not ENV_REFERENCE.match(reference):
                raise ValueError(
                    f"{provider}: never write a key in this file. Name the environment variable instead, "
                    f"for example `{provider}: env:{provider.upper()}_API_KEY` (or `none` for a provider without a key)"
                )
        return value

    @model_validator(mode="after")
    def _unique_names(self) -> "VeranoFile":
        seen: set[str] = set()
        for entry in self.prompts:
            if entry.name in seen:
                raise ValueError(f"two prompts are called '{entry.name}'")
            seen.add(entry.name)
        return self


def variables_of(*templates: str | None) -> list[str]:
    """`{{ name }}` placeholders, in order of first use."""
    found: list[str] = []
    for template in templates:
        for name in VARIABLE.findall(template or ""):
            if name not in found:
                found.append(name)
    return found
