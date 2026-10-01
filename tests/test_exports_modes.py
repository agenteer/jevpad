import json
from pathlib import Path

from jevpad.export import export_rows, input_hash
from jevpad.modes import banner


def test_export_preserves_original_text(monkeypatch, tmp_path: Path):
    import jevpad.export as export_module
    monkeypatch.setattr(export_module, "ROOT", tmp_path)
    original = "Keep punctuation — and whitespace.\nExactly."
    rows = [{"original_text": original, "input_hash": input_hash(original), "mode": "FIXTURE", "run_id": "abc"}]
    csv_path, json_path, _ = export_rows("test", rows)
    assert json.loads(json_path.read_text())[0]["original_text"] == original
    assert original in csv_path.read_text()


def test_html_export_prioritizes_input_judgments_and_action(monkeypatch, tmp_path: Path):
    import jevpad.export as export_module
    monkeypatch.setattr(export_module, "ROOT", tmp_path)
    rows = [{
        "id": "M01",
        "original_text": "Please keep <this> readable.",
        "input_hash": "abc123",
        "judgments": {
            "team": {"type": "choice", "choice": "billing", "confidence": 0.91},
            "expects_reply": {"type": "noul", "noul": 0.72},
            "urgency": {"type": "score", "score": 1.25, "legend": {"0": "low", "2": "high"}},
        },
        "action": "billing review queue",
        "mode": "LIVE",
        "run_id": "run-1",
        "answered_model": "jev-test",
        "final_provider": "test-provider",
        "attempts": 1,
        "attempt_statuses": [200],
        "elapsed_ms": 12.5,
    }]
    csv_path, json_path, html_path = export_rows("messages", rows, "out/report.html")
    rendered = html_path.read_text()

    assert rendered.index("Original input") < rendered.index("Jev's answers") < rendered.index("From the rules")
    assert "class='mode'>LIVE</span>" in rendered
    assert "Team: <b>billing</b>" in rendered
    assert "Expects Reply: P(yes) 0.72" in rendered
    assert "Urgency: 1.25 of 2" in rendered
    assert "&#x27;type&#x27;" not in rendered
    assert rendered.index("Run details") > rendered.index("</table>")
    assert "Input hash" in rendered and "Provider" in rendered and "Run ID" in rendered
    assert json.loads(json_path.read_text()) == rows
    assert set(csv_path.read_text().splitlines()[0].split(",")) == set(rows[0])


def test_html_export_shows_replay_fixture_and_fault_modes(monkeypatch, tmp_path: Path):
    import jevpad.export as export_module
    monkeypatch.setattr(export_module, "ROOT", tmp_path)
    rows = [
        {"original_text": mode, "judgments": {}, "action": "none", "mode": mode}
        for mode in ("REPLAY", "FIXTURE", "INJECTED FAULT (TIMEOUT)")
    ]
    _, _, html_path = export_rows("modes", rows, "modes.html")
    rendered = html_path.read_text()
    assert "FIXTURE / INJECTED FAULT (TIMEOUT) / REPLAY" in rendered


def test_mode_labels_are_unmistakable():
    assert "NOT MODEL OUTPUT" in banner("fixture")
    assert "FRESH MODEL OUTPUT" in banner("live")
    replay = banner("replay", original_timestamp="2026-09-24T00:00:00+00:00")
    assert "REPLAY" in replay and "ORIGINAL UTC" in replay
    fault = banner("live", injected_fault="ratelimit")
    assert fault == "=== INJECTED FAULT (RATELIMIT) · NO PROVIDER CALL ==="
    assert "LIVE" not in fault
    evidence = banner("evidence")
    assert evidence == "=== SAVED EVIDENCE · NO PROVIDER CALL ==="
    assert "REPLAY" not in evidence and "LIVE" not in evidence
    fault_replay = banner("replay", original_timestamp="2026-09-24T00:00:00+00:00", injected_fault="timeout")
    assert "INJECTED FAULT (TIMEOUT)" in fault_replay and "RECORDED LIVE OUTPUT" not in fault_replay


def test_row_mode_labels_name_injected_faults():
    from jevpad.modes import mode_label
    assert mode_label("live") == "LIVE"
    assert mode_label("fixture") == "FIXTURE"
    assert mode_label("live", "server") == "INJECTED FAULT (SERVER)"
    assert mode_label("fixture", "server") == "FIXTURE"


def test_html_export_follows_dark_color_scheme(monkeypatch, tmp_path: Path):
    import jevpad.export as export_module
    monkeypatch.setattr(export_module, "ROOT", tmp_path)
    _, _, html_path = export_rows("theme", [{"original_text": "x", "mode": "FIXTURE"}], "theme.html")
    rendered = html_path.read_text()
    assert "color-scheme:light dark" in rendered
    assert "@media (prefers-color-scheme: dark)" in rendered


def test_score_scale_is_shown_only_when_known():
    from jevpad.export import _judgment_lines

    with_legend = {"urgency": {"type": "score", "score": 1.35, "legend": {"0": "a", "1": "b", "2": "c"}}}
    without_legend = {"urgency": {"type": "score", "score": 1.35, "probabilities": {"1": 0.8}}}
    assert "1.35 of 2" in _judgment_lines(with_legend)
    assert "of 0" not in _judgment_lines(without_legend) and "1.35" in _judgment_lines(without_legend)
