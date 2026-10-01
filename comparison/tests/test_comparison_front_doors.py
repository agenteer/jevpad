"""run_comparison.py and score_comparison.py only choose a run number or a file; the frozen runner is unchanged."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_comparison  # noqa: E402
import score_comparison  # noqa: E402


def test_next_run_number_starts_at_three_and_counts_up(tmp_path: Path):
    assert run_comparison.next_run_number(tmp_path) == 3
    (tmp_path / "test-20260929T184146Z-gateway-pass3.jsonl").write_text("")
    (tmp_path / "test-20260930T000000Z-gateway-pass5.jsonl").write_text("")
    (tmp_path / "test-20260925T022043Z-pass1.jsonl").write_text("")  # the Sep 24-25 record is not counted
    assert run_comparison.next_run_number(tmp_path) == 6
    (tmp_path / "test-20260929T230000Z-gateway-temp0-pass6.jsonl").write_text("")  # temperature-0 runs count too
    assert run_comparison.next_run_number(tmp_path) == 7


def test_latest_run_picks_the_newest_gateway_file(tmp_path: Path):
    old = tmp_path / "test-a-gateway-pass3.jsonl"
    new = tmp_path / "test-b-gateway-pass4.jsonl"
    old.write_text(""); new.write_text("")
    os.utime(old, (time.time() - 100, time.time() - 100))
    assert score_comparison.latest_run(tmp_path) == new


def test_latest_run_includes_temperature_zero_runs(tmp_path: Path):
    old = tmp_path / "test-a-gateway-pass3.jsonl"
    new = tmp_path / "test-b-gateway-temp0-pass4.jsonl"
    old.write_text(""); new.write_text("")
    os.utime(old, (time.time() - 100, time.time() - 100))
    assert score_comparison.latest_run(tmp_path) == new


def test_frozen_runners_are_unchanged():
    import json, hashlib
    here = Path(run_comparison.__file__).resolve().parent
    for freeze in ("FROZEN-gateway.json", "FROZEN-gateway-temp0.json"):
        frozen = json.loads((here / freeze).read_text())
        for name, digest in frozen["sha256"].items():
            assert hashlib.sha256((here / name).read_bytes()).hexdigest() == digest, (freeze, name)


def test_run_comparison_starts_the_temperature_zero_runner():
    import rerun_gateway_temp0
    assert run_comparison.rerun_gateway_temp0 is rerun_gateway_temp0
