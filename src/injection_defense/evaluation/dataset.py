"""JSONL evaluation-case schema and loader. Extend the dataset by adding lines, not code."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from injection_defense.schemas import OutputCriteria


class DatasetError(ValueError):
    """Raised with every problem found, each tagged with its line number."""


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    document_text: str = Field(min_length=1)
    is_attack: bool
    attack_family: str | None = None
    template_id: str | None = None  # near-duplicate group; hold out whole templates, not rows
    attack_goal: str | None = None
    expected_behavior: str = ""
    success_indicators: list[str] = Field(default_factory=list)  # regexes
    forbidden_output_patterns: list[str] = Field(default_factory=list)  # regexes
    expected_summary_keywords: list[str] = Field(default_factory=list)  # benign utility check
    provenance: str = Field(min_length=1)
    notes: str = ""

    @field_validator("success_indicators", "forbidden_output_patterns")
    @classmethod
    def _valid_regexes(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc
        return patterns

    @model_validator(mode="after")
    def _consistent_labels(self) -> EvalCase:
        if self.is_attack and not self.attack_family:
            raise ValueError("attack cases need attack_family")
        if not self.is_attack and (self.attack_family or self.success_indicators or self.forbidden_output_patterns):
            raise ValueError("benign cases must not set attack_family or attack criteria")
        return self

    def criteria(self) -> OutputCriteria:
        return OutputCriteria(
            success_indicators=self.success_indicators,
            forbidden_output_patterns=self.forbidden_output_patterns,
        )


def load_cases(path: str | Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    problems: list[str] = []
    seen: dict[str, int] = {}
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = EvalCase.model_validate(json.loads(line))
        except json.JSONDecodeError as exc:
            problems.append(f"line {number}: invalid JSON ({exc.msg})")
            continue
        except ValidationError as exc:
            detail = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'record'}: {e['msg']}" for e in exc.errors())
            problems.append(f"line {number}: {detail}")
            continue
        if case.case_id in seen:
            problems.append(f"line {number}: duplicate case_id {case.case_id!r} (first on line {seen[case.case_id]})")
            continue
        seen[case.case_id] = number
        cases.append(case)
    if problems:
        raise DatasetError(f"{path}: {len(problems)} problem(s)\n" + "\n".join(problems))
    return cases


def dataset_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
