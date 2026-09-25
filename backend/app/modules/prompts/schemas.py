"""Prompt enums and shapes shared by the prompts module's API (Phase 2)."""

from enum import StrEnum


class PromptSource(StrEnum):
    MANUAL = "manual"
    ASSISTANT = "assistant"
