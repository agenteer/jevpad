"""Run Jev and one small LLM on the same BANKING77 examples.

Both models get the same message text, the same instruction and the same 77 label
strings. Neither sees the reference label. Calls are sequential (concurrency 1),
alternate which model goes first on each example, and are never retried: a failed
call is recorded as a failure.

    uv run python run.py --split dev
    uv run python run.py --split test      # refuses unless FROZEN.json matches
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).parent
FROZEN_FILES = ["config.json", "manifest.json", "run.py"]
RUN_BUDGET_USD = 2.0  # stop well below the $10 ceiling shared by all tutorial calls
KEYS: dict[str, str] = {}


def sha_file(name: str) -> str:
    return hashlib.sha256((HERE / name).read_bytes()).hexdigest()


def load_key(name: str) -> str:
    key = os.environ.get(name)
    if not key:
        env = HERE.parent / ".env"
        for line in env.read_text().splitlines():
            if line.startswith(f"{name}="):
                key = line.split("=", 1)[1].strip()
    if not key:
        sys.exit(f"{name} is not set (see LAUNCH_CONFIG.json)")
    return key


def check_frozen() -> dict:
    frozen = json.loads((HERE / "FROZEN.json").read_text())
    for name in FROZEN_FILES:
        if frozen["sha256"][name] != sha_file(name):
            sys.exit(f"{name} changed after the freeze; refusing to run the test split")
    return frozen


def jev_call(client: httpx.Client, cfg: dict, labels: list[str], text: str) -> dict:
    j = cfg["jev"]
    body = {
        "model": j["model"],
        "state": text,
        "questions": {
            "intent": {
                "type": "choice",
                "instructions": cfg["instruction"],
                "criteria": {label: None for label in labels},
            }
        },
        "providerOptions": {"gateway": {"only": j["provider_only"]}},
    }
    t0 = time.perf_counter()
    r = client.post(j["endpoint"], json=body, headers={"Authorization": f"Bearer {KEYS['jev']}"})
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    elapsed = (time.perf_counter() - t0) * 1000
    out = {"http_status": r.status_code, "elapsed_ms": round(elapsed, 1),
           "retry_after": r.headers.get("retry-after")}
    if r.status_code != 200 or "answers" not in data:
        out["error"] = (data.get("error") if isinstance(data, dict) else None) or r.text[:300]
        return out
    ans = data["answers"]["intent"]
    probs = ans.get("probabilities") or {}
    gw = (data.get("provider_metadata") or {}).get("gateway", {})
    attempts = [a for m in gw.get("routing", {}).get("modelAttempts", []) for a in m.get("providerAttempts", [])]
    if attempts:
        out["provider_attempts"] = [(a.get("provider"), a.get("statusCode")) for a in attempts]
        last = attempts[-1]
        if last.get("startTime") and last.get("endTime"):
            out["provider_ms"] = last["endTime"] - last["startTime"]
    out.update(
        prediction=ans.get("choice"),
        confidence=ans.get("confidence"),
        top3=sorted(probs.items(), key=lambda kv: -kv[1])[:3],
        answered_model=data.get("model"),
        usage=data.get("usage"),
        final_provider=gw.get("routing", {}).get("finalProvider"),
        cost=gw.get("cost"),
        market_cost=gw.get("marketCost"),
        generation_id=gw.get("generationId"),
    )
    return out


def llm_call(client: httpx.Client, cfg: dict, labels: list[str], text: str) -> dict:
    m = cfg["llm"]
    body = {
        "model": m["model"],
        "messages": [
            {"role": "system", "content": m["system"]},
            {"role": "user", "content": f"{cfg['instruction']}\n\nCustomer message:\n{text}"},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "intent",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"intent": {"type": "string", "enum": labels}},
                    "required": ["intent"],
                    "additionalProperties": False,
                },
            },
        },
        "max_completion_tokens": m["max_completion_tokens"],
    }
    if m.get("reasoning_effort"):
        body["reasoning_effort"] = m["reasoning_effort"]
    t0 = time.perf_counter()
    r = client.post(m["endpoint"], json=body, headers={"Authorization": f"Bearer {KEYS['llm']}"})
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    elapsed = (time.perf_counter() - t0) * 1000
    out = {"http_status": r.status_code, "elapsed_ms": round(elapsed, 1),
           "retry_after": r.headers.get("retry-after")}
    if r.status_code != 200 or "choices" not in data:
        out["error"] = (data.get("error") if isinstance(data, dict) else None) or r.text[:300]
        return out
    content = data["choices"][0]["message"].get("content") or ""
    try:
        prediction = json.loads(content)["intent"]
    except (json.JSONDecodeError, KeyError, TypeError):
        prediction = None
        out["error"] = f"unparseable content: {content[:200]!r}"
    usage = data.get("usage") or {}
    out.update(
        prediction=prediction,
        answered_model=data.get("model"),
        finish_reason=data["choices"][0].get("finish_reason"),
        usage={k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
        reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        cost=round((usage.get("prompt_tokens") or 0) * m["price_per_million"]["input"] / 1e6
                   + (usage.get("completion_tokens") or 0) * m["price_per_million"]["output"] / 1e6, 8),
        cost_basis="usage x list price in config.json",
        final_provider="openai (direct API)",
    )
    return out


RETRYABLE = {429, 500, 502, 503, 504}


def call_with_retries(caller, client, cfg, labels, text) -> dict:
    """Same policy for both models: retry 429/5xx/timeouts with backoff.

    elapsed_ms is the final attempt only; total_ms includes every attempt and wait.
    """
    policy = cfg["retry_policy"]
    attempts = []
    t0 = time.perf_counter()
    for attempt in range(policy["max_attempts"]):
        t_attempt = time.perf_counter()
        try:
            res = caller(client, cfg, labels, text)
        except httpx.HTTPError as e:
            res = {"http_status": None, "error": f"{type(e).__name__}: {e}",
                   "elapsed_ms": round((time.perf_counter() - t_attempt) * 1000, 1)}
        err = res.get("error")
        attempts.append({
            "status": res.get("http_status"),
            "elapsed_ms": res.get("elapsed_ms"),
            "error": str(err.get("message") if isinstance(err, dict) else err)[:160] if err else None,
            "retry_after": res.get("retry_after"),
        })
        retryable = res.get("http_status") in RETRYABLE or res.get("http_status") is None
        if not retryable or attempt == policy["max_attempts"] - 1:
            break
        wait = policy["backoff_s"][min(attempt, len(policy["backoff_s"]) - 1)]
        try:
            wait = max(wait, float(res.get("retry_after") or 0))
        except ValueError:
            pass
        time.sleep(min(wait, policy["max_wait_s"]))
    res["attempt_log"] = attempts
    res["attempt_statuses"] = [a["status"] for a in attempts]
    res["attempts"] = len(attempts)
    res["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--limit", type=int, default=None, help="dev only: first N examples")
    ap.add_argument("--llm-effort", default=None, help="dev only: override reasoning_effort")
    ap.add_argument("--pass-no", type=int, default=1, help="test: pass 1 (headline) or 2 (repeat)")
    args = ap.parse_args()

    frozen = check_frozen() if args.split == "test" else None
    if args.split == "test" and args.limit:
        sys.exit("--limit is not allowed on the test split")
    cfg = json.loads((HERE / "config.json").read_text())
    if args.llm_effort:
        if args.split == "test":
            sys.exit("--llm-effort is not allowed on the test split")
        cfg["llm"]["reasoning_effort"] = args.llm_effort
    manifest = json.loads((HERE / "manifest.json").read_text())
    labels = manifest["labels"]
    examples = [e for e in manifest["examples"] if e["split"] == args.split][: args.limit]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = f"-{args.llm_effort}" if args.llm_effort else ""
    if args.split == "test":
        tag = f"-pass{args.pass_no}"
    out_path = HERE / "results" / f"{args.split}-{stamp}{tag}.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    KEYS.update(jev=load_key("AI_GATEWAY_API_KEY"), llm=load_key("OPENAI_API_KEY"))
    callers = {"jev": jev_call, "llm": llm_call}
    spent = 0.0
    batch_ms = {"jev": 0.0, "llm": 0.0}
    t_start = time.perf_counter()
    with httpx.Client(timeout=cfg["timeout_s"]) as client, out_path.open("w") as f:
        f.write(json.dumps({"type": "run_header", "split": args.split, "pass": args.pass_no, "started_utc": stamp,
                            "config": cfg, "frozen": frozen,
                            "sha256": {n: sha_file(n) for n in FROZEN_FILES}}) + "\n")
        for i, ex in enumerate(examples):
            order = ["jev", "llm"] if i % 2 == 0 else ["llm", "jev"]
            for position, key in enumerate(order):
                started = datetime.now(timezone.utc).isoformat()
                res = call_with_retries(callers[key], client, cfg, labels, ex["text"])
                pred = res.get("prediction")
                rec = {
                    "type": "call", "example_id": ex["example_id"], "model_key": key,
                    "position": position, "started_utc": started, "reference": ex["label"],
                    "valid": pred in labels, "correct": pred == ex["label"], **res,
                }
                batch_ms[key] += res.get("elapsed_ms") or 0.0
                for c in (res.get("cost"),):
                    try:
                        spent += float(c or 0)
                    except (TypeError, ValueError):
                        pass
                f.write(json.dumps(rec) + "\n")
            f.flush()
            if spent > RUN_BUDGET_USD:
                print(f"budget stop at ${spent:.4f}")
                break
            if (i + 1) % 20 == 0:
                print(f"{i + 1}/{len(examples)} examples, billed so far ${spent:.5f}", flush=True)
        f.write(json.dumps({"type": "run_footer", "wall_s": round(time.perf_counter() - t_start, 2),
                            "sum_request_ms": batch_ms, "billed_usd": spent}) + "\n")
    print(f"done -> {out_path.relative_to(HERE)}  billed ${spent:.5f}")


if __name__ == "__main__":
    main()
