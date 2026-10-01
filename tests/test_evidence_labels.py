import io
import json

from rich.console import Console

import jevpad.cli as cli
import jevpad.evidence as evidence_module


def _record(run_id: str, mode: str, timestamp: str, fault: str | None = None) -> dict:
    failed = fault is not None
    return {
        "run_id": run_id, "timestamp_utc": timestamp, "mode": mode, "recipe": "messages", "example_id": "M01",
        "answered_model": None if failed else ("hand-written-fixture" if mode == "fixture" else "typesafe-ai/jev"),
        "requested_model": "typesafe-ai/jev" if mode == "live" else "none",
        "final_provider": "no answer" if failed else "typesafe-ai",
        "error_type": "TypeSafeRateLimitError" if failed else None,
        "error_message": "controlled injected HTTP 429" if failed else None,
        "injected_fault": fault,
    }


def _write(directory, day: str, records: list[dict]) -> None:
    (directory / f"{day}.jsonl").write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def _capture(monkeypatch) -> io.StringIO:
    output = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, width=400))
    return output


def _line_with(text: str, run_id: str) -> str:
    return next(line for line in text.splitlines() if run_id in line)


def test_runs_list_is_not_labeled_replay_and_names_each_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(evidence_module, "RUNS_DIR", tmp_path)
    _write(tmp_path, "2026-09-25", [
        _record("live00000001", "live", "2026-09-25T02:00:00+00:00"),
        _record("fixture00001", "fixture", "2026-09-25T02:01:00+00:00"),
        _record("fault0000001", "live", "2026-09-25T02:02:00+00:00", fault="ratelimit"),
    ])
    output = _capture(monkeypatch)
    assert cli.list_runs(20) == 0
    text = output.getvalue()
    assert "SAVED EVIDENCE · NO PROVIDER CALL" in text
    assert "REPLAY" not in text and "RECORDED LIVE OUTPUT" not in text
    assert "LIVE" in _line_with(text, "live00000001")
    assert "FIXTURE" in _line_with(text, "fixture00001")
    fault_row = _line_with(text, "fault0000001")
    assert "INJECTED FAULT (RATELIMIT)" in fault_row
    assert "LIVE" not in fault_row


def test_runs_list_shows_newest_records_first_across_days(monkeypatch, tmp_path):
    monkeypatch.setattr(evidence_module, "RUNS_DIR", tmp_path)
    _write(tmp_path, "2026-09-24", [_record("older0000001", "live", "2026-09-24T12:00:00+00:00")])
    _write(tmp_path, "2026-09-25", [_record("newer0000001", "live", "2026-09-25T12:00:00+00:00")])
    output = _capture(monkeypatch)
    cli.list_runs(1)
    text = output.getvalue()
    assert "newer0000001" in text
    assert "older0000001" not in text


def test_replay_labels_injected_fault_records_as_faults(monkeypatch, tmp_path):
    monkeypatch.setattr(evidence_module, "RUNS_DIR", tmp_path)
    _write(tmp_path, "2026-09-25", [_record("fault0000001", "live", "2026-09-25T02:02:00+00:00", fault="ratelimit")])
    output = _capture(monkeypatch)
    assert cli.replay("fault0000001") == 1
    text = output.getvalue()
    assert "REPLAY · RECORDED INJECTED FAULT (RATELIMIT) · NO PROVIDER CALL" in text
    assert "RECORDED LIVE OUTPUT" not in text


def test_replay_shows_live_records_and_refuses_fixtures(monkeypatch, tmp_path):
    monkeypatch.setattr(evidence_module, "RUNS_DIR", tmp_path)
    _write(tmp_path, "2026-09-25", [
        _record("live00000001", "live", "2026-09-25T02:00:00+00:00"),
        _record("fixture00001", "fixture", "2026-09-25T02:01:00+00:00"),
    ])
    output = _capture(monkeypatch)
    assert cli.replay("live00000001") == 0
    assert "REPLAY · RECORDED LIVE OUTPUT · ORIGINAL UTC 2026-09-25T02:00:00+00:00" in output.getvalue()
    output = _capture(monkeypatch)
    assert cli.replay("fixture00001") == 1
    assert "fixture records remain labeled fixtures" in output.getvalue()
    assert "RECORDED LIVE OUTPUT" not in output.getvalue()
