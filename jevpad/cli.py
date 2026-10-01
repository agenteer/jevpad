from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from jevpad.config import Settings, load_settings
from jevpad.evidence import find_run, iter_records
from jevpad.jev import build_questions, judge, load_yaml
from jevpad.modes import banner, mode_label
from jevpad.recipes import run_messages, run_reading
from jevpad.runner import NO_FIXTURES, run_questions
from jevpad.tryapp import DEFAULT_QUESTIONS, readable_result, run_try, serve


console = Console()


FAULT_HELP = "simulate this failure without calling the provider; the run is labeled INJECTED FAULT"
MODE_HELP = "live (default) calls the provider; fixture uses hand-written offline answers labeled FIXTURE"


def add_common(parser: argparse.ArgumentParser, html_example: str = "out/messages.html",
               mode_help: str = MODE_HELP) -> None:
    parser.add_argument("--mode", choices=("live", "fixture"), default="live", help=mode_help)
    parser.add_argument("--inject-fault", choices=("timeout", "ratelimit", "auth", "malformed", "server"), help=FAULT_HELP)
    parser.add_argument("--export", action="store_true", help="write CSV and JSON under out/")
    parser.add_argument("--html", metavar="PATH", help=f"also write a static HTML report, e.g. {html_example}")
    parser.add_argument("--pace", type=float, default=0, metavar="SECONDS", help="pause between batch requests (default: 0)")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="jevpad",
        description="A scratchpad for Jev questions: write them, run them, and see what Jev was asked and what it answered.",
        epilog="Start with `jevpad doctor`, then `jevpad try \"your message\"`. "
               "Use `jevpad run` for your own questions file.",
    )
    commands = root.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="check configuration without revealing secrets")
    doctor.add_argument("--live", action="store_true", help="make one tiny Jev call")
    doctor.add_argument("--inject-fault", choices=("timeout", "ratelimit", "auth", "malformed", "server"), help=FAULT_HELP)
    messages = commands.add_parser("messages", help="example application: triage support messages")
    add_common(messages)
    group = messages.add_mutually_exclusive_group(required=True)
    group.add_argument("--text")
    group.add_argument("--input")
    reading = commands.add_parser(
        "reading", help="example application: a reading list for each reader",
        description="Score every article for every reader and list every article for each reader, most relevant first. "
                    "Readers come from data/readers.csv (id,description); add a row to add yourself.",
    )
    add_common(reading, "out/reading.html")
    selection = reading.add_mutually_exclusive_group()
    selection.add_argument("--reader", action="append", metavar="ID",
                           help="only this reader; repeat it or give a comma list (default: every reader)")
    selection.add_argument("--compare", nargs=2, metavar=("READER_A", "READER_B"),
                           help="two readers side by side, with each article's rank change")
    reading.add_argument("--input", help="articles: CSV with id,title,description columns, or a folder of .md/.txt files "
                                         "(default: data/academy-articles.csv)")
    reading.add_argument("--readers", metavar="FILE.csv", help="readers: CSV with id,description columns "
                                                               "(default: data/readers.csv)")
    runs = commands.add_parser("runs", help="list saved calls")
    runs.add_argument("--limit", type=int, default=20)
    replay = commands.add_parser("replay", help="show a saved call again")
    replay.add_argument("run_id")
    first_try = commands.add_parser("try", help="send one text with the questions in recipes/try/questions.yaml")
    first_try.add_argument("message", help='the text to send, as state {"message": <text>}')
    first_try.add_argument("--questions", default=str(DEFAULT_QUESTIONS), metavar="FILE.yaml",
                           help="YAML file of questions to send (default: recipes/try/questions.yaml)")
    first_try.add_argument("--json", action="store_true", help="print the provider's raw JSON response body")
    first_try.add_argument("--inject-fault", choices=("timeout", "ratelimit", "auth", "malformed", "server"), help=FAULT_HELP)
    run = commands.add_parser(
        "run", help="send your own questions file for one text or each row of a CSV",
        description="Send your own questions to Jev for one text (--text) or each row of a CSV (--input). "
                    "Each input is sent as state {\"message\": <text>}, so your instructions can refer to `message`. "
                    "Nothing acts on the answers: you get judgments only, and your code decides the action.",
        epilog="Example: jevpad run --questions examples/questions/support-triage.yaml --input data/messages.csv --export",
    )
    run.add_argument("--questions", required=True, metavar="FILE.yaml",
                     help="YAML file of questions, same format as recipes/try/questions.yaml")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="one text to send")
    source.add_argument("--input", metavar="FILE.csv", help="CSV with a header row; one call per row (never modified)")
    run.add_argument("--column", default="text", help="CSV column holding the text (default: text)")
    run.add_argument("--json", action="store_true", help="print the provider's raw JSON response body for each input")
    add_common(run, "out/run.html", "live only (default); fixture is not available for your own questions")
    playground = commands.add_parser("playground", help="serve the try page on 127.0.0.1:8765")
    playground.add_argument("--inject-fault", choices=("timeout", "ratelimit", "auth", "malformed", "server"), help=FAULT_HELP)
    return root


def first_try(
    message: str, questions_path: str, raw_json: bool, settings: Settings, injected_fault: str | None,
) -> int:
    definitions = load_yaml(Path(questions_path))
    answers, record = run_try(settings, message, definitions, injected_fault)
    if record["error_type"]:
        console.print(f"FAILED: {record['error_type']}: {record['error_message']}")
        console.print(f"Attempts: {record['retries']['attempt_count']} · statuses: {record['retries']['attempt_statuses']}")
        return 1
    if raw_json:
        console.print_json(json.dumps(record["raw_response"], ensure_ascii=False))
    else:
        console.print(readable_result(message, definitions, answers, record))
    return 0


def doctor(live: bool, injected_fault: str | None = None) -> int:
    settings = load_settings()
    fault = injected_fault or settings.fault
    # The LIVE banner promises fresh model output, so doctor prints it only after a call succeeds.
    if not live:
        console.print("=== LIVE MODE CONFIGURED · CONFIG CHECK ONLY · NO MODEL OUTPUT ===")
    elif fault:
        console.print(banner("live", injected_fault=fault))
    else:
        console.print("=== LIVE CHECK · ONE TINY MODEL CALL ===")
    table = Table(title="Configuration (secrets never displayed)")
    table.add_column("Setting")
    table.add_column("Value")
    for key, value in (
        ("Route", settings.route), ("Base host", settings.base_host),
        ("Requested model", settings.typesafe_model), ("TypeSafe key present", "yes" if settings.typesafe_key_present else "no"),
        ("Pinned provider", settings.pin_provider or "none"),
        ("Max retries", str(settings.jev_max_retries)), ("Total retry budget", f"{settings.jev_retry_budget_s:g}s"),
    ):
        table.add_row(key, value)
    console.print(table)
    if not settings.typesafe_key_present:
        console.print("No TypeSafe API key is configured. Copy .env.example to .env and set one documented route before a live call.")
    if not live:
        console.print("Config-only check; no model call was made. Add --live for a tiny request.")
        return 0
    questions = build_questions({"ready": {"type": "noul", "instructions": "Is `text` a short greeting?"}})
    _, record = judge(settings=settings, recipe="doctor", example_id="doctor-live", origin="synthetic",
                      state={"text": "Hello."}, questions=questions, mode="live", injected_fault=fault)
    if record["error_type"]:
        console.print(f"FAILED: {record['error_type']}: {record['error_message']}")
        return 1
    if not fault:
        console.print(banner("live"))
    console.print(f"Answered model: {record['answered_model']} · provider: {record['final_provider']} · run: {record['run_id']}")
    return 0


def list_runs(limit: int) -> int:
    console.print(banner("evidence"))
    table = Table(title="Recent evidence calls")
    for column in ("Run ID", "UTC", "Mode", "Recipe", "Example", "Model", "Final provider", "Status"):
        table.add_column(column)
    newest_first = sorted(iter_records(), key=lambda record: record["timestamp_utc"], reverse=True)
    for record in newest_first[:limit]:
        table.add_row(record["run_id"], record["timestamp_utc"], mode_label(record["mode"], record.get("injected_fault")),
                      record["recipe"],
                      record["example_id"], str(record.get("answered_model") or record["requested_model"]),
                      str(record.get("final_provider") or "no answer"),
                      "FAILED" if record["error_type"] else "OK")
    console.print(table)
    return 0


def replay(run_id: str) -> int:
    record = find_run(run_id)
    if not record:
        console.print(f"No evidence record found for run_id {run_id}")
        return 1
    if record["mode"] != "live":
        console.print("Replay accepts saved live and injected-fault records only; fixture records remain labeled fixtures.")
        return 1
    console.print(banner("replay", original_timestamp=record["timestamp_utc"], injected_fault=record.get("injected_fault")))
    console.print_json(json.dumps(record, ensure_ascii=False))
    return 1 if record["error_type"] else 0


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "doctor":
            return doctor(args.live, args.inject_fault)
        if args.command == "runs":
            return list_runs(args.limit)
        if args.command == "replay":
            return replay(args.run_id)
        if args.command == "try":
            settings = load_settings()
            fault = args.inject_fault or settings.fault
            console.print(banner("live", injected_fault=fault))
            return first_try(args.message, args.questions, args.json, settings, fault)
        if args.command == "run":
            if args.mode != "live":
                raise ValueError(NO_FIXTURES)
            settings = load_settings()
            fault = args.inject_fault or settings.fault
            console.print(banner("live", injected_fault=fault))
            return run_questions(settings=settings, mode=args.mode, questions_path=args.questions, text=args.text,
                                 source=args.input, column=args.column, export=args.export, html=args.html,
                                 raw_json=args.json, fault=fault, pace=args.pace)[1]
        if args.command == "playground":
            settings = load_settings()
            fault = args.inject_fault or settings.fault
            serve(settings, injected_fault=fault)
            return 0
        settings = load_settings()
        fault = args.inject_fault or settings.fault
        console.print(banner(args.mode, injected_fault=fault))
        if args.command == "messages":
            return run_messages(settings=settings, mode=args.mode, text=args.text, source=args.input,
                                export=args.export, html=args.html, fault=fault, pace=args.pace)[1]
        if args.command == "reading":
            return run_reading(settings=settings, mode=args.mode, readers=args.compare or args.reader,
                               compare=bool(args.compare), source=args.input, readers_source=args.readers,
                               export=args.export, html=args.html, fault=fault, pace=args.pace)[1]
    except (ValueError, RuntimeError, OSError) as exc:
        console.print(f"FAILED: {exc}")
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
