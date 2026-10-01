"""Run the Jev vs GPT-5.4-mini comparison yourself.

Sends each of the 154 bank messages in manifest.json to both models through Vercel AI Gateway,
using the key already in the project's .env, and records every answer in results/. GPT-5.4-mini
runs at temperature 0, so it gives its most likely label, and Vercel's charge for every answer of
both models is saved. The settings were frozen before any run (FROZEN-gateway-temp0.json); the
frozen runner, rerun_gateway_temp0.py, checks them and refuses to run if they changed. This file
only picks the next run number and starts it.

    uv run python run_comparison.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rerun_gateway_temp0  # noqa: E402  (the frozen runner)

FIRST_GATEWAY_RUN = 3  # runs 1 and 2 are the Sep 24-25 record (GPT called directly at OpenAI)
GATEWAY_RUNS = "test-*-gateway*-pass*.jsonl"  # run 3 (gateway-pass3) and every later gateway run


def next_run_number(results: Path = HERE / "results") -> int:
    numbers = [int(m.group(1)) for p in results.glob(GATEWAY_RUNS)
               if (m := re.search(r"-gateway(?:-[a-z0-9]+)?-pass(\d+)\.jsonl$", p.name))]
    return max(numbers, default=FIRST_GATEWAY_RUN - 1) + 1


def main() -> None:
    number = next_run_number()
    print(f"Running the comparison (run {number}): 154 bank messages to Jev and GPT-5.4-mini through "
          "Vercel AI Gateway. About 3-7 minutes and about $0.07; progress every 20 messages.", flush=True)
    rerun_gateway_temp0.main(["--split", "test", "--pass-no", str(number)])
    print("Next: uv run python score_comparison.py", flush=True)


if __name__ == "__main__":
    main()
