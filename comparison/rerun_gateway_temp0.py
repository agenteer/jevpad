"""Run the comparison with GPT-5.4-mini at temperature 0 and Vercel's charge recorded for both (a declared variant).

Run 3 (Sep 29) sent both models through Vercel AI Gateway (rerun_via_gateway.py). This variant keeps
that route, prompt, schema, reasoning effort and retry policy, and changes one setting and one record:

- Setting: GPT-5.4-mini gets `temperature: 0`. Runs 1-3 did not set it, so the API default of 1
  applied and each label was sampled. At 0 it takes its most likely next token at every step, so it
  gives its most likely label, as Jev gives the option it rates most probable. Jev has no
  temperature setting; its Choice answer was the top-probability option on 154 of 154 in run 3.
- Record: the gateway returns each chat completion's generation ID as the response `id` and its
  charge in `usage.cost` / `usage.market_cost`. Run 3 read only `provider_metadata`, which this
  endpoint does not send, so GPT-5.4-mini's charge was not saved. Here they are saved as
  `generation_id`, `gateway_cost` and `gateway_market_cost`, the fields Jev's answers already carry.

    uv run python rerun_gateway_temp0.py --split dev --limit 2
    uv run python rerun_gateway_temp0.py --split test --pass-no 4

How it reuses the frozen files without changing them (run.py and rerun_via_gateway.py stay
byte-identical, so FROZEN.json, FROZEN-gateway.json and runs 1-3 stay reproducible):

- run.py's `jev_call`, `llm_call`, `call_with_retries` and `RUN_BUDGET_USD` are used as they are;
  rerun_via_gateway.py's key lookup and gateway-metadata reader too.
- run.py's `llm_call` sends no provider options and no temperature, so its client gets a thin wrapper
  that adds `providerOptions: {"gateway": {"only": llm.provider_only}}` and `temperature: llm.temperature`
  to the request body before posting. Nothing else in the body changes.
- The loop below mirrors rerun_via_gateway.py's (alternating order, record format, budget stop);
  only the settings file, freeze file, runner name and output name differ.

Key: the one Vercel AI Gateway key, found as rerun_via_gateway.py finds it (AI_GATEWAY_API_KEY, or
TYPESAFE_API_KEY when TYPESAFE_BASE_URL is on ai-gateway.vercel.sh). It is never printed or saved.

The test split refuses to run unless config-gateway-temp0.json, manifest.json, run.py,
rerun_via_gateway.py and this file match FROZEN-gateway-temp0.json. Results go to
`results/test-<UTC>-gateway-temp0-pass<N>.jsonl`.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
RUNNER = "rerun_gateway_temp0.py"
CONFIG_NAME = "config-gateway-temp0.json"
FROZEN_NAME = "FROZEN-gateway-temp0.json"
FROZEN_FILES = [CONFIG_NAME, "manifest.json", "run.py", "rerun_via_gateway.py", RUNNER]
TAG = "gateway-temp0"

_spec = importlib.util.spec_from_file_location("comparison_rerun_via_gateway", HERE / "rerun_via_gateway.py")
gw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gw)
base = gw.base  # run.py, loaded unchanged


def sha_file(name: str, here: Path = HERE) -> str:
    return hashlib.sha256((here / name).read_bytes()).hexdigest()


def check_frozen(here: Path = HERE) -> dict:
    frozen = json.loads((here / FROZEN_NAME).read_text())
    for name in FROZEN_FILES:
        if frozen["sha256"].get(name) != sha_file(name, here):
            sys.exit(f"{name} changed after the temperature-0 freeze; refusing to run the test split")
    return frozen


class _PinAndTemperature:
    """Client wrapper that adds the provider pin and the temperature to run.py's LLM request body."""

    def __init__(self, client: httpx.Client, provider_only: list[str], temperature: float):
        self._client = client
        self._only = list(provider_only)
        self._temperature = temperature
        self.response: httpx.Response | None = None

    def post(self, url, *, json=None, **kwargs):
        body = dict(json or {})
        body["providerOptions"] = {"gateway": {"only": self._only}}
        body["temperature"] = self._temperature
        self.response = self._client.post(url, json=body, **kwargs)
        return self.response


def _response_json(response: httpx.Response | None) -> dict:
    if response is None or not response.headers.get("content-type", "").startswith("application/json"):
        return {}
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def llm_call(client: httpx.Client, cfg: dict, labels: list[str], text: str) -> dict:
    m = cfg["llm"]
    only = m["provider_only"]
    pinned = _PinAndTemperature(client, only, m["temperature"])
    out = base.llm_call(pinned, cfg, labels, text)
    data = _response_json(pinned.response)
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    meta = gw._gateway_metadata(pinned.response)
    routing = meta.get("routing") or {}
    attempts = [a for mo in routing.get("modelAttempts", []) for a in mo.get("providerAttempts", [])]
    if attempts:
        out["provider_attempts"] = [(a.get("provider"), a.get("statusCode")) for a in attempts]
        last = attempts[-1]
        if last.get("startTime") and last.get("endTime"):
            out["provider_ms"] = last["endTime"] - last["startTime"]
    if "final_provider" in out:  # set by run.py only when the model answered
        reported = routing.get("finalProvider")
        out["final_provider"] = (f"{reported} (via Vercel AI Gateway)" if reported
                                 else f"not named in the response (request pinned to only={only})")
        out["route"] = "Vercel AI Gateway, OpenAI-compatible endpoint"
        out["temperature"] = m["temperature"]
        out["generation_id"] = data.get("generationId") or data.get("id") or meta.get("generationId")
        cost, market = usage.get("cost"), usage.get("market_cost")
        if cost is None:
            cost, market = meta.get("cost"), meta.get("marketCost")
        out["gateway_cost"] = cost
        out["gateway_market_cost"] = market
        out["gateway_cost_basis"] = "charge reported by Vercel AI Gateway in the response (usage.cost)"
    return out


def run_split(split: str, pass_no: int | None = None, limit: int | None = None, here: Path = HERE,
              results_dir: Path | None = None, transport: httpx.BaseTransport | None = None,
              environ=None, env_path: Path | None = None) -> Path:
    if split == "test":
        if pass_no is None:
            sys.exit("--pass-no is required on the test split")
        if limit:
            sys.exit("--limit is not allowed on the test split")
    frozen = check_frozen(here) if split == "test" else None
    cfg = json.loads((here / CONFIG_NAME).read_text())
    manifest = json.loads((here / "manifest.json").read_text())
    labels = manifest["labels"]
    examples = [e for e in manifest["examples"] if e["split"] == split][:limit]

    key, key_source = gw.load_gateway_key(env_path, environ)
    base.KEYS.update(jev=key, llm=key)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = f"-{TAG}-pass{pass_no}" if split == "test" else f"-{TAG}"
    out_path = (results_dir or here / "results") / f"{split}-{stamp}{tag}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    callers = {"jev": base.jev_call, "llm": llm_call}
    spent = 0.0
    batch_ms = {"jev": 0.0, "llm": 0.0}
    t_start = time.perf_counter()
    client_kwargs = {"timeout": cfg["timeout_s"]}
    if transport is not None:
        client_kwargs["transport"] = transport
    with httpx.Client(**client_kwargs) as client, out_path.open("w") as f:
        f.write(json.dumps({"type": "run_header", "split": split, "pass": pass_no, "started_utc": stamp,
                            "variant": cfg.get("variant"), "runner": RUNNER,
                            "key_source": key_source, "config": cfg, "frozen": frozen,
                            "sha256": {n: sha_file(n, here) for n in FROZEN_FILES}}) + "\n")
        for i, ex in enumerate(examples):
            order = ["jev", "llm"] if i % 2 == 0 else ["llm", "jev"]
            for position, model_key in enumerate(order):
                started = datetime.now(timezone.utc).isoformat()
                res = base.call_with_retries(callers[model_key], client, cfg, labels, ex["text"])
                pred = res.get("prediction")
                rec = {
                    "type": "call", "example_id": ex["example_id"], "model_key": model_key,
                    "position": position, "started_utc": started, "reference": ex["label"],
                    "valid": pred in labels, "correct": pred == ex["label"], **res,
                }
                batch_ms[model_key] += res.get("elapsed_ms") or 0.0
                try:
                    spent += float(res.get("cost") or 0)
                except (TypeError, ValueError):
                    pass
                f.write(json.dumps(rec) + "\n")
            f.flush()
            if spent > base.RUN_BUDGET_USD:
                print(f"budget stop at ${spent:.4f}")
                break
            if (i + 1) % 20 == 0:
                print(f"{i + 1}/{len(examples)} examples, billed so far ${spent:.5f}", flush=True)
        f.write(json.dumps({"type": "run_footer", "wall_s": round(time.perf_counter() - t_start, 2),
                            "sum_request_ms": batch_ms, "billed_usd": spent}) + "\n")
    print(f"done -> {out_path}  billed ${spent:.5f}  (key from {key_source})")
    return out_path


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Both models through Vercel AI Gateway, GPT-5.4-mini at temperature 0")
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--pass-no", type=int, default=None, help="test: required")
    ap.add_argument("--limit", type=int, default=None, help="dev only: first N examples")
    args = ap.parse_args(argv)
    run_split(args.split, args.pass_no, args.limit)


if __name__ == "__main__":
    main()
