import json

import pytest

from jevpad.config import Settings
from jevpad.recipes import run_messages


def fault_settings() -> Settings:
    return Settings(
        typesafe_key_present=False, typesafe_base_url=None, typesafe_model="jev-latest",
        pin_provider=None, fault=None, jev_max_retries=0, jev_retry_budget_s=1,
    )


@pytest.mark.parametrize("kind", ["timeout", "ratelimit", "auth", "malformed", "server"])
def test_each_injected_fault_is_a_failed_record(kind, monkeypatch, tmp_path):
    import jevpad.evidence as evidence_module
    monkeypatch.setattr(evidence_module, "RUNS_DIR", tmp_path)
    rows, exit_code = run_messages(
        settings=fault_settings(), mode="live", text="hello", source=None,
        export=False, html=None, fault=kind,
    )
    record = json.loads(next(tmp_path.glob("*.jsonl")).read_text().strip())
    assert exit_code == 1
    assert rows[0]["action"] == "FAILED — no action taken"
    assert rows[0]["judgments"] == {}
    assert rows[0]["mode"] == f"INJECTED FAULT ({kind.upper()})"
    assert "LIVE" not in rows[0]["mode"]
    assert record["error_type"]
    assert record["injected_fault"] == kind
    assert record["retries"]["attempt_count"] >= 1
    assert len(record["retries"]["attempt_statuses"]) == record["retries"]["attempt_count"]


def test_missing_key_is_visible_failure_without_fallback(monkeypatch, tmp_path):
    import jevpad.evidence as evidence_module
    monkeypatch.setattr(evidence_module, "RUNS_DIR", tmp_path)
    rows, exit_code = run_messages(
        settings=fault_settings(), mode="live", text="hello", source=None,
        export=False, html=None, fault=None,
    )
    assert exit_code == 1
    assert rows[0]["mode"] == "LIVE"
    assert "TYPESAFE_API_KEY" in rows[0]["error"]
    assert rows[0]["action"] == "FAILED — no action taken"


def test_empty_text_is_rejected_before_evidence_call(monkeypatch, tmp_path):
    import jevpad.evidence as evidence_module
    monkeypatch.setattr(evidence_module, "RUNS_DIR", tmp_path)
    with pytest.raises(ValueError, match="empty"):
        run_messages(
            settings=fault_settings(), mode="live", text="   ", source=None,
            export=False, html=None, fault=None,
        )
    assert not list(tmp_path.glob("*.jsonl"))


def test_retry_attempts_and_statuses_are_counted(monkeypatch, tmp_path):
    import jevpad.evidence as evidence_module
    monkeypatch.setattr(evidence_module, "RUNS_DIR", tmp_path)
    configured = fault_settings()
    object.__setattr__(configured, "jev_max_retries", 2)
    object.__setattr__(configured, "jev_retry_budget_s", 5)
    rows, exit_code = run_messages(
        settings=configured, mode="live", text="hello", source=None,
        export=False, html=None, fault="ratelimit",
    )
    record = json.loads(next(tmp_path.glob("*.jsonl")).read_text().strip())
    assert exit_code == 1
    assert rows[0]["attempts"] == 3
    assert rows[0]["attempt_statuses"] == [429, 429, 429]
    assert record["retries"]["attempt_statuses"] == [429, 429, 429]
