"""Run Jev triage over a CSV of messages and print/save the results.

Usage:
    uv run python -m triage.run
    uv run python -m triage.run --input data/messages.csv --output out/results.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import TypeSafeClient

from .jev_client import ask_jev
from .rules import next_step

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "data" / "messages.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "out" / "results.csv"

# Column order matters for the printed table: message first, then Jev's raw
# answers, then the next_step the rules in rules.py computed from them.
FIELDNAMES = [
    "id",
    "text",
    "team",
    "team_confidence",
    "wants_refund",
    "urgency_score",
    "urgency_confidence",
    "next_step",
]


def load_messages(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def triage_one(message: dict, client) -> dict:
    answers = ask_jev(client, message["text"])
    return {
        "id": message["id"],
        "text": message["text"],
        "team": answers.team,
        "team_confidence": round(answers.team_confidence, 2),
        "wants_refund": round(answers.wants_refund, 2),
        "urgency_score": round(answers.urgency_score, 2),
        "urgency_confidence": round(answers.urgency_confidence, 2),
        "next_step": next_step(answers),
    }


def triage_all(messages: list[dict], client) -> list[dict]:
    return [triage_one(message, client) for message in messages]


def save_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows: list[dict]) -> None:
    text_width = 58
    jev_col = "-- Jev's answers " + "-" * 40
    cols = f"{'id':<4} {'text':<{text_width}} | {'team':<17} {'conf':<5} {'refund':<7} {'urg':<5} {'uconf':<6} | next_step"
    print(f"{'':<{4 + text_width + 1}} | {jev_col[:53]:<53} | rules")
    print(cols)
    print("-" * len(cols))
    for row in rows:
        text = row["text"]
        if len(text) > text_width:
            text = text[: text_width - 1] + "…"
        print(
            f"{row['id']:<4} {text:<{text_width}} | "
            f"{row['team']:<17} {row['team_confidence']:<5} {row['wants_refund']:<7} "
            f"{row['urgency_score']:<5} {row['urgency_confidence']:<6} | {row['next_step']}"
        )


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Triage customer messages with Jev.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    messages = load_messages(args.input)
    with TypeSafeClient() as client:
        rows = triage_all(messages, client)

    print_table(rows)
    save_csv(rows, args.output)
    print(f"\nSaved {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
