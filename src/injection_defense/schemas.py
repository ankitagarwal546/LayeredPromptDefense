"""Pydantic schemas shared by the pipeline, defenses, and API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from injection_defense.config import MAX_DOCUMENT_CHARS, MAX_INSTRUCTION_CHARS, DefenseConfig


class SummarizeRequest(BaseModel):
    document_text: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARS)
    instruction: str = Field(
        default="Summarize this document.", min_length=1, max_length=MAX_INSTRUCTION_CHARS
    )
    # None -> server default (DEFAULT_MODEL_MODE). "real" never falls back to the mock.
    model: Literal["mock", "real"] | None = None
    # Real mode only: one of the configured names (LLM_MODEL or LLM_EXTRA_MODELS). None -> LLM_MODEL.
    model_name: str | None = Field(default=None, max_length=200)
    # True: the instruction may be any task on the document (the web UI sends this), so the model is
    # not told it is a summarizer. Experiments always summarize and never set it.
    general_task: bool = False
    # Return the exact prompt sent to the model (for the UI's prompt inspector). Never set by experiments.
    include_prompt: bool = False
    # None -> server default preset (DEFAULT_DEFENSE_PRESET).
    defenses: DefenseConfig | None = None

    @field_validator("document_text", "instruction")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class RuleMatch(BaseModel):
    rule_id: str
    description: str
    weight: float
    spans: list[tuple[int, int]]  # character offsets into the original document


class DetectionResult(BaseModel):
    """What a detection layer observed. Policy is recorded separately in `policy_action`."""

    layer: Literal["heuristic", "classifier"]
    # "unavailable": the layer could not run (e.g. no classifier configured). flagged is None.
    status: Literal["evaluated", "unavailable", "error"]
    flagged: bool | None = None
    score: float | None = None
    matched_rules: list[RuleMatch] = Field(default_factory=list)
    explanation: str = ""
    model_name: str | None = None
    model_calls: int = 0
    # Set by the pipeline after applying the configured policy.
    policy_action: Literal["none", "blocked", "sanitized", "flagged_only", "ignored_error"] = "none"


class OutputCriteria(BaseModel):
    """Predefined, explicit criteria for judging a generated output."""

    success_indicators: list[str] = Field(default_factory=list)  # regexes
    forbidden_output_patterns: list[str] = Field(default_factory=list)  # regexes
    # Structured checks (evaluation/attack_checks.py) and the document's key topics they may need.
    checks: list[dict] = Field(default_factory=list)
    key_topics: list[list[str]] = Field(default_factory=list)


class ValidationResult(BaseModel):
    status: Literal["evaluated", "not_evaluated"]
    # no_indicator: nothing matched. indicator_matched: output appears to satisfy the attacker
    # goal. needs_review: matched, but only in what looks like a mention/quotation of the
    # attack, so it must be adjudicated manually. not_evaluated: no criteria were supplied.
    outcome: Literal["no_indicator", "indicator_matched", "needs_review", "not_evaluated"]
    matched_patterns: list[str] = Field(default_factory=list)
    explanation: str = ""


class GuardFindingModel(BaseModel):
    check: str
    detail: str


class RuntimeGuardResult(BaseModel):
    """Oracle-free output checks (defenses/runtime_guard.py)."""

    flagged: bool
    findings: list[GuardFindingModel] = Field(default_factory=list)
    policy_action: Literal["none", "withheld", "flagged_only"] = "none"


class PromptPreview(BaseModel):
    system: str
    user: str


class ModelInfo(BaseModel):
    provider: str
    name: str
    is_mock: bool


class SummarizeResponse(BaseModel):
    request_id: str
    status: Literal["processed", "blocked"]
    blocked_by: str | None = None
    # allow: nothing flagged. warn: processed but something was flagged/sanitized, or a layer
    # could not run. block: no summary was delivered.
    enforcement_decision: Literal["allow", "warn", "block"]
    layers_run: list[str] = Field(default_factory=list)  # layers that actually executed
    reached_model: bool  # False when a defense blocked the request before generation
    summary: str | None = None
    defenses: DefenseConfig
    detections: list[DetectionResult] = Field(default_factory=list)
    output_validation: ValidationResult | None = None
    runtime_guard: RuntimeGuardResult | None = None
    prompt: PromptPreview | None = None  # only when the request asked for it
    model: ModelInfo
    model_calls: int = 0
    latency_ms: float
    timings_ms: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
