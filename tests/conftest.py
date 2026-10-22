"""Test safety net: no network, no credentials from the developer's environment or .env."""

import pytest

from injection_defense.config import Settings
from injection_defense.llm.base import LLMClient, LLMResponse, PromptBundle

_ENV_VARS = [
    "LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL",
    "CLASSIFIER_PROVIDER", "CLASSIFIER_MODEL", "CLASSIFIER_API_KEY", "CLASSIFIER_BASE_URL",
    "DEFAULT_MODEL_MODE", "DEFAULT_DEFENSE_PRESET",
]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    def _no_network(*args, **kwargs):
        raise AssertionError("tests must not make real network calls")

    monkeypatch.setattr("httpx.HTTPTransport.handle_request", _no_network)


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)


class ScriptedLLM(LLMClient):
    """Deterministic fake that returns a fixed reply and records every prompt it receives."""

    provider = "scripted-test"
    model_name = "scripted-test-model"
    is_mock = False
    generation_params: dict = {}

    def __init__(self, reply: str = "A neutral summary."):
        self.reply = reply
        self.prompts: list[PromptBundle] = []

    def generate(self, prompt: PromptBundle) -> LLMResponse:
        self.prompts.append(prompt)
        return LLMResponse(text=self.reply, model_name=self.model_name, is_mock=False)
