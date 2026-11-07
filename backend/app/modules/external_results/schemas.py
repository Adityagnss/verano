"""
Schemas for results computed outside Verano. Sizes are capped so one upload cannot fill the database: at most
`MAX_CASES` cases, answers cut to `MAX_ANSWER_CHARS`, and a handful of short notes (commit, branch, ...).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

MAX_CASES = 2000
MAX_ANSWER_CHARS = 2000


class ExternalCase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    passed: bool
    problems: list[str] = Field(default_factory=list, max_length=20)
    answer: str = Field(default="", description="The answer that was checked; long answers are cut.")

    @field_validator("answer")
    @classmethod
    def _cut(cls, answer: str) -> str:
        return answer[:MAX_ANSWER_CHARS]

    @field_validator("problems")
    @classmethod
    def _short(cls, problems: list[str]) -> list[str]:
        return [problem[:500] for problem in problems]


class ExternalRunCreate(BaseModel):
    source: str = Field(default="pytest", min_length=1, max_length=40, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=200, description="What was checked, such as the test suite or commit.")
    cases: list[ExternalCase] = Field(max_length=MAX_CASES)
    details: dict[str, str] = Field(default_factory=dict, description="Short notes: commit, branch.")

    @field_validator("details")
    @classmethod
    def _small(cls, details: dict[str, str]) -> dict[str, str]:
        return {key[:60]: value[:300] for key, value in list(details.items())[:20]}


class ExternalRunSummary(BaseModel):
    id: uuid.UUID
    source: str
    name: str
    passed: int
    failed: int
    details: dict[str, str]
    created_at: datetime


class ExternalRunOut(ExternalRunSummary):
    cases: list[ExternalCase]
