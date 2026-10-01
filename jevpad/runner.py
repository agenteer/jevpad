"""`jevpad run`: send your own questions file to Jev for one text or a CSV column.

There is no policy here, so nothing acts on the answers: each row shows the input and
Jev's judgments, and your own code decides what to do with them.
"""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from jevpad.config import ROOT, Settings
from jevpad.export import export_rows, input_hash
from jevpad.jev import build_questions, judge
from jevpad.modes import mode_label
from jevpad.tryapp import parse_question_text, readable_result


console = Console()
FAILED = "FAILED — no action taken"
STATE_KEY = "message"
NO_FIXTURES = (
    "jevpad run has no fixture mode: fixtures are hand-written answers for the built-in examples, "
    "and there are none for your own questions. Run it live, or add --inject-fault KIND to see the "
    "failure path offline."
)


def load_question_file(path: str) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"questions file not found: {path}")
    try:
        return parse_question_text(source.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"questions file {path}: {exc}") from None
    except Exception as exc:  # YAML syntax errors
        raise ValueError(f"questions file {path} is not valid YAML: {exc}") from None


def load_inputs(text: str | None, source: str | None, column: str) -> list[dict[str, str]]:
    if text is not None:
        if not text.strip():
            raise ValueError("--text is empty; provide non-blank text before calling a model")
        return [{"id": "TEXT-01", "text": text}]
    if not source:
        raise ValueError("provide --text or --input")
    input_path = Path(source)
    if input_path.suffix.lower() != ".csv":
        raise ValueError("--input must be a .csv file with a header row")
    if not input_path.is_file():
        raise ValueError(f"input file not found: {source}")
    with input_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        columns = reader.fieldnames or []
    if column not in columns:
        raise ValueError(f"{source} has no column {column!r}; its columns are: {', '.join(columns) or 'none'}. "
                         "Choose one with --column.")
    if not rows:
        raise ValueError(f"{source} has a header but no rows")
    items = []
    for number, row in enumerate(rows, 1):
        value = row.get(column) or ""
        if not value.strip():
            raise ValueError(f"{source} row {number}: column {column!r} is empty")
        items.append({"id": (row.get("id") or "").strip() or f"R{number:02}", "text": value})
    return items


def _sent_block(text: str, definitions: dict[str, Any], record: dict[str, Any]) -> str:
    """The state and questions part of readable_result, for a call that returned no answers."""
    return readable_result(text, definitions, {}, record).split("\n\nAnswers:")[0]


def _judgment_summary(answers: dict[str, Any]) -> str:
    parts = []
    for name, answer in answers.items():
        kind = answer.get("type")
        if kind == "choice":
            parts.append(f"{name}={answer.get('choice')} (conf {float(answer.get('confidence', 0)):.2f})")
        elif kind == "noul":
            parts.append(f"{name}: P(yes) {float(answer.get('noul', 0)):.2f}")
        elif kind == "score":
            parts.append(f"{name}={float(answer.get('score', 0)):.2f}")
        else:
            parts.append(f"{name}: unavailable")
    return "\n".join(parts)


def _export_name(questions_path: str) -> str:
    return f"run-{Path(questions_path).stem}"


def run_questions(
    *, settings: Settings, mode: str, questions_path: str, text: str | None, source: str | None,
    column: str = "text", export: bool = False, html: str | None = None, raw_json: bool = False,
    fault: str | None = None, pace: float = 0,
) -> tuple[list[dict[str, Any]], int]:
    if mode != "live":
        raise ValueError(NO_FIXTURES)
    if pace < 0:
        raise ValueError("--pace must be zero or greater")
    if not fault and not settings.typesafe_key_present:
        raise ValueError("Live mode needs TYPESAFE_API_KEY. Copy .env.example to .env and configure route A or B "
                         "(see README), or add --inject-fault KIND to try the failure path offline.")
    definitions = load_question_file(questions_path)
    questions = build_questions(definitions)
    items = load_inputs(text, source, column)
    name = _export_name(questions_path)
    if source and (export or html):
        protected = Path(source).resolve()
        planned = [ROOT / "out" / f"{name}.csv", ROOT / "out" / f"{name}.json"]
        if html:
            planned.append(Path(html) if Path(html).is_absolute() else ROOT / html)
        if any(path.resolve() == protected for path in planned):
            raise ValueError(f"an export would overwrite the input file {source}; move the input or choose another --html path")

    rows: list[dict[str, Any]] = []
    failed = False
    for index, item in enumerate(items):
        if index and pace:
            time.sleep(pace)
        answers, record = judge(
            settings=settings, recipe="run", example_id=item["id"], origin="user",
            state={STATE_KEY: item["text"]}, questions=questions, mode=mode, injected_fault=fault,
        )
        label = mode_label(mode, record["injected_fault"])
        console.rule(Text(f"{label} · input {index + 1} of {len(items)} · {item['id']}"), style="dim")
        if record["error_type"]:
            failed = True
            error = f"{record['error_type']}: {record['error_message']}"
            console.print(_sent_block(item["text"], definitions, record), markup=False, highlight=False)
            console.print(f"\n{FAILED}: {error}", markup=False, highlight=False)
            console.print(f"Attempts: {record['retries']['attempt_count']} · statuses: "
                          f"{record['retries']['attempt_statuses']}", markup=False, highlight=False)
        elif raw_json:
            console.print_json(json.dumps(record["raw_response"], ensure_ascii=False))
        else:
            console.print(readable_result(item["text"], definitions, answers, record), markup=False, highlight=False)
        rows.append({
            "id": item["id"], "original_text": item["text"], "input_hash": input_hash(item["text"]),
            "judgments": {} if record["error_type"] else answers,
            "status": FAILED if record["error_type"] else "answered",
            "mode": label, "run_id": record["run_id"],
            "error": f"{record['error_type']}: {record['error_message']}" if record["error_type"] else "",
            "answered_model": record["answered_model"], "final_provider": record["final_provider"],
            "attempts": record["retries"]["attempt_count"],
            "attempt_statuses": record["retries"]["attempt_statuses"],
            "elapsed_ms": record["elapsed_ms"],
        })
        if fault:
            break
    if source:
        show_table(rows)
    if export or html:
        paths = export_rows(name, rows, html, judgments_only=True, title=f"jevpad run · {Path(questions_path).name}")
        console.print(f"Exports: {paths[0]} · {paths[1]}" + (f" · {paths[2]}" if paths[2] else ""), markup=False)
    return rows, 1 if failed else 0


def show_table(rows: list[dict[str, Any]]) -> None:
    table = Table(title="jevpad run — input | judgments only; your code decides the action")
    for column in ("Mode", "ID", "Input text", "Judgments", "Provider / attempts", "Run ID"):
        table.add_column(column)
    for row in rows:
        judgments = f"{FAILED}\n{row['error']}" if row["error"] else _judgment_summary(row["judgments"])
        cells = (row["mode"], row["id"], row["original_text"], judgments,
                 f"{row['final_provider']} / {row['attempts']} {row['attempt_statuses']}", row["run_id"])
        table.add_row(*(Text(str(cell)) for cell in cells))
    console.print(table)
