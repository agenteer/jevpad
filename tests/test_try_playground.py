import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import replace
from http.server import HTTPServer

import jevpad.tryapp as tryapp
import jevpad.cli as cli
from jevpad.config import Settings


def settings() -> Settings:
    return Settings(
        typesafe_key_present=True, typesafe_base_url="https://example.invalid", typesafe_model="jev-test",
        pin_provider=None, fault=None,
        jev_max_retries=0, jev_retry_budget_s=1, _typesafe_api_key="test-only-key",
    )


def fake_judge(**kwargs):
    answers = {
        "team": {"type": "choice", "choice": "billing", "confidence": 0.9,
                 "probabilities": {"billing": 0.9, "other": 0.1}},
        "requests_refund": {"type": "noul", "noul": 0.95},
        "urgency": {"type": "score", "score": 1.2, "probabilities": {"1": 0.8}},
    }
    record = {
        "answered_model": "jev-test", "final_provider": "mock-provider", "elapsed_ms": 12.3,
        "retries": {"attempt_count": 2, "attempt_statuses": [429, 200]},
        "raw_response": {"model": "jev-test", "answers": answers},
        "error_type": None, "error_message": None, "run_id": "mock-run",
    }
    return answers, record


@contextmanager
def playground_server(monkeypatch, configured=None):
    monkeypatch.setattr(tryapp, "judge", fake_judge)
    server = HTTPServer(("127.0.0.1", 0), tryapp.make_handler(configured or settings()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def post(server, payload: bytes, headers: dict[str, str] | None = None):
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/api/try", data=payload,
        headers=headers or {}, method="POST",
    )
    try:
        response = urllib.request.urlopen(request, timeout=2)
        return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def test_try_teaching_output_uses_mocked_client(monkeypatch):
    monkeypatch.setattr(tryapp, "judge", fake_judge)
    definitions = tryapp.load_yaml(tryapp.DEFAULT_QUESTIONS)
    answers, record = tryapp.run_try(settings(), "Please refund the duplicate.", definitions)
    rendered = tryapp.readable_result("Please refund the duplicate.", definitions, answers, record)
    assert "State sent:" in rendered
    assert "Choice" in rendered and "probabilities=" in rendered
    assert "probability of yes=" in rendered
    # Everything sent to Jev is shown, including the Noul's criteria line.
    assert "criteria: Answer yes only for an explicit request to return money; honor negation." in rendered
    assert "Final provider: mock-provider" in rendered
    assert "statuses: [429, 200]" in rendered


def test_try_cli_uses_mocked_client(monkeypatch, capsys):
    monkeypatch.setattr(tryapp, "judge", fake_judge)
    monkeypatch.setattr(cli, "load_settings", settings)
    monkeypatch.setattr("sys.argv", ["jevpad", "try", "Please refund the duplicate."])
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert "Final provider: mock-provider" in output
    assert "probability of yes=" in output


def test_playground_page_and_payload_use_mocked_client(monkeypatch):
    html = tryapp.page_html()
    assert "Local try page (jevpad) — not TypeSafe's playground" in html
    assert "#questions{min-height:31rem" in html
    assert "test-only-key" not in html
    with playground_server(monkeypatch) as server:
        payload = json.dumps({"message": "A message", "questions": tryapp.question_text()}).encode()
        status, body = post(server, payload, {
            "Content-Type": "application/json",
            "Origin": f"http://127.0.0.1:{server.server_port}",
        })
    assert status == 200
    assert "mock-provider" in body
    assert "test-only-key" not in body


def test_playground_rejects_cross_origin(monkeypatch):
    with playground_server(monkeypatch) as server:
        status, body = post(server, b"{}", {
            "Content-Type": "application/json", "Origin": "https://hostile.example",
        })
    assert status == 403
    assert "must come from" in body


def test_playground_rejects_non_json_content_type(monkeypatch):
    with playground_server(monkeypatch) as server:
        status, body = post(server, b"{}", {
            "Content-Type": "text/plain", "Origin": f"http://127.0.0.1:{server.server_port}",
        })
    assert status == 415
    assert "application/json" in body


def test_playground_rejects_body_at_16_kb(monkeypatch):
    with playground_server(monkeypatch) as server:
        status, body = post(server, b"x" * tryapp.MAX_BODY_BYTES, {
            "Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}",
        })
    assert status == 413
    assert "under 16 KB" in body


def test_playground_rejects_invalid_question_shape_readably(monkeypatch):
    payload = json.dumps({"message": "hello", "questions": '{"missing_fields": {}}'}).encode()
    with playground_server(monkeypatch) as server:
        status, body = post(server, payload, {
            "Content-Type": "application/json", "Referer": f"http://127.0.0.1:{server.server_port}/",
        })
    assert status == 400
    assert "needs type choice, noul, or score" in body
    assert "Traceback" not in body


def test_injected_fault_labels_try_doctor_playground_and_recipe(monkeypatch, capsys):
    configured = replace(settings(), fault="timeout")
    monkeypatch.setattr(tryapp, "judge", fake_judge)
    monkeypatch.setattr(cli, "judge", fake_judge)
    monkeypatch.setattr(cli, "load_settings", lambda: configured)

    monkeypatch.setattr("sys.argv", ["jevpad", "try", "hello"])
    assert cli.main() == 0
    assert "INJECTED FAULT (TIMEOUT) · NO PROVIDER CALL" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["jevpad", "doctor", "--live"])
    assert cli.main() == 0
    assert "INJECTED FAULT (TIMEOUT) · NO PROVIDER CALL" in capsys.readouterr().out

    assert "INJECTED FAULT (TIMEOUT) · NO PROVIDER CALL" in tryapp.page_html("timeout")
    assert "LIVE" not in tryapp.page_html("timeout")

    seen = {}
    monkeypatch.setattr(cli, "run_messages", lambda **kwargs: (seen.update(kwargs) or ([], 1)))
    monkeypatch.setattr("sys.argv", ["jevpad", "messages", "--text", "hello"])
    assert cli.main() == 1
    assert seen["fault"] == "timeout"
    assert "INJECTED FAULT (TIMEOUT) · NO PROVIDER CALL" in capsys.readouterr().out


def test_doctor_explains_how_to_fix_a_missing_key(monkeypatch, capsys):
    configured = replace(settings(), typesafe_key_present=False, _typesafe_api_key=None)
    monkeypatch.setattr(cli, "load_settings", lambda: configured)
    monkeypatch.setattr("sys.argv", ["jevpad", "doctor"])
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert "No TypeSafe API key is configured" in output
    assert "Copy .env.example to .env" in output


def test_doctor_live_banner_only_after_a_successful_call(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_settings", settings)
    monkeypatch.setattr(cli, "judge", fake_judge)
    monkeypatch.setattr("sys.argv", ["jevpad", "doctor", "--live"])
    assert cli.main() == 0
    output = capsys.readouterr().out
    assert "LIVE CHECK · ONE TINY MODEL CALL" in output
    assert output.index("LIVE · FRESH MODEL OUTPUT") < output.index("Answered model")

    def failing_judge(**kwargs):
        answers, record = fake_judge(**kwargs)
        record.update(error_type="TypeSafeAuthenticationError", error_message="401 Cannot authenticate")
        return answers, record

    monkeypatch.setattr(cli, "judge", failing_judge)
    assert cli.main() == 1
    output = capsys.readouterr().out
    assert "FAILED: TypeSafeAuthenticationError" in output
    assert "FRESH MODEL OUTPUT" not in output


def test_playground_page_follows_dark_color_scheme():
    html = tryapp.page_html()
    assert "color-scheme:light dark" in html
    assert "@media (prefers-color-scheme: dark)" in html
