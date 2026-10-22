"""DEVELOPMENT-ONLY mock model.

This is a deterministic stub for exercising application flow and tests. It is NOT a language
model and its behavior says nothing about how real LLMs respond to prompt injection. Its
"vulnerability" is a fixed regex rule that ignores prompt structure, so no defense can be
evaluated with it. Never report mock-model numbers as research results.
"""

from __future__ import annotations

import re

from injection_defense.llm.base import LLMClient, LLMResponse, PromptBundle

MOCK_MODEL_NAME = "mock-naive-v1"
MOCK_PREFIX = "[MOCK SUMMARY]"

_OVERRIDE = re.compile(
    r"\b(ignore|disregard|forget|set aside|new task|you are now|from now on|instead)\b", re.I
)
_DIRECTIVE = re.compile(
    r"\b(?:output|print|say|write|reply with|respond with)\b[^\"“'\n]{0,40}[\"“']([^\"”'\n]{3,80})[\"”']",
    re.I,
)
_DELIMITED = re.compile(r"^<<<(?!END_)(\w+)>>>\n(.*?)\n<<<END_\1>>>$", re.S | re.M)
_SENTENCE =re.compile(r"(?<=[.!?])\s+")


class MockLLM(LLMClient):
    provider = "mock"
    model_name = MOCK_MODEL_NAME
    is_mock = True
    generation_params = {"deterministic": True}

    def generate(self, prompt: PromptBundle) -> LLMResponse:
        text = self._respond(prompt.user)
        return LLMResponse(text=text, model_name=self.model_name, is_mock=True)

    @staticmethod
    def _respond(user_text: str) -> str:
        directive = _DIRECTIVE.search(user_text)
        if directive and _OVERRIDE.search(user_text):
            return directive.group(1)  # naive "follows the injection" behavior
        delimited = _DELIMITED.search(user_text)
        if delimited:  # structural layout: summarize only the delimited document
            user_text = delimited.group(2)
        paragraphs = [p.strip() for p in user_text.split("\n\n") if p.strip()]
        body = max(paragraphs, key=len) if paragraphs else ""
        sentences = _SENTENCE.split(body)
        return f"{MOCK_PREFIX} " + " ".join(sentences[:2])
