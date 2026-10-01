from __future__ import annotations

import csv
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from jevpad.config import ROOT


def input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _judgment_lines(judgments: Any) -> str:
    if not isinstance(judgments, dict) or not judgments:
        return "<span class='muted'>No model judgments</span>"
    lines = []
    for name, answer in judgments.items():
        label = html.escape(str(name).replace("_", " ").title())
        if not isinstance(answer, dict):
            lines.append(f"{label}: {html.escape(str(answer))}")
            continue
        kind = answer.get("type")
        if kind == "choice":
            choice = html.escape(str(answer.get("choice", "")))
            confidence = float(answer.get("confidence", 0))
            lines.append(f"{label}: <b>{choice}</b> <span class='muted'>({confidence:.2f})</span>")
        elif kind == "noul":
            lines.append(f"{label}: P(yes) {float(answer.get('noul', 0)):.2f}")
        elif kind == "score":
            legend = answer.get("legend") or {}
            numeric_levels = [int(key) for key in legend if str(key).lstrip("-").isdigit()]
            scale = f" of {max(numeric_levels)}" if numeric_levels else ""  # no legend (fixtures): state no scale
            lines.append(f"{label}: {float(answer.get('score', 0)):.2f}{scale}")
        else:
            lines.append(f"{label}: <span class='muted'>unavailable</span>")
    return "<br>".join(lines)


def _judgment_cell(row: dict[str, Any], judgments_only: bool) -> str:
    if judgments_only and row.get("error"):
        return f"<b>{html.escape(str(row.get('status') or 'FAILED'))}</b><br><span class='muted'>{html.escape(str(row['error']))}</span>"
    return _judgment_lines(row.get("judgments"))


def _cell(row: dict[str, Any], field: str, judgments_only: bool) -> str:
    if field == "judgments":
        return _judgment_cell(row, judgments_only)
    text = html.escape(str(row.get(field, "")))
    if field == "title" and row.get("url"):
        return f"<a href='{html.escape(str(row['url']), quote=True)}'>{text}</a>"
    return text


def _plumbing_table(rows: list[dict[str, Any]]) -> str:
    fields = [
        ("id", "ID"),
        ("input_hash", "Input hash"),
        ("answered_model", "Model"),
        ("final_provider", "Provider"),
        ("attempts", "Attempts"),
        ("attempt_statuses", "Statuses"),
        ("elapsed_ms", "Elapsed ms"),
        ("run_id", "Run ID"),
        ("error", "Error"),
    ]
    present = [(key, label) for key, label in fields if any(row.get(key) not in (None, "") for row in rows)]
    if not present:
        return ""
    headers = "".join(f"<th>{html.escape(label)}</th>" for _, label in present)
    body = "".join(
        "<tr>" + "".join(
            f"<td>{html.escape(json.dumps(row.get(key), ensure_ascii=False) if isinstance(row.get(key), (dict, list)) else str(row.get(key, '')))}</td>"
            for key, _ in present
        ) + "</tr>"
        for row in rows
    )
    return f"<details><summary>Run details</summary><div class='details-scroll'><table class='details'><thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table></div></details>"


JUDGMENTS_ONLY = "Judgments only; your code decides the action"


def _table(rows: list[dict[str, Any]], groups: list[tuple[str, list[str]]], judgments_only: bool) -> str:
    top = "".join(f"<th colspan='{len(names)}' class='g{index}'>{label}</th>" for index, (label, names) in enumerate(groups))
    sub = "".join(
        f"<th class='g{index}'>{html.escape(field.replace('_', ' '))}</th>"
        for index, (_, names) in enumerate(groups) for field in names
    )
    body = "".join(
        "<tr>" + "".join(
            f"<td class='g{index}{' nw' if field in ('profile', 'reader', 'action', 'label', 'rank', 'site_academy_path') else ''}'>"
            + _cell(row, field, judgments_only)
            + "</td>"
            for index, (_, names) in enumerate(groups) for field in names
        ) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{top}</tr><tr>{sub}</tr></thead><tbody>{body}</tbody></table>"


def export_rows(
    recipe: str, rows: list[dict[str, Any]], html_path: str | None = None,
    *, judgments_only: bool = False, title: str | None = None,
    sections: list[tuple[str, str]] | None = None, section_field: str = "reader",
) -> tuple[Path, Path, Path | None]:
    """Write out/<recipe>.csv and .json, and optionally an HTML report.

    judgments_only is for `jevpad run`: there is no policy, so the report has no code-action group.
    sections, as (id, text) pairs, splits the HTML into one table per value of `section_field`, in the rows' order;
    each section is headed by its text in quotes (a reader's own description), with the id as a small label.
    """
    destination = ROOT / "out"
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / f"{recipe}.json"
    csv_path = destination / f"{recipe}.csv"
    json_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fields = sorted({key for row in rows for key in row})
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    rendered: Path | None = None
    if html_path:
        rendered = Path(html_path)
        if not rendered.is_absolute():
            rendered = ROOT / rendered
        rendered.parent.mkdir(parents=True, exist_ok=True)
        groups = [
            ("Original input", ["id", "profile", "reader", "title", "original_text"]),
            ("Jev's answers", ["judgments"]),
            ("From the rules", ["action", "label", "rank", "result", "prose_model"]),
            # Reading recipe only: the Academy site's own path label, for comparison; Jev never sees it.
            ("The site's own label (not Jev's)", ["site_academy_path"]),
        ]
        if judgments_only:
            groups = [("Original input", ["id", "original_text"]), (JUDGMENTS_ONLY, ["judgments"])]
        if sections:
            # The section heading names the reader and the linked title identifies the item.
            groups = [(label, [field for field in names if field not in (section_field, "id")]) for label, names in groups]
        groups = [(label, [field for field in names if field in fields]) for label, names in groups]
        groups = [(label, names) for label, names in groups if names]
        modes = sorted({str(row["mode"]) for row in rows if row.get("mode")})
        badge = f" <span class='mode'>{html.escape(' / '.join(modes))}</span>" if modes else ""
        if sections:
            nav = " · ".join(f"<a href='#{html.escape(key, quote=True)}'>{html.escape(key)}</a>" for key, _ in sections)
            content = f"<p class='nav'>Readers: {nav}</p>" + "".join(
                f"<h2 id='{html.escape(key, quote=True)}'>“{html.escape(note)}”</h2><p class='note'>Reader: {html.escape(key)}</p>"
                + _table([row for row in rows if row.get(section_field) == key], groups, judgments_only)
                for key, note in sections
            )
        else:
            content = _table(rows, groups, judgments_only)
        plumbing = _plumbing_table(rows)
        rendered.write_text(
            "<!doctype html><meta charset='utf-8'><title>Jev export</title>"
            "<style>body{font:22px/1.35 system-ui;margin:1.5rem;color:#171717}table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #999;padding:.5rem .6rem;text-align:left;vertical-align:top;overflow-wrap:break-word}"
            "th{background:#eee}.g1{background:#f3f6fb}.g2{background:#f4faf2}.g3{background:#faf6ee}.nw{white-space:nowrap}"
            "thead tr:first-child th{font-size:24px}.muted{color:#555;font-size:.88em}"
            "h2{margin:2rem 0 .3rem;font-weight:600}.note{margin:0 0 .8rem;font-size:.8em;color:#555}.nav{font-size:18px}"
            ".mode{display:inline-block;background:#b45309;color:#fff;font-size:20px;padding:3px 12px;border-radius:12px;vertical-align:middle}"
            "details{margin-top:1rem;font-size:17px}summary{cursor:pointer;font-weight:700}.details-scroll{overflow-x:auto;margin-top:.6rem}"
            ".details{font-size:15px}.details th,.details td{padding:.35rem .45rem;white-space:nowrap}"
            ":root{color-scheme:light dark}"
            "@media (prefers-color-scheme: dark){body{background:#1b1b1d;color:#e8e8e6}th,td{border-color:#5c5c62}"
            "th{background:#2d2d31}.g1{background:#1f2735}.g2{background:#1f2b21}.g3{background:#2e291f}.muted,.note{color:#adadab}a{color:#8ab4f8}}</style>"
            f"<h1>{html.escape(title or recipe.title())}{badge}</h1>{content}{plumbing}",
            encoding="utf-8",
        )
    return csv_path, json_path, rendered
