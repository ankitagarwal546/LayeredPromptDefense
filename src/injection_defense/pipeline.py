"""The configurable defense pipeline: detect -> (policy) -> build prompt -> generate -> validate."""

from __future__ import annotations

import logging
import time
import uuid

from injection_defense.config import DefenseConfig
from injection_defense.defenses.base import Detector
from injection_defense.defenses.heuristic import NEUTRAL_REDACTION, REDACTION, HeuristicDetector, redact_matches
from injection_defense.defenses.output_validator import OutputValidator
from injection_defense.defenses.runtime_guard import canary_instruction, check_output, new_canary
from injection_defense.defenses.structural import build_baseline_prompt, build_structural_prompt
from injection_defense.llm.base import LLMClient, PromptBundle
from injection_defense.schemas import (
    DetectionResult,
    GuardFindingModel,
    ModelInfo,
    OutputCriteria,
    PromptPreview,
    RuntimeGuardResult,
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
        role: str | None = None,
    ):
        self.llm = llm
        self.config = config
        self.role = role  # None = the evaluated summarization role line (see structural.GENERAL_ROLE)
        self.heuristic = heuristic or HeuristicDetector.for_version(config.heuristic_rules)
        # A prompt-based classifier follows the configured prompt version; other detectors are used as given.
        self.classifier = classifier.with_prompt(config.classifier_prompt) if hasattr(classifier, "with_prompt") else classifier
        self.validator = validator or OutputValidator()

    def run(
        self,
        document: str,
        instruction: str,
        *,
        criteria: OutputCriteria | None = None,
        request_id: str | None = None,
        include_prompt: bool = False,
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
                text = redact_matches(text, result, NEUTRAL_REDACTION if self.config.sanitize_marker == "neutral" else REDACTION)

        prompt = (
            build_structural_prompt(instruction, text, variant=self.config.structural_variant, role=self.role)
            if self.config.structural
            else build_baseline_prompt(instruction, text, role=self.role)
        )
        canary = new_canary() if self.config.runtime_guard else None
        if canary:
            prompt = PromptBundle(system=prompt.system + canary_instruction(canary), user=prompt.user)
        preview = PromptPreview(system=prompt.system, user=prompt.user) if include_prompt else None
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
        guard = None
        if self.config.runtime_guard:
            t0 = time.perf_counter()
            report = check_output(output, document, instruction, canary)
            timings["runtime_guard"] = _ms(t0)
            action = "none"
            if report.flagged:
                action = "withheld" if self.config.runtime_guard_policy == "withhold" else "flagged_only"
                if action == "withheld" and blocked_by is None:
                    summary, blocked_by = None, "runtime_guard"
            guard = RuntimeGuardResult(flagged=report.flagged, policy_action=action,
                                       findings=[GuardFindingModel(check=f.check, detail=f.detail) for f in report.findings])
        return self._finish(
            request_id, started, timings, detections, calls,
            blocked_by=blocked_by, summary=summary, validation=validation, guard=guard, prompt=preview,
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
        guard: RuntimeGuardResult | None = None,
        prompt: PromptPreview | None = None,
    ) -> SummarizeResponse:
        warnings = [MOCK_WARNING] if self.llm.is_mock else []
        warnings += [f"{d.layer} layer {d.status}: {d.explanation}" for d in detections if d.status != "evaluated"]
        response = SummarizeResponse(
            request_id=request_id or uuid.uuid4().hex[:12],
            status="blocked" if blocked_by else "processed",
            blocked_by=blocked_by,
            enforcement_decision=_decision(blocked_by, detections, validation, guard),
            layers_run=[k for k in timings if k != "generation"],
            reached_model="generation" in timings,
            summary=summary,
            defenses=self.config,
            detections=detections,
            output_validation=validation,
            runtime_guard=guard,
            prompt=prompt,
            model=ModelInfo(provider=self.llm.provider, name=self.llm.model_name, is_mock=self.llm.is_mock),
            model_calls=calls,
            latency_ms=_ms(started),
            timings_ms=timings,
            warnings=warnings,
        )
        # Metadata only: never the document or the summary text.
        logger.info(
            "request_id=%s status=%s decision=%s blocked_by=%s config=%s layers=%s model=%s mock=%s calls=%d latency_ms=%.1f",
            response.request_id, response.status, response.enforcement_decision, blocked_by,
            self.config.name, ",".join(response.layers_run) or "-",
            self.llm.model_name, self.llm.is_mock, calls, response.latency_ms,
        )
        return response


def _decision(
    blocked_by: str | None, detections: list[DetectionResult], validation: ValidationResult | None,
    guard: RuntimeGuardResult | None = None,
) -> str:
    if blocked_by:
        return "block"
    flagged = any(d.policy_action in ("flagged_only", "sanitized", "ignored_error") for d in detections)
    reviewed = validation is not None and validation.outcome in ("indicator_matched", "needs_review")
    guarded = guard is not None and guard.flagged
    return "warn" if flagged or reviewed or guarded else "allow"


def _ms(since: float) -> float:
    return round((time.perf_counter() - since) * 1000, 3)
