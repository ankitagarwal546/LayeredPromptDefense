"""Runtime settings (environment) and named defense configurations (experiments)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
MAX_DOCUMENT_CHARS = 50_000
MAX_INSTRUCTION_CHARS = 1_000

LLMProvider = Literal["mock", "openai_compatible", "anthropic"]
ClassifierProvider = Literal["none", "openai_compatible", "anthropic", "transformers"]


class Settings(BaseSettings):
    """Environment-driven settings. Secrets are SecretStr so they never print in reprs."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: LLMProvider = "mock"
    llm_model: str = ""
    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 512
    llm_timeout_s: float = 60.0

    classifier_provider: ClassifierProvider = "none"
    classifier_model: str = ""
    classifier_api_key: SecretStr | None = None
    classifier_base_url: str = ""
    # transformers provider only: label that means "injection", and the decision threshold
    classifier_positive_label: str = "INJECTION"
    classifier_threshold: float = 0.5

    data_dir: Path = REPO_ROOT / "data"
    results_dir: Path = REPO_ROOT / "results"

    default_model_mode: Literal["mock", "real"] = "mock"
    default_defense_preset: str = "E4"
    log_level: str = "INFO"


class DefenseConfig(BaseModel):
    """Which defense layers run, and what policy is applied when a layer fires.

    Detection (what a layer reports) and policy (what the pipeline does about it)
    are separate: see pipeline.py.
    """

    name: str = "custom"
    heuristic: bool = False
    heuristic_policy: Literal["block", "sanitize", "flag_only"] = "block"
    classifier: bool = False
    classifier_policy: Literal["block", "flag_only"] = "block"
    structural: bool = False
    structural_variant: Literal["v1", "v2", "v3"] = "v3"  # prompt wording; v1 = original (see docs/DEV_LOG.md)
    output_validation: bool = False
    output_validation_policy: Literal["withhold", "flag_only"] = "flag_only"
    # If a detector errors or is unavailable: False = continue (fail open), True = block.
    fail_closed_on_detector_error: bool = False

    def enabled_layers(self) -> list[str]:
        layers = ["heuristic", "classifier", "structural", "output_validation"]
        return [layer for layer in layers if getattr(self, layer)]


# E5 deliberately excludes output_validation: it needs ground-truth criteria that a deployed
# system would not have. See docs/EXPERIMENT_PROTOCOL.md ("Oracle leakage").
PRESETS: dict[str, DefenseConfig] = {
    "E0": DefenseConfig(name="E0"),
    "E1": DefenseConfig(name="E1", heuristic=True),
    "E1b": DefenseConfig(name="E1b", heuristic=True, heuristic_policy="sanitize"),
    "E2": DefenseConfig(name="E2", structural=True),
    "E3": DefenseConfig(name="E3", classifier=True),
    "E4": DefenseConfig(name="E4", heuristic=True, structural=True),
    "E5": DefenseConfig(name="E5", heuristic=True, classifier=True, structural=True),
}


def get_preset(name: str) -> DefenseConfig:
    try:
        return PRESETS[name].model_copy()
    except KeyError:
        raise ValueError(f"Unknown defense preset {name!r}; choose from {sorted(PRESETS)}") from None
