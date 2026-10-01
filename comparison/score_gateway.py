"""Score a both-via-gateway results file with score.py, relabelling the route lines.

    uv run python score_gateway.py results/test-<UTC>-gateway-pass3.jsonl [--repeat <pass4>] [--md out.md] [--json out.json]

score.py reads these files unchanged; its counts are correct as they are. It was written for the
Sep 24-25 setup, so this wrapper keeps score.py byte-identical and adjusts only what it reports:

- route labels: score.py hard-codes GPT-5.4-mini's route as "OpenAI API (direct)";
- the 95% range: score.py stores it rounded to three decimals, and the percentages shown are then
  rounded again (0.81462 -> 0.815 -> "82" instead of "81"); here it is kept unrounded, so it is
  rounded once, when shown;
- charges: the gateway-reported charge for GPT-5.4-mini is added (saved from the temperature-0
  runs on; earlier runs did not record it);
- settings: the run's route, prompt shape, reasoning effort and temperature, read from the run's
  own header, so the report can state the conditions it was run under.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import score

HERE = Path(__file__).resolve().parent
GATEWAY_RUNNERS = ("rerun_via_gateway.py", "rerun_gateway_temp0.py")
JEV_ROUTE = "Vercel AI Gateway, pinned to the TypeSafe provider"
LLM_ROUTE = "Vercel AI Gateway, pinned to the OpenAI provider"
NOT_RECORDED = "not recorded by this run"


def run_settings(header: dict, calls: list[dict]) -> dict:
    """The conditions of the run, from its header, plus how Jev's answers relate to its probabilities."""
    cfg = header.get("config") or {}
    jev, llm = cfg.get("jev") or {}, cfg.get("llm") or {}
    with_probs = [c for c in calls if c["model_key"] == "jev" and c.get("top3")]
    return {
        "jev_host": urlparse(jev.get("endpoint", "")).hostname,
        "llm_host": urlparse(llm.get("endpoint", "")).hostname,
        "jev_provider_only": jev.get("provider_only"),
        "llm_provider_only": llm.get("provider_only"),
        "llm_reasoning_effort": llm.get("reasoning_effort"),
        "llm_temperature": llm.get("temperature"),  # None: not sent, so the API default (1) applied
        "llm_system_message": bool(llm.get("system")),
        "labels": len(json.loads((HERE / "manifest.json").read_text())["labels"]),
        "concurrency": cfg.get("concurrency"),
        "alternating_order": "alternating" in (cfg.get("order") or ""),
        "jev_top_probability_choice": {
            "answers_with_probabilities": len(with_probs),
            "choice_is_top": sum(1 for c in with_probs if c.get("prediction") == c["top3"][0][0]),
        },
    }


def summarize(path: Path) -> dict:
    header, calls = score.load(path)
    s = score.summarize(path)
    for key in ("jev", "llm"):
        k = s["models"][key]["correct"]
        s["models"][key]["wilson95"] = list(score.wilson(k, s["examples"]))  # unrounded; rounded once when shown
    s["settings"] = run_settings(header, calls)
    s["runner"] = header.get("runner")
    if header.get("runner") in GATEWAY_RUNNERS:
        s["variant"] = header.get("variant")
        s["models"]["jev"]["route"] = JEV_ROUTE
        s["models"]["llm"]["route"] = LLM_ROUTE
        llm_calls = [c for c in calls if c["model_key"] == "llm"]
        charged = [c.get("gateway_cost") for c in llm_calls if c.get("gateway_cost") is not None]
        s["models"]["llm"]["charged_usd"] = round(sum(float(c) for c in charged), 6) if charged else None
        s["models"]["llm"]["charged_answers"] = len(charged)
        s["models"]["jev"]["charged_answers"] = sum(1 for c in calls if c["model_key"] == "jev" and c.get("cost") is not None)
    return s


def temperature_words(t) -> str:
    return "not set (the API default, 1)" if t is None else f"{t:g}"


def to_markdown(s: dict) -> str:
    md = score.to_markdown(s)
    if s.get("variant"):
        llm_charged = s["models"]["llm"]["charged_usd"]
        charged = NOT_RECORDED if llm_charged is None else f"\\${llm_charged:.4f} (gateway-reported)"
        md = md.replace("(Vercel promotion).", f"(gateway-reported). Actually charged for GPT-5.4-mini: {charged}.")
        st = s["settings"]
        md = (f"Variant: {s['variant']}\n\n"
              f"GPT-5.4-mini settings: reasoning effort {st['llm_reasoning_effort']}, "
              f"temperature {temperature_words(st['llm_temperature'])}.\n\n" + md)
    return md


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--repeat")
    ap.add_argument("--md")
    ap.add_argument("--json")
    args = ap.parse_args()
    s = summarize(Path(args.path))
    if args.repeat:
        s["run_to_run"] = score.agreement(Path(args.path), Path(args.repeat))
    md = to_markdown(s)
    if args.repeat:
        md += "\n\nRun-to-run (first vs repeat gateway pass, same settings): " + "; ".join(
            f"{k}: same answer on {v['same_answer']} of {v['compared']}" for k, v in s["run_to_run"].items())
    print(md)
    print("\nJev confidence sidebar (observed on this sample, not a calibration claim):", s["jev_confidence_sidebar"])
    print("Disagreements:", len(s["disagreements"]))
    if args.md:
        Path(args.md).write_text(md + "\n")
    if args.json:
        Path(args.json).write_text(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
