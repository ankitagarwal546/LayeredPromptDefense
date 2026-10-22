"""Real-LLM adapters (OpenAI-compatible chat completions, Anthropic Messages) and a factory.

Nothing here runs unless the caller asks for a real model and the environment is configured.
Adapters are written against the public API shapes; they have not been exercised against a
live endpoint in this repository's automated tests (which use a stubbed HTTP transport).
"""

from __future__ import annotations

import httpx

from injection_defense.config import Settings
from injection_defense.llm.base import (
    LLMClient,
    LLMError,
    LLMResponse,
    ModelNotConfiguredError,
    PromptBundle,
)
from injection_defense.llm.mock import MockLLM

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class _HTTPClient(LLMClient):
    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        temperature: float,
        max_tokens: int,
        timeout_s: float,
        transport: httpx.BaseTransport | None = None,
    ):
        self.model_name = model
        self._api_key = api_key
        self._http = httpx.Client(timeout=timeout_s, transport=transport)
        self.generation_params = {"temperature": temperature, "max_tokens": max_tokens}
        self._temperature = temperature
        self._max_tokens = max_tokens

    def generate(self, prompt: PromptBundle) -> LLMResponse:
        try:
            response = self._http.post(**self._request(prompt))
            response.raise_for_status()
            text = self._parse(response.json())
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"{self.provider} call failed with HTTP {exc.response.status_code}") from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            # Deliberately drop the original exception: it could echo request details.
            raise LLMError(f"{self.provider} call failed or returned an unexpected response") from None
        return LLMResponse(text=text, model_name=self.model_name, is_mock=False)

    def _request(self, prompt: PromptBundle) -> dict:
        raise NotImplementedError

    def _parse(self, payload: dict) -> str:
        raise NotImplementedError


class OpenAICompatibleClient(_HTTPClient):
    provider = "openai_compatible"

    def __init__(self, *, base_url: str, **kwargs):
        super().__init__(**kwargs)
        self._url = base_url.rstrip("/") + "/chat/completions"

    def _request(self, prompt: PromptBundle) -> dict:
        return {
            "url": self._url,
            "headers": {"Authorization": f"Bearer {self._api_key}"},
            "json": {
                "model": self.model_name,
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                "messages": [
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user},
                ],
            },
        }

    def _parse(self, payload: dict) -> str:
        return payload["choices"][0]["message"]["content"]


class AnthropicClient(_HTTPClient):
    provider = "anthropic"

    def _request(self, prompt: PromptBundle) -> dict:
        return {
            "url": ANTHROPIC_URL,
            "headers": {"x-api-key": self._api_key, "anthropic-version": ANTHROPIC_VERSION},
            "json": {
                "model": self.model_name,
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                "system": prompt.system,
                "messages": [{"role": "user", "content": prompt.user}],
            },
        }

    def _parse(self, payload: dict) -> str:
        return "".join(b["text"] for b in payload["content"] if b.get("type") == "text")


def create_real_llm_client(
    settings: Settings, *, transport: httpx.BaseTransport | None = None
) -> LLMClient:
    """Like create_llm_client("main") but refuses LLM_PROVIDER=mock, so a request for a real
    model can never be answered by the mock."""
    if settings.llm_provider == "mock":
        raise ModelNotConfiguredError("main", ["LLM_PROVIDER (set to a real provider)"])
    return create_llm_client(settings, transport=transport)


def create_llm_client(
    settings: Settings,
    *,
    role: str = "main",
    transport: httpx.BaseTransport | None = None,
) -> LLMClient:
    """Build the client for `role` ("main" or "classifier").

    Raises ModelNotConfiguredError when required settings are missing. Never returns the mock
    for the classifier role, and never substitutes the mock for a missing real configuration.
    """
    if role == "main":
        provider = settings.llm_provider
        if provider == "mock":
            return MockLLM()
        model, key, base_url = settings.llm_model, settings.llm_api_key, settings.llm_base_url
        max_tokens = settings.llm_max_tokens
    else:
        provider = settings.classifier_provider
        model = settings.classifier_model or settings.llm_model
        key = settings.classifier_api_key or settings.llm_api_key
        base_url = settings.classifier_base_url or settings.llm_base_url
        max_tokens = 200

    missing = []
    if provider == "none":
        missing.append("CLASSIFIER_PROVIDER")
    if not model:
        missing.append("CLASSIFIER_MODEL" if role == "classifier" else "LLM_MODEL")
    if key is None or not key.get_secret_value():
        missing.append("CLASSIFIER_API_KEY" if role == "classifier" else "LLM_API_KEY")
    if missing:
        raise ModelNotConfiguredError(role, missing)

    common = dict(
        model=model,
        api_key=key.get_secret_value(),
        temperature=0.0 if role == "classifier" else settings.llm_temperature,
        max_tokens=max_tokens,
        timeout_s=settings.llm_timeout_s,
        transport=transport,
    )
    if provider == "anthropic":
        return AnthropicClient(**common)
    return OpenAICompatibleClient(base_url=base_url, **common)
