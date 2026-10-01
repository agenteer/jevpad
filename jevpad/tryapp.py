from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from jevpad.config import ROOT, Settings
from jevpad.jev import build_questions, judge, load_yaml


DEFAULT_QUESTIONS = ROOT / "recipes/try/questions.yaml"
MAX_BODY_BYTES = 16 * 1024
PAGE = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Local try page</title>
<style>
body{font:22px/1.45 system-ui;margin:0 auto;max-width:1050px;padding:2rem;background:#fafafa;color:#171717}
textarea,button,pre{font:inherit} textarea{box-sizing:border-box;width:100%;min-height:7rem;padding:.8rem}
#questions{min-height:31rem;font:18px/1.35 ui-monospace,monospace} button{padding:.7rem 1.3rem;margin:1rem 0}
pre{white-space:pre-wrap;background:white;border:1px solid #bbb;padding:1rem;overflow:auto} label{font-weight:700}
:root{color-scheme:light dark}
@media (prefers-color-scheme: dark){
body{background:#1b1b1d;color:#e8e8e6} pre{background:#242427;border-color:#55555a}
textarea{background:#242427;color:#e8e8e6;border:1px solid #6b6b70} button{background:#34343a;color:#e8e8e6;border:1px solid #7a7a80;border-radius:4px}
button:hover{background:#404047}
}
</style>
<h1>Local try page (jevpad) — not TypeSafe's playground</h1>
__MODE_BANNER__
<p>The API key stays in the Python process and is never sent to this page.</p>
<label for="message">Message</label><textarea id="message">I paid for the same order twice. Please return only the duplicate payment. Keep my subscription active.</textarea>
<label for="questions">Questions (editable YAML or JSON)</label><textarea id="questions">__QUESTIONS__</textarea>
<button id="run">Run</button><p id="status"></p><h2>Readable answer</h2><pre id="readable"></pre><h2>Raw JSON</h2><pre id="raw"></pre>
<script>
run.onclick=async()=>{status.textContent='Running…';readable.textContent='';raw.textContent='';
try{const r=await fetch('/api/try',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message:message.value,questions:questions.value})});
const d=await r.json();status.textContent=r.ok?'Complete':'Failed';readable.textContent=d.readable||d.error;raw.textContent=JSON.stringify(d.raw_response||d,null,2)}
catch(e){status.textContent='Failed';readable.textContent=String(e)}};
</script></html>"""


def question_text(path: Path = DEFAULT_QUESTIONS) -> str:
    return path.read_text(encoding="utf-8")


def page_html(injected_fault: str | None = None) -> str:
    mode = (
        f"<p><strong>INJECTED FAULT ({injected_fault.upper()}) · NO PROVIDER CALL</strong></p>"
        if injected_fault else "<p><strong>LIVE · each run makes a provider call</strong></p>"
    )
    return (PAGE.replace("__MODE_BANNER__", mode)
            .replace("__QUESTIONS__", question_text().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")))


def parse_question_text(text: str) -> dict[str, Any]:
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("questions must be a non-empty YAML or JSON object")
    for question_id, spec in parsed.items():
        if not isinstance(question_id, str) or not question_id.strip():
            raise ValueError("each question needs a non-empty string name")
        if not isinstance(spec, dict):
            raise ValueError(f"question {question_id!r} must be an object")
        kind = spec.get("type")
        if kind not in {"choice", "noul", "score"}:
            raise ValueError(f"question {question_id!r} needs type choice, noul, or score")
        if not isinstance(spec.get("instructions"), str) or not spec["instructions"].strip():
            raise ValueError(f"question {question_id!r} needs non-empty instructions")
        if kind == "choice" and (not isinstance(spec.get("options"), dict) or not spec["options"]):
            raise ValueError(f"choice question {question_id!r} needs a non-empty options object")
        if kind == "score" and not isinstance(spec.get("levels"), (dict, list)):
            raise ValueError(f"score question {question_id!r} needs levels")
    return parsed


def run_try(
    settings: Settings, message: str, definitions: dict[str, Any], injected_fault: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not message.strip():
        raise ValueError("message is empty; enter a non-blank message")
    questions = build_questions(definitions)
    return judge(settings=settings, recipe="try", example_id="first-try", origin="user",
                 state={"message": message}, questions=questions, mode="live", injected_fault=injected_fault)


def readable_result(message: str, definitions: dict[str, Any], answers: dict[str, Any], record: dict[str, Any]) -> str:
    lines = [f"State sent: message={message!r}", "", "Questions:"]
    for name, spec in definitions.items():
        lines.extend([f"- {name} ({spec['type'].title()}): {spec['instructions']}"])
        if spec.get("criteria"):
            lines.append(f"    criteria: {spec['criteria']}")
        values = spec.get("options") or spec.get("levels")
        if isinstance(values, dict):
            lines.extend(f"    {key}: {value}" for key, value in values.items())
        elif isinstance(values, list):
            lines.extend(f"    {index}: {value}" for index, value in enumerate(values))
    lines.extend(["", "Answers:"])
    for name, answer in answers.items():
        kind = answer.get("type")
        if kind == "choice":
            lines.append(f"- {name}: choice={answer.get('choice')} · confidence={answer.get('confidence')} · probabilities={answer.get('probabilities')}")
        elif kind == "noul":
            lines.append(f"- {name}: probability of yes={answer.get('noul')}")
        elif kind == "score":
            detail = f" · level probabilities={answer.get('probabilities')}" if answer.get("probabilities") is not None else ""
            lines.append(f"- {name}: score={answer.get('score')}{detail}")
    lines.extend(["", f"Answered model: {record.get('answered_model')}", f"Final provider: {record.get('final_provider')}",
                  f"Attempts: {record['retries']['attempt_count']} · statuses: {record['retries']['attempt_statuses']}",
                  f"Elapsed: {record.get('elapsed_ms')} ms"])
    return "\n".join(lines)


def make_handler(settings: Settings, injected_fault: str | None = None) -> type[BaseHTTPRequestHandler]:
    fault = injected_fault or settings.fault

    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, value: dict[str, Any]) -> None:
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path != "/":
                self.send_error(404)
                return
            body = page_html(fault).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/api/try":
                self.send_error(404)
                return
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            origin = self.headers.get("Origin")
            referer = self.headers.get("Referer")
            if origin:
                same_origin = origin == expected_origin
            elif referer:
                parsed = urlsplit(referer)
                try:
                    same_origin = (
                        parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
                        and parsed.port == self.server.server_port
                    )
                except ValueError:
                    same_origin = False
            else:
                same_origin = False
            if not same_origin:
                self._json(403, {"error": f"request must come from {expected_origin}"})
                return
            if self.headers.get_content_type() != "application/json":
                self._json(415, {"error": "Content-Type must be application/json"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0:
                    raise ValueError("Content-Length must be zero or greater")
                if length >= MAX_BODY_BYTES:
                    self._json(413, {"error": "request body must be under 16 KB"})
                    return
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                message = payload.get("message")
                question_source = payload.get("questions")
                if not isinstance(message, str):
                    raise ValueError("message must be a string")
                if not isinstance(question_source, str):
                    raise ValueError("questions must be a YAML or JSON string")
                definitions = parse_question_text(question_source)
                answers, record = run_try(settings, message, definitions, fault)
                if record["error_type"]:
                    self._json(502, {"error": f"{record['error_type']}: {record['error_message']}", "record": record})
                    return
                self._json(200, {"readable": readable_result(message, definitions, answers, record),
                                 "raw_response": record["raw_response"], "record": record})
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve(
    settings: Settings, host: str = "127.0.0.1", port: int = 8765, injected_fault: str | None = None,
) -> None:
    fault = injected_fault or settings.fault
    server = HTTPServer((host, port), make_handler(settings, fault))
    if fault:
        print(f"INJECTED FAULT ({fault.upper()}) · NO PROVIDER CALL")
    print(f"Local try page: http://{host}:{port} (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
