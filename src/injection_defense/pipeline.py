"""The configurable defense pipeline: detect -> (policy) -> build prompt -> generate -> validate."""

from __future__ import annotations

import logging
import time
import uuid

from injection_defense.config import DefenseConfig
from injection_defense.defenses.base import Detector
from injection_defense.defenses.heuristic import HeuristicDetector, redact_matches
from injection_defense.defenses.output_validator import OutputValidator
from injection_defense.defenses.structural import build_baseline_prompt, build_structural_prompt
from injection_defense.llm.base import LLMClient
from injection_defense.schemas import (
    DetectionResult,
    ModelInfo,
    OutputCriteria,
    SummarizeResponse,
    ValidationResult,
)

logger = logging.getLogger("injection_defense")

MOCK_WARNING = (
    "MOCK MODEL: development stub, not a language model. Output is not evidence about real "
    "LLM security."
)


class DefensePipeline:
    def __init__(
        self,
        llm: LLMClient,
        config: DefenseConfig,
        *,
        heuristic: Detector | None = None,
        classifier: Detector | None = None,
        validator: OutputValidator | None = None,
    ):
        self.llm = llm
        self.config = config
        self.heuristic = heuristic or HeuristicDetector()
        self.classifier = classifier
        self.validator = validator or OutputValidator()

    def run(
        self,
        document: str,
        instruction: str,
        *,
        criteria: OutputCriteria | None = None,
        request_id: str | None = None,
    ) -> SummarizeResponse:
        started = time.perf_counter()
        timings: dict[str, float] = {}
        detections: list[DetectionResult] = []
        calls = 0
        text = document

        for layer, detector, policy in self._detection_layers():
            t0 = time.perf_counter()
            result = detector.detect(text)
            timings[layer] = _ms(t0)
            calls += result.model_calls
            result.policy_action = self._policy_action(result, policy)
            detections.append(result)
            if result.policy_action == "blocked":
                return self._finish(request_id, started, timings, detections, calls, blocked_by=layer)
            if result.policy_action == "sanitized":
                text = redact_matches(text, result)

        prompt = (
            build_structural_prompt(instruction, text, variant=self.config.structural_variant)
            if self.config.structural
            else build_baseline_prompt(instruction, text)
        )
        t0 = time.perf_counter()
        output = self.llm.generate(prompt).text
        timings["generation"] = _ms(t0)
        calls += 1

        validation = None
        blocked_by = None
        summary: str | None = output
        if self.config.output_validation:
            t0 = time.perf_counter()
            validation = self.validator.validate(output, criteria)
            timings["output_validation"] = _ms(t0)
            if validation.outcome == "indicator_matched" and self.config.output_validation_policy == "withhold":
                summary, blocked_by = None, "output_validation"
        return self._finish(
            request_id, started, timings, detections, calls,
            blocked_by=blocked_by, summary=summary, validation=validation,
        )

    def _detection_layers(self) -> list[tuple[str, Detector, str]]:
        layers = []
        if self.config.heuristic:
            layers.append(("heuristic", self.heuristic, self.config.heuristic_policy))
        if self.config.classifier:
            if self.classifier is None:
                raise ValueError("classifier layer enabled but no classifier was provided")
            layers.append(("classifier", self.classifier, self.config.classifier_policy))
        return layers

    def _policy_action(self, result: DetectionResult, policy: str) -> str:
        """Policy is decided here, separately from what the detector reported."""
        if result.status != "evaluated":
            return "blocked" if self.config.fail_closed_on_detector_error else "ignored_error"
        if not result.flagged:
            return "none"
        return {"block": "blocked", "sanitize": "sanitized", "flag_only": "flagged_only"}[policy]

    def _finish(
        self,
        request_id: str | None,
        started: float,
        timings: dict[str, float],
        detections: list[DetectionResult],
        calls: int,
        *,
        blocked_by: str | None = None,
        summary: str | None = None,
        validation: ValidationResult | None = None,
    ) -> SummarizeResponse:
        response = SummarizeResponse(
            request_id=request_id or uuid.uuid4().hex[:12],
            status="blocked" if blocked_by else "processed",
            blocked_by=blocked_by,
            summary=summary,
            defenses=self.config,
            detections=detections,
            output_validation=validation,
            model=ModelInfo(provider=self.llm.provider, name=self.llm.model_name, is_mock=self.llm.is_mock),
            model_calls=calls,
            latency_ms=_ms(started),
            timings_ms=timings,
            warnings=[MOCK_WARNING] if self.llm.is_mock else [],
        )
        # Metadata only: never the document or the summary text.
        logger.info(
            "request_id=%s status=%s blocked_by=%s config=%s model=%s mock=%s calls=%d latency_ms=%.1f",
            response.request_id, response.status, blocked_by, self.config.name,
            self.llm.model_name, self.llm.is_mock, calls, response.latency_ms,
        )
        return response


def _ms(since: float) -> float:
    return round((time.perf_counter() - since) * 1000, 3)
