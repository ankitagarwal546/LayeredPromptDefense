import logging

import pytest

from injection_defense.config import PRESETS, DefenseConfig, Settings, get_preset
from injection_defense.logging_config import configure_logging


def test_defaults_are_safe_and_mock(settings):
    assert settings.llm_provider == "mock" and settings.classifier_provider == "none"
    assert settings.llm_api_key is None and settings.default_model_mode == "mock"


def test_env_vars_are_read_and_secrets_are_hidden(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "sk-very-secret")
    s = Settings(_env_file=None)
    assert s.llm_provider == "openai_compatible" and s.llm_api_key.get_secret_value() == "sk-very-secret"
    assert "sk-very-secret" not in repr(s) and "sk-very-secret" not in str(s.model_dump())


def test_invalid_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nonsense")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_presets_match_the_protocol_table():
    assert PRESETS["E0"].enabled_layers() == []
    assert PRESETS["E1"].enabled_layers() == ["heuristic"]
    assert PRESETS["E2"].enabled_layers() == ["structural"]
    assert PRESETS["E3"].enabled_layers() == ["classifier"]
    assert PRESETS["E4"].enabled_layers() == ["heuristic", "structural"]
    assert PRESETS["E5"].enabled_layers() == ["heuristic", "classifier", "structural"]  # no oracle L4
    assert PRESETS["E1b"].heuristic_policy == "sanitize"


def test_get_preset_returns_a_copy_and_rejects_unknown():
    a = get_preset("E1")
    a.heuristic = False
    assert PRESETS["E1"].heuristic is True
    with pytest.raises(ValueError, match="Unknown defense preset"):
        get_preset("E99")


def test_defense_config_rejects_unknown_policy_and_variant():
    with pytest.raises(ValueError):
        DefenseConfig(heuristic_policy="explode")
    with pytest.raises(ValueError):
        DefenseConfig(structural_variant="v9")


def test_configure_logging_is_idempotent_and_validates_level():
    configure_logging("DEBUG")
    configure_logging("INFO")
    logger = logging.getLogger("injection_defense")
    assert sum(getattr(h, "_injection_defense", False) for h in logger.handlers) == 1
    assert logger.level == logging.INFO
    with pytest.raises(ValueError):
        configure_logging("LOUD")
