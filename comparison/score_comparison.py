"""Score your latest comparison run: how many each model got right, how long it took, what it cost.

    uv run python score_comparison.py            # the latest run in results/
    uv run python score_comparison.py <file>     # a specific run

Prints the table, then writes the same results as a web page next to the run,
results/<run>.report.html, with every term explained in plain words.

Reads only the saved answers; it calls no model.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import report_html  # noqa: E402
import score_gateway  # noqa: E402


def latest_run(results: Path = HERE / "results") -> Path:
    runs = sorted(results.glob("test-*-gateway*-pass*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not runs:
        raise SystemExit("No comparison run found in results/. Run: uv run python run_comparison.py")
    return runs[-1]


def main() -> None:
    args = sys.argv[1:]
    path = Path(args[0]) if args else latest_run()
    print(f"Scoring {path.name}", flush=True)
    sys.argv = [sys.argv[0], str(path)]
    score_gateway.main()
    page = report_html.write(score_gateway.summarize(path), path).resolve()
    shown = page.relative_to(Path.cwd()) if page.is_relative_to(Path.cwd()) else page
    print(f"\nThe same results as a web page, with every term explained: {shown}", flush=True)
    print(f"Open it in your browser: {page.as_uri()}", flush=True)


if __name__ == "__main__":
    main()
