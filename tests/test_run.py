"""Offline tests for `jevpad run`: a fake TypeSafe client stands in for the provider."""
import json
from dataclasses import replace
from pathlib import Path

import pytest
from rich.console import Console

import jevpad.cli as cli
import jevpad.evidence as evidence_module
import jevpad.export as export_module
import jevpad.jev as jev_module
import jevpad.runner as runner
from jevpad.config import Settings


EXAMPLE = str(Path(__file__).resolve().parents[1] / "examples/questions/support-triage.yaml")


def settings() -> Settings:
    return Settings(
        typesafe_key_present=True, typesafe_base_url="https://example.invalid", typesafe_model="jev-test",
        pin_provider=None, fault=None,
        jev_max_retries=0, jev_retry_budget_s=1, _typesafe_api_key="test-only-key",
    )


class FakeClient:
    """Answers like Jev would, keyed on the text, without any network."""

    sent: list[dict] = []

    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def system_one(self, *, state, questions, **kwargs):
        FakeClient.sent.append({"state": state, "questions": sorted(questions)})
        refund = 0.93 if "refund" in state["message"].lower() else 0.04
        answers = {
            "team": {"type": "choice", "choice": "billing", "confidence": 0.88,
                     "probabilities": {"billing": 0.88, "other": 0.12}},
            "requests_refund": {"type": "noul", "noul": refund},
            "urgency": {"type": "score", "score": 0.7, "probabilities": {"0": 0.4, "1": 0.5}},
        }
        body = {"model": "jev-test", "answers": answers}
        usage = type("Usage", (), {"model_dump": lambda self, **_: {"total_tokens": 42}})()
        raw = type("Raw", (), {"json": lambda self: body})()
        return type("Response", (), {"answers": answers, "model": "jev-test", "usage": usage,
                                     "raw_http_response": raw})()


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """Evidence and exports go to tmp_path; the real client is kept (only injected faults use it)."""
    monkeypatch.setattr(evidence_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(export_module, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "load_settings", settings)
    monkeypatch.setattr(runner, "console", Console(width=400))
    monkeypatch.setattr(cli, "console", Console(width=400))
    return tmp_path


@pytest.fixture
def fake_client(offline, monkeypatch):
    FakeClient.sent = []
    monkeypatch.setattr(jev_module, "TypeSafeClient", FakeClient)
    return offline


def run_cli(monkeypatch, *args: str) -> int:
    monkeypatch.setattr("sys.argv", ["jevpad", "run", *args])
    return cli.main()


def evidence(tmp_path: Path) -> list[dict]:
    return [json.loads(line) for source in (tmp_path / "runs").glob("*.jsonl")
            for line in source.read_text().splitlines()]


def test_run_text_shows_what_was_sent_and_the_answers(fake_client, monkeypatch, capsys):
    assert run_cli(monkeypatch, "--questions", EXAMPLE, "--text", "Please refund the duplicate [bold]charge[/bold].") == 0
    output = capsys.readouterr().out
    assert "=== LIVE · FRESH MODEL OUTPUT ===" in output
    assert "State sent: message='Please refund the duplicate [bold]charge[/bold].'" in output
    assert "criteria: Answer yes only for an explicit request to return money; honor negation." in output
    assert "- team: choice=billing" in output
    assert "- requests_refund: probability of yes=0.93" in output
    assert "Final provider: not exposed by SDK" in output
    assert "Judgments" not in output  # --text prints no summary table
    assert FakeClient.sent == [{"state": {"message": "Please refund the duplicate [bold]charge[/bold]."},
                                "questions": ["requests_refund", "team", "urgency"]}]
    [record] = evidence(fake_client)
    assert record["recipe"] == "run" and record["mode"] == "live" and record["error_type"] is None
    assert record["answers"]["requests_refund"]["noul"] == 0.93


def test_run_csv_column_exports_judgments_only_and_leaves_input_unchanged(fake_client, monkeypatch, capsys):
    offline = fake_client
    source = offline / "inbox.csv"
    source.write_text("id,body,channel\nA1,Please refund me.,email\nA2,How do exports work?,chat\n", encoding="utf-8")
    before = source.read_bytes()
    assert run_cli(monkeypatch, "--questions", EXAMPLE, "--input", str(source), "--column", "body",
                   "--export", "--html", "out/run.html") == 0
    output = capsys.readouterr().out
    assert source.read_bytes() == before
    assert "input 1 of 2 · A1" in output and "input 2 of 2 · A2" in output
    assert "judgments only; your code decides the action" in output
    assert "requests_refund: P(yes) 0.93" in output and "requests_refund: P(yes) 0.04" in output

    rows = json.loads((offline / "out/run-support-triage.json").read_text())
    assert [row["id"] for row in rows] == ["A1", "A2"]
    assert [row["original_text"] for row in rows] == ["Please refund me.", "How do exports work?"]
    assert all(row["status"] == "answered" and row["mode"] == "LIVE" for row in rows)
    assert "action" not in rows[0]
    header = (offline / "out/run-support-triage.csv").read_text().splitlines()[0].split(",")
    assert "judgments" in header and "action" not in header
    report = (offline / "out/run.html").read_text()
    assert "Judgments only; your code decides the action" in report
    assert "From the rules" not in report
    assert "jevpad run · support-triage.yaml" in report
    assert len(evidence(offline)) == 2


def test_run_injected_fault_is_a_failed_row_and_exit_status_1(offline, monkeypatch, capsys):
    source = offline / "inbox.csv"
    source.write_text("text\nfirst\nsecond\n", encoding="utf-8")
    assert run_cli(monkeypatch, "--questions", EXAMPLE, "--input", str(source),
                   "--inject-fault", "ratelimit", "--export", "--html", "out/run.html") == 1
    output = capsys.readouterr().out
    assert "=== INJECTED FAULT (RATELIMIT) · NO PROVIDER CALL ===" in output
    assert "FAILED — no action taken: TypeSafeRateLimitError" in output
    assert "FRESH MODEL OUTPUT" not in output
    [row] = json.loads((offline / "out/run-support-triage.json").read_text())
    assert row["id"] == "R01"
    assert row["status"] == "FAILED — no action taken"
    assert row["mode"] == "INJECTED FAULT (RATELIMIT)"
    assert row["judgments"] == {}
    assert row["attempts"] == 1 and row["attempt_statuses"] == [429]
    assert "FAILED — no action taken" in (offline / "out/run.html").read_text()
    [record] = evidence(offline)
    assert record["injected_fault"] == "ratelimit" and record["error_type"]


def test_run_rejects_a_bad_question_type_clearly(offline, monkeypatch, capsys, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("tone:\n  type: sentiment\n  instructions: How does `message` sound?\n", encoding="utf-8")
    assert run_cli(monkeypatch, "--questions", str(bad), "--text", "hello") == 2
    output = capsys.readouterr().out
    assert f"questions file {bad}: question 'tone' needs type choice, noul, or score" in output
    assert "Traceback" not in output
    assert not evidence(offline)


def test_run_fixture_mode_is_refused_without_fake_output(offline, monkeypatch, capsys):
    assert run_cli(monkeypatch, "--questions", EXAMPLE, "--text", "hello", "--mode", "fixture") == 2
    output = capsys.readouterr().out
    assert "no fixture mode" in output
    assert "FIXTURE · NOT MODEL OUTPUT" not in output and "Answers:" not in output
    assert not evidence(offline)


def test_run_names_the_columns_when_the_csv_column_is_missing(offline, monkeypatch, capsys):
    source = offline / "inbox.csv"
    source.write_text("id,body\nA1,hello\n", encoding="utf-8")
    assert run_cli(monkeypatch, "--questions", EXAMPLE, "--input", str(source)) == 2
    assert "has no column 'text'; its columns are: id, body" in capsys.readouterr().out
    assert not evidence(offline)


def test_run_refuses_to_export_over_its_own_input(offline, monkeypatch, capsys):
    (offline / "out").mkdir()
    source = offline / "out/run-support-triage.csv"
    source.write_text("text\nhello\n", encoding="utf-8")
    assert run_cli(monkeypatch, "--questions", EXAMPLE, "--input", str(source), "--export") == 2
    assert "would overwrite the input file" in capsys.readouterr().out
    assert source.read_text() == "text\nhello\n"


def test_run_without_a_key_explains_the_fix_before_any_call(offline, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_settings", lambda: replace(settings(), typesafe_key_present=False, _typesafe_api_key=None))
    assert run_cli(monkeypatch, "--questions", EXAMPLE, "--text", "hello") == 2
    output = capsys.readouterr().out
    assert "needs TYPESAFE_API_KEY" in output and "--inject-fault" in output
    assert "--mode fixture" not in output
    assert not evidence(offline)
