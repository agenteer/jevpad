from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jevpad.config import ROOT


RUNS_DIR = ROOT / "runs"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def code_revision() -> str:
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "companion"],
            cwd=ROOT.parent, capture_output=True, text=True, check=True,
        ).stdout.strip()
        if dirty:
            return "uncommitted"
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "uncommitted"


def append_record(record: dict[str, Any]) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    day = record["timestamp_utc"][:10]
    destination = RUNS_DIR / f"{day}.jsonl"
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return destination


def iter_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not RUNS_DIR.exists():
        return records
    for source in sorted(RUNS_DIR.glob("*.jsonl"), reverse=True):
        for line in source.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def find_run(run_id: str) -> dict[str, Any] | None:
    return next((record for record in iter_records() if record.get("run_id") == run_id), None)

