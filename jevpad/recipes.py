from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from jevpad.config import ROOT, Settings
from jevpad.export import export_rows, input_hash
from jevpad.jev import build_questions, judge, load_yaml
from jevpad import modes
from jevpad.modes import mode_label
from recipes.messages.policy import proposed_action
from rich.text import Text

from recipes.reading.policy import relevance_label


console = Console()


def _progress(total: int):
    """A one-line 'Asking Jev: n of total' status that updates in place and disappears when the run ends."""
    status = console.status(f"Asking Jev: 0 of {total}")
    status.start()
    return status
def _pace(mode: str, seconds: float) -> None:
    """Avoid bursting the teaching batches; excluded from per-call elapsed time."""
    if seconds < 0:
        raise ValueError("--pace must be zero or greater")
    if mode == "live" and seconds:
        time.sleep(seconds)


def _evidence_fields(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "answered_model": record["answered_model"],
        "final_provider": record["final_provider"],
        "attempts": record["retries"]["attempt_count"],
        "attempt_statuses": record["retries"]["attempt_statuses"],
        "elapsed_ms": record["elapsed_ms"],
    }


def _reject_empty(value: str, label: str = "input") -> str:
    if not value.strip():
        raise ValueError(f"{label} is empty; provide non-blank text before calling a model")
    return value


def load_messages(text: str | None, source: str | None) -> list[dict[str, str]]:
    if text is not None:
        return [{"id": "USER-01", "text": _reject_empty(text), "origin": "user"}]
    if not source:
        raise ValueError("provide --text or --input")
    input_path = Path(source)
    if input_path.suffix.lower() == ".csv":
        with input_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if not {"id", "text"}.issubset(rows[0] if rows else {}):
            raise ValueError("message CSV must have id,text columns")
        return [{"id": row["id"], "text": _reject_empty(row["text"]), "origin": row.get("origin", "user")} for row in rows]
    if input_path.suffix.lower() == ".txt":
        lines = input_path.read_text(encoding="utf-8").splitlines()
        items = [{"id": f"L{index:02}", "text": _reject_empty(line), "origin": "user"} for index, line in enumerate(lines, 1) if line.strip()]
        if not items:
            raise ValueError("message input file contains no non-blank messages")
        return items
    raise ValueError("message input must be .csv (id,text) or .txt (one message per line)")


def run_messages(*, settings: Settings, mode: str, text: str | None, source: str | None,
                 export: bool, html: str | None, fault: str | None, pace: float = 0) -> tuple[list[dict[str, Any]], int]:
    definitions = load_yaml(ROOT / "recipes/messages/questions.yaml")
    questions = build_questions(definitions)
    rows: list[dict[str, Any]] = []
    failed = False
    items = list(load_messages(text, source))
    status = _progress(len(items))
    for index, item in enumerate(items):
        status.update(f"Asking Jev: {index + 1} of {len(items)} · {item['id']}")
        if index:
            _pace(mode, pace)
        answers, record = judge(
            settings=settings, recipe="messages", example_id=item["id"], origin=item["origin"],
            state={"message": item["text"]}, questions=questions, mode=mode, injected_fault=fault,
        )
        if record["error_type"]:
            failed = True
            action = "FAILED — no action taken"
            judgments: dict[str, Any] = {}
        else:
            action = proposed_action(answers)
            judgments = answers
        row = {
            "id": item["id"], "original_text": item["text"], "input_hash": input_hash(item["text"]),
            "judgments": judgments, "action": action, "mode": mode_label(mode, record["injected_fault"]), "run_id": record["run_id"],
            "error": f"{record['error_type']}: {record['error_message']}" if record["error_type"] else "",
            **_evidence_fields(record),
        }
        record["render"] = row
        rows.append(row)
        if fault:
            break
    status.stop()
    show_messages(rows)
    if export or html:
        paths = export_rows("messages", rows, html)
        console.print(f"Exports: {paths[0]} · {paths[1]}" + (f" · {paths[2]}" if paths[2] else ""))
    return rows, 1 if failed else 0


def show_messages(rows: list[dict[str, Any]]) -> None:
    table = Table(title="Message triage — the message | Jev's answers | next step from the rules")
    for column in ("Mode", "ID", "Original message", "Jev's answers", "Next step (rules)", "Provider / attempts", "Run ID"):
        table.add_column(column)
    for row in rows:
        judgments = row["judgments"]
        if judgments:
            rendered = (
                f"team={judgments['team']['choice']} (conf {judgments['team']['confidence']:.2f})\n"
                f"refund={judgments['requests_refund']['noul']:.2f} · reply={judgments['expects_reply']['noul']:.2f}\n"
                f"urgency={judgments['urgency']['score']:.2f} (conf {judgments['urgency']['confidence']:.2f})"
            )
        else:
            rendered = row["error"]
        table.add_row(row["mode"], row["id"], row["original_text"], rendered, row["action"],
                      f"{row['final_provider']} / {row['attempts']} {row['attempt_statuses']}", row["run_id"])
    console.print(table)


READING_DATA = ROOT / "data/academy-articles.csv"
READERS_DATA = ROOT / "data/readers.csv"
READING_QUESTIONS = ROOT / "recipes/reading/preferences.yaml"
SITE_PATH_LABEL = "Site's path (reference, not Jev)"
TOP_PICKS = 3


def load_reading(source: str | None) -> list[dict[str, str]]:
    """Articles to rank. Each has id, title and description; url and academy_path pass through when present."""
    input_path = Path(source) if source else READING_DATA
    if input_path.is_dir():
        rows = []
        for index, file in enumerate(sorted([*input_path.glob("*.md"), *input_path.glob("*.txt")]), 1):
            content = _reject_empty(file.read_text(encoding="utf-8"), file.name)
            rows.append({"id": f"F{index:02}", "title": file.stem, "description": content, "origin": "user"})
        if not rows:
            raise ValueError("reading input folder contains no non-blank .md/.txt files")
        return rows
    if input_path.suffix.lower() != ".csv":
        raise ValueError("reading input must be a CSV or a folder of .md/.txt files")
    with input_path.open(encoding="utf-8", newline="") as handle:
        data = list(csv.DictReader(handle))
    if not data or not {"id", "title", "description"}.issubset(data[0]):
        raise ValueError("reading CSV must have id,title,description columns")
    items = []
    for row in data:
        item = {"id": row["id"], "title": _reject_empty(row["title"]), "description": _reject_empty(row["description"]),
                "origin": row.get("origin", "user")}
        for extra in ("url", "academy_path"):
            if row.get(extra):
                item[extra] = row[extra]
        items.append(item)
    return items


def load_readers(source: str | None = None) -> list[dict[str, str]]:
    """Readers from a CSV with id,description columns: one row per person, in their own words."""
    path = Path(source) if source else READERS_DATA
    with path.open(encoding="utf-8", newline="") as handle:
        data = list(csv.DictReader(handle))
    if not data or not {"id", "description"}.issubset(data[0]):
        raise ValueError(f"readers file {path} must have id,description columns and at least one row")
    readers = [{"id": _reject_empty(row["id"], "reader id").strip(),
                "description": _reject_empty(row["description"], f"description for reader {row['id']}")} for row in data]
    ids = [reader["id"] for reader in readers]
    duplicates = sorted({reader_id for reader_id in ids if ids.count(reader_id) > 1})
    if duplicates:
        raise ValueError(f"readers file {path} repeats the id {', '.join(duplicates)}")
    return readers


def select_readers(readers: list[dict[str, str]], wanted: list[str] | None) -> list[dict[str, str]]:
    """All readers, or the named ones in the order given. `wanted` entries may be comma lists."""
    if not wanted:
        return readers
    by_id = {reader["id"]: reader for reader in readers}
    names = [name.strip() for entry in wanted for name in entry.split(",") if name.strip()]
    unknown = [name for name in names if name not in by_id]
    if unknown:
        raise ValueError(f"unknown reader {', '.join(unknown)}; readers in the file: {', '.join(by_id)}")
    return [by_id[name] for name in dict.fromkeys(names)]


def run_reading(*, settings: Settings, mode: str, readers: list[str] | None = None, compare: bool = False,
                source: str | None = None, readers_source: str | None = None, export: bool = False,
                html: str | None = None, fault: str | None = None, pace: float = 0) -> tuple[list[dict[str, Any]], int]:
    items = load_reading(source)
    selected = select_readers(load_readers(readers_source), readers)
    if compare and len(selected) != 2:
        raise ValueError("--compare needs two different readers")
    if mode == "fixture":
        missing = [reader["id"] for reader in selected if reader["id"] not in modes.READING_FIXTURES]
        if missing:
            raise ValueError(f"no fixture answers for reader {', '.join(missing)}; fixtures exist only for the readers "
                             "shipped in data/readers.csv. Run your own reader live (drop --mode fixture).")
    questions = build_questions(load_yaml(READING_QUESTIONS)["questions"])
    all_rows: list[dict[str, Any]] = []
    failed = False
    by_reader: dict[str, list[dict[str, Any]]] = {}
    request_index = 0
    status = _progress(len(selected) * len(items))
    for reader in selected:
        rows = []
        for item in items:
            if request_index:
                _pace(mode, pace)
            request_index += 1
            status.update(f"Asking Jev: {request_index} of {len(selected) * len(items)} · {reader['id']} · {item['title'][:48]}")
            # Per call, Jev sees the reader's own description and the article's title and description, nothing else.
            state = {"reader": reader["description"], "title": item["title"], "description": item["description"]}
            answers, record = judge(
                settings=settings, recipe="reading", example_id=item["id"], origin=item["origin"],
                state=state, questions=questions, mode=mode, profile=reader["id"], injected_fault=fault,
            )
            if record["error_type"]:
                failed = True
                score = overview = None
                label = "FAILED — no answer"
            else:
                score = answers["relevance"]["score"]
                overview = answers["opinion_or_overview"]["noul"]
                label = relevance_label(score)  # a label only; the article stays in the list either way
            row = {
                "reader": reader["id"], "id": item["id"], "title": item["title"], "original_text": item["description"],
                "input_hash": input_hash(item["description"]),
                "judgments": answers, "relevance": score, "label": label, "opinion_or_overview": overview,
                "mode": mode_label(mode, record["injected_fault"]), "run_id": record["run_id"],
                "error": f"{record['error_type']}: {record['error_message']}" if record["error_type"] else "",
                **_evidence_fields(record),
            }
            if "url" in item:
                row["url"] = item["url"]
            if "academy_path" in item:
                # The Academy site's own path label, carried for comparison only; Jev never sees it.
                row["site_academy_path"] = item["academy_path"]
            rows.append(row)
            if fault:
                break
        # Every article stays; the list is ordered by relevance alone (the opinion_or_overview answer is display-only).
        ranked = sorted(rows, key=lambda row: row["relevance"] if row["relevance"] is not None else -1, reverse=True)
        for rank, row in enumerate(ranked, 1):
            row["rank"] = rank
        by_reader[reader["id"]] = ranked
        all_rows.extend(ranked)
        if fault:
            break
    status.stop()
    descriptions = {reader["id"]: reader["description"] for reader in selected}
    if compare and len(by_reader) == 2:
        show_reading_compare(by_reader, descriptions)
    else:
        show_top_picks(by_reader, descriptions)
        if len(by_reader) == 1:
            [(reader_id, rows)] = by_reader.items()
            show_reader_list(reader_id, selected[0]["description"], rows)
    if export or html:
        sections = [(reader["id"], reader["description"]) for reader in selected if reader["id"] in by_reader]
        paths = export_rows("reading", all_rows, html, title="Reading list", sections=sections)
        console.print(f"Exports: {paths[0]} · {paths[1]}" + (f" · {paths[2]}" if paths[2] else ""))
    return all_rows, 1 if failed else 0


def _reader_cell(reader_id: str, description: str) -> Text:
    """The person first, in their own words; the short id is only a handle."""
    return Text(f"“{description}”\n") + Text(f"Reader: {reader_id}", style="dim")


def _pick(row: dict[str, Any]) -> str:
    return row["error"] or f"{row['relevance']:.2f} · {row['label']}"


def show_top_picks(by_reader: dict[str, list[dict[str, Any]]], descriptions: dict[str, str]) -> None:
    table = Table(title=f"Reading list — each reader's top {TOP_PICKS} articles by relevance (0–3)")
    for column in ("Mode", "Reader (in their own words)", f"Top {TOP_PICKS} · relevance · label"):
        table.add_column(column)
    for reader_id, rows in by_reader.items():
        errors = [row for row in rows if row["error"]]
        picks = errors[0]["error"] if errors else "\n".join(
            f"{row['rank']}. {row['title']} · {_pick(row)}" for row in rows[:TOP_PICKS]
        )
        table.add_row(rows[0]["mode"], _reader_cell(reader_id, descriptions[reader_id]), Text(picks))
    console.print(table)


def show_reader_list(reader_id: str, description: str, rows: list[dict[str, Any]]) -> None:
    table = Table(title=Text(f"Reading list for “{description}” (Reader: {reader_id})"))
    for column in ("Rank", "Article", "Jev's answers", "Label (from the rules)"):
        table.add_column(column)
    table.add_column(SITE_PATH_LABEL, max_width=13)
    table.add_column("Provider / attempts")
    for row in rows:
        judgments = row["judgments"]
        rendered = row["error"] if row["error"] else (
            f"relevance={row['relevance']:.2f} (conf {judgments['relevance']['confidence']:.2f})\n"
            f"opinion/overview={row['opinion_or_overview']:.2f}"
        )
        table.add_row(str(row["rank"]), Text(row["title"]), Text(rendered), row["label"], row.get("site_academy_path", "—"),
                      f"{row['final_provider']} / {row['attempts']} {row['attempt_statuses']}")
    console.print(table)


def show_reading_compare(by_reader: dict[str, list[dict[str, Any]]], descriptions: dict[str, str]) -> None:
    left, right = list(by_reader)
    left_map = {row["id"]: row for row in by_reader[left]}
    right_map = {row["id"]: row for row in by_reader[right]}
    table = Table(title="Reading list — same articles, two readers")
    table.add_column("Mode")
    table.add_column("Article")
    for reader_id in (left, right):
        table.add_column(_reader_cell(reader_id, descriptions[reader_id]) + Text("\nrank · relevance · label"))
    table.add_column("Rank change")
    table.add_column(SITE_PATH_LABEL, max_width=13)
    for item_id in sorted(left_map, key=lambda key: left_map[key]["rank"]):
        a, b = left_map[item_id], right_map[item_id]
        table.add_row(a["mode"], Text(a["title"]), f"{a['rank']} · {_pick(a)}", f"{b['rank']} · {_pick(b)}",
                      f"{a['rank'] - b['rank']:+d}", a.get("site_academy_path", "—"))
    console.print(table)
