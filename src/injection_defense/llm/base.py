"""Model-provider interface. Pipeline code depends only on this, never on a vendor SDK."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMError(Exception):
    """A model call failed. Messages must never contain secrets or document text."""


class ModelNotConfiguredError(LLMError):
    """A real model was requested but its configuration is missing."""

    def __init__(self, role: str, missing: list[str]):
        self.role = role
        self.missing = missing
        super().__init__(f"{role} model is not configured; missing: {', '.join(missing)}")


@dataclass(frozen=True)
class PromptBundle:
    """System instructions and user content, kept separate as far as the provider allows."""

    system: str
    user: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model_name: str
    is_mock: bool


class LLMClient(ABC):
    provider: str
    model_name: str
    is_mock: bool = False
    # Recorded in experiment metadata for reproducibility.
    generation_params: dict[str, object]

    @abstractmethod
    def generate(self, prompt: PromptBundle) -> LLMResponse: ...
