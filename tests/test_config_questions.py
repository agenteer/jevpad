from pathlib import Path

from jevpad.config import load_settings
from jevpad.jev import build_questions, load_yaml


def test_settings_repr_never_contains_secret(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "super-secret-value")
    settings = load_settings(tmp_path / "missing.env")
    rendered = repr(settings)
    assert "super-secret-value" not in rendered
    assert settings.typesafe_key_present is True


def test_route_a_needs_only_typesafe_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "direct-key")
    monkeypatch.delenv("TYPESAFE_BASE_URL", raising=False)
    monkeypatch.delenv("TYPESAFE_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("JEV_MAX_RETRIES", raising=False)
    monkeypatch.delenv("JEV_RETRY_BUDGET_S", raising=False)
    settings = load_settings(tmp_path / "missing.env")
    assert settings.route == "A (direct TypeSafe)"
    assert settings.base_host == "api.typesafe.ai"
    assert settings.typesafe_model == "jev-latest"
    assert settings.jev_max_retries == 5
    assert settings.jev_retry_budget_s == 60


def test_questions_build_from_each_yaml():
    message_questions = build_questions(load_yaml(Path("recipes/messages/questions.yaml")))
    reading_questions = build_questions(load_yaml(Path("recipes/reading/preferences.yaml"))["questions"])
    assert set(message_questions) == {"team", "requests_refund", "expects_reply", "urgency"}
    assert set(reading_questions) == {"relevance", "opinion_or_overview"}
