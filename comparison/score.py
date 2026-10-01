"""Score one results file, following ANALYSIS_PLAN.md.

    uv run python score.py results/<file>.jsonl [--md out.md] [--json out.json]
    uv run python score.py results/<pass1>.jsonl --repeat results/<pass2>.jsonl

Accuracy denominator = every example in the run; unanswered counts as wrong.
p95 = nearest rank over the n values shown. Cost = catalog cost (usage x list price
from config.json) for both models; the amount actually charged is shown separately.
"""
import argparse
import json
import math
import statistics
from pathlib import Path


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(p / 100 * len(ordered))) - 1]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def exact_mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def load(path: Path) -> tuple[dict, list[dict]]:
    lines = [json.loads(l) for l in path.read_text().splitlines()]
    header = next(l for l in lines if l["type"] == "run_header")
    return header, [l for l in lines if l["type"] == "call"]


CURRENT_CONFIG = json.loads((Path(__file__).parent / "config.json").read_text())


def catalog_cost(call: dict, key: str, cfg: dict) -> float:
    usage = call.get("usage") or {}
    if "catalog_price_per_million" not in cfg.get("jev", {}) or "price_per_million" not in cfg.get("llm", {}):
        cfg = CURRENT_CONFIG  # dev runs predate the price fields; prices are unchanged
    if key == "jev":
        price = cfg["jev"]["catalog_price_per_million"]
        return (usage.get("input_tokens") or 0) * price["input"] / 1e6
    price = cfg["llm"]["price_per_million"]
    return ((usage.get("prompt_tokens") or 0) * price["input"]
            + (usage.get("completion_tokens") or 0) * price["output"]) / 1e6


def summarize(path: Path) -> dict:
    header, calls = load(path)
    cfg = header["config"]
    examples = sorted({c["example_id"] for c in calls})
    n = len(examples)
    out = {"file": path.name, "split": header["split"], "pass": header.get("pass"),
           "started_utc": header["started_utc"], "examples": n, "models": {}}
    by = {}
    for key in ("jev", "llm"):
        cs = [c for c in calls if c["model_key"] == key]
        by[key] = {c["example_id"]: c for c in cs}
        answered = [c for c in cs if c.get("http_status") == 200 and c.get("valid")]
        served = [c["elapsed_ms"] for c in answered]
        usable = [c.get("total_ms") or c["elapsed_ms"] for c in answered]
        prov = [c["provider_ms"] for c in answered if c.get("provider_ms") is not None]
        correct = sum(1 for c in cs if c.get("correct"))
        attempts = [a for c in cs for a in (c.get("attempt_log") or [])]
        refused = [a for a in attempts if a.get("status") == 429]
        lo, hi = wilson(correct, n)
        out["models"][key] = {
            "answered_model": next((c.get("answered_model") for c in answered), None),
            "route": "Vercel AI Gateway (TypeSafe provider)" if key == "jev" else "OpenAI API (direct)",
            "correct": correct, "total": n, "wilson95": [round(lo, 3), round(hi, 3)],
            "answered": len(answered), "correct_of_answered": f"{correct}/{len(answered)}",
            "never_answered": [c["example_id"] for c in cs if not (c.get("http_status") == 200 and c.get("valid"))],
            "invalid_answers": sum(1 for c in cs if c.get("http_status") == 200 and not c.get("valid")),
            "finish_reason_length": sum(1 for c in cs if c.get("finish_reason") == "length"),
            "served_ms": {"n": len(served), "median": statistics.median(served) if served else None,
                          "p95": pct(served, 95), "worst": max(served) if served else None},
            "usable_ms": {"n": len(usable), "median": statistics.median(usable) if usable else None,
                          "p95": pct(usable, 95), "worst": max(usable) if usable else None},
            "provider_ms_median": statistics.median(prov) if prov else None,
            "availability": {
                "attempts_total": len(attempts),
                "attempts_refused_429": len(refused),
                "attempts_timeout_or_connection": sum(1 for a in attempts if a.get("status") is None),
                "examples_needing_retry": sum(1 for c in cs if (c.get("attempts") or 1) > 1),
                "retry_after_sent": any(a.get("retry_after") for a in attempts),
                "refusal_message": next((a["error"] for a in refused if a.get("error")), None),
                "slowest_refusal_ms": max((a.get("elapsed_ms") or 0 for a in refused), default=None),
            },
            "catalog_cost_usd": round(sum(catalog_cost(c, key, cfg) for c in cs), 6),
            "charged_usd": round(sum(float(c.get("cost") or 0) for c in cs), 6) if key == "jev" else None,
            "sum_usable_s": round(sum(c.get("total_ms") or c.get("elapsed_ms") or 0 for c in cs) / 1000, 1),
        }

    def paired(ids):
        b = c = both = neither = 0
        for ex in ids:
            jc, lc = bool(by["jev"][ex].get("correct")), bool(by["llm"][ex].get("correct"))
            both += jc and lc
            b += jc and not lc
            c += lc and not jc
            neither += not jc and not lc
        return {"n": len(ids), "both_correct": both, "only_jev": b, "only_llm": c, "both_wrong": neither,
                "exact_mcnemar_p": round(exact_mcnemar(b, c), 4)}

    both_answered = [ex for ex in examples
                     if ex not in out["models"]["jev"]["never_answered"] and ex not in out["models"]["llm"]["never_answered"]]
    out["paired_all"] = paired(examples)
    out["paired_both_answered"] = paired(both_answered)
    out["disagreements"] = [
        {"example_id": ex, "reference": by["jev"][ex]["reference"], "jev": by["jev"][ex].get("prediction"),
         "jev_confidence": by["jev"][ex].get("confidence"), "llm": by["llm"][ex].get("prediction")}
        for ex in examples if by["jev"][ex].get("prediction") != by["llm"][ex].get("prediction")
    ]
    jc = [c for c in by["jev"].values() if c.get("confidence") is not None]
    out["jev_confidence_sidebar"] = [
        {"threshold": t, "kept": len(k), "correct_among_kept": sum(1 for c in k if c.get("correct"))}
        for t in (0.5, 0.8, 0.95) for k in [[c for c in jc if c["confidence"] >= t]]
    ]
    return out


def agreement(p1: Path, p2: Path) -> dict:
    _, a = load(p1)
    _, b = load(p2)
    res = {}
    for key in ("jev", "llm"):
        pa = {c["example_id"]: c.get("prediction") for c in a if c["model_key"] == key}
        pb = {c["example_id"]: c.get("prediction") for c in b if c["model_key"] == key}
        common = [e for e in pa if e in pb and pa[e] is not None and pb[e] is not None]
        res[key] = {"compared": len(common), "same_answer": sum(1 for e in common if pa[e] == pb[e]),
                    "changed_ids": [e for e in common if pa[e] != pb[e]]}
    return res


def fmt_ms(v):
    return "—" if v is None else f"{v:,.0f} ms"


def to_markdown(s: dict) -> str:
    j, l = s["models"]["jev"], s["models"]["llm"]
    ci = lambda m: f"{m['wilson95'][0]*100:.0f}–{m['wilson95'][1]*100:.0f}%"
    rows = [
        f"| | Jev | GPT-5.4-mini |",
        "| --- | --- | --- |",
        f"| Model that answered | `{j['answered_model']}` | `{l['answered_model']}` |",
        f"| Route | {j['route']} | {l['route']} |",
        f"| Correct of {j['total']} | **{j['correct']}** ({j['correct']/j['total']*100:.1f}%, 95% CI {ci(j)}) | **{l['correct']}** ({l['correct']/l['total']*100:.1f}%, 95% CI {ci(l)}) |",
        f"| Answered / correct of answered | {j['answered']} / {j['correct_of_answered']} | {l['answered']} / {l['correct_of_answered']} |",
        f"| Served request time: median / p95 / worst | {fmt_ms(j['served_ms']['median'])} / {fmt_ms(j['served_ms']['p95'])} / {fmt_ms(j['served_ms']['worst'])} | {fmt_ms(l['served_ms']['median'])} / {fmt_ms(l['served_ms']['p95'])} / {fmt_ms(l['served_ms']['worst'])} |",
        f"| Time to a usable answer (incl. retries): median / p95 / worst | {fmt_ms(j['usable_ms']['median'])} / {fmt_ms(j['usable_ms']['p95'])} / {fmt_ms(j['usable_ms']['worst'])} | {fmt_ms(l['usable_ms']['median'])} / {fmt_ms(l['usable_ms']['p95'])} / {fmt_ms(l['usable_ms']['worst'])} |",
        f"| Total wait for all {j['total']} answers | {j['sum_usable_s']:.1f} s | {l['sum_usable_s']:.1f} s |",
        f"| Examples that needed a retry | {j['availability']['examples_needing_retry']} | {l['availability']['examples_needing_retry']} |",
        f"| Catalog cost for the run | \\${j['catalog_cost_usd']:.4f} | \\${l['catalog_cost_usd']:.4f} |",
    ]
    pa, pb = s["paired_all"], s["paired_both_answered"]
    rows += ["", f"Paired (all {pa['n']}): both right {pa['both_correct']}, only Jev {pa['only_jev']}, only GPT-5.4-mini {pa['only_llm']}, both wrong {pa['both_wrong']}; exact McNemar p = {pa['exact_mcnemar_p']}.",
             f"Paired (both answered, {pb['n']}): only Jev {pb['only_jev']}, only GPT-5.4-mini {pb['only_llm']}; p = {pb['exact_mcnemar_p']}.",
             f"Jev time at TypeSafe (gateway-reported), median: {fmt_ms(j['provider_ms_median'])}. Actually charged for Jev: \\${j['charged_usd']:.4f} (Vercel promotion)."]
    av = j["availability"]
    rows += ["", f"Availability (Jev): {av['attempts_refused_429']} of {av['attempts_total']} attempts refused with HTTP 429; "
             f"{j['availability']['examples_needing_retry']} examples needed a retry; never answered: {j['never_answered'] or 'none'}; "
             f"slowest refusal {fmt_ms(av['slowest_refusal_ms'])}; retry-after sent: {av['retry_after_sent']}. "
             f"GPT-5.4-mini: {l['availability']['attempts_refused_429']} refusals under the same policy."]
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--repeat", help="second pass file for run-to-run agreement")
    ap.add_argument("--md")
    ap.add_argument("--json")
    args = ap.parse_args()
    s = summarize(Path(args.path))
    if args.repeat:
        s["run_to_run"] = agreement(Path(args.path), Path(args.repeat))
    md = to_markdown(s)
    if args.repeat:
        r = s["run_to_run"]
        md += "\n\nRun-to-run (pass 1 vs pass 2, same settings): " + "; ".join(
            f"{k}: same answer on {v['same_answer']} of {v['compared']}" for k, v in r.items())
    print(md)
    print("\nJev confidence sidebar (observed on this sample, not a calibration claim):", s["jev_confidence_sidebar"])
    print("Disagreements:", len(s["disagreements"]))
    if args.md:
        Path(args.md).write_text(md + "\n")
    if args.json:
        Path(args.json).write_text(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
