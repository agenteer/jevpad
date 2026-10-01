"""Rerun the comparison with BOTH models through Vercel AI Gateway (a declared variant).

The Sep 24-25 passes called Jev through Vercel AI Gateway and GPT-5.4-mini directly at
api.openai.com. This wrapper runs the same comparison with GPT-5.4-mini on the gateway
too (`openai/gpt-5.4-mini`, pinned to the OpenAI provider), so both models share one
route, one key and one retry policy. Everything else is run.py's own code.

    uv run python rerun_via_gateway.py --split dev
    uv run python rerun_via_gateway.py --split test --pass-no 3

How it reuses run.py without changing it (run.py stays byte-identical, so FROZEN.json
and the Sep 24-25 passes stay reproducible):

- run.py is loaded by file path as a module; its `jev_call`, `llm_call`,
  `call_with_retries`, `RUN_BUDGET_USD` and `sha_file` are used as they are.
- Settings come from `config-gateway.json` instead of `config.json`.
- Both entries of run.py's module-level `KEYS` dict are set to the one gateway key
  (the same mechanism run.py's own `main` uses).
- run.py's `llm_call` does not send provider options, so the LLM call gets a thin client
  wrapper that adds `providerOptions: {"gateway": {"only": llm.provider_only}}` to the
  request body before posting. Nothing else in the body changes.
- run.py's `llm_call` labels its route "openai (direct API)"; that label is replaced
  with the provider the gateway reports, and the gateway's own cost is kept as
  `gateway_cost`. The `cost` field stays usage x list price, as in run.py.
- The loop below mirrors run.py's `main` (alternating order, record format, budget
  stop); only the settings file, freeze file, key and output name differ.

Key: `AI_GATEWAY_API_KEY` from the environment or the root `.env` (the file run.py
reads). If it is missing, `TYPESAFE_API_KEY` is used when `TYPESAFE_BASE_URL` points at
ai-gateway.vercel.sh, because that key is then a Vercel AI Gateway key. The key is
never printed or written to the results.

The test split refuses to run unless `config-gateway.json`, `manifest.json`, `run.py`
and this file match `FROZEN-gateway.json`. Results go to
`results/test-<UTC>-gateway-pass<N>.jsonl`, so they never mix with the old passes.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
CONFIG_NAME = "config-gateway.json"
FROZEN_NAME = "FROZEN-gateway.json"
FROZEN_FILES = [CONFIG_NAME, "manifest.json", "run.py", "rerun_via_gateway.py"]
GATEWAY_HOST = "ai-gateway.vercel.sh"

_spec = importlib.util.spec_from_file_location("comparison_run", HERE / "run.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)


def sha_file(name: str, here: Path = HERE) -> str:
    return hashlib.sha256((here / name).read_bytes()).hexdigest()


def check_frozen(here: Path = HERE) -> dict:
    frozen = json.loads((here / FROZEN_NAME).read_text())
    for name in FROZEN_FILES:
        if frozen["sha256"].get(name) != sha_file(name, here):
            sys.exit(f"{name} changed after the gateway freeze; refusing to run the test split")
    return frozen


def read_env_file(path: Path) -> dict[str, str]:
    """Parse NAME=value lines the way run.py's load_key does (last match wins, value stripped).

    Unlike run.py, a missing file is not an error here: the key may come from the environment.
    """
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            name, value = line.split("=", 1)
            values[name] = value.strip()
    return values


def load_gateway_key(env_path: Path | None = None, environ=None) -> tuple[str, str]:
    """Return (key, where it came from). The key itself is never printed."""
    environ = os.environ if environ is None else environ
    dotenv = read_env_file(env_path or HERE.parent / ".env")

    def lookup(name: str) -> str | None:
        return environ.get(name) or dotenv.get(name) or None

    key = lookup("AI_GATEWAY_API_KEY")
    if key:
        return key, "AI_GATEWAY_API_KEY"
    base_url = lookup("TYPESAFE_BASE_URL") or ""
    key = lookup("TYPESAFE_API_KEY")
    if key and GATEWAY_HOST in base_url:
        return key, "TYPESAFE_API_KEY (TYPESAFE_BASE_URL is Vercel AI Gateway)"
    sys.exit("No Vercel AI Gateway key: set AI_GATEWAY_API_KEY, or TYPESAFE_API_KEY with "
             f"TYPESAFE_BASE_URL on {GATEWAY_HOST}, in the environment or the root .env")


class _ProviderPin:
    """Client wrapper that adds the gateway provider pin to run.py's LLM request body."""

    def __init__(self, client: httpx.Client, provider_only: list[str]):
        self._client = client
        self._only = list(provider_only)
        self.response: httpx.Response | None = None

    def post(self, url, *, json=None, **kwargs):
        body = dict(json or {})
        body["providerOptions"] = {"gateway": {"only": self._only}}
        self.response = self._client.post(url, json=body, **kwargs)
        return self.response


def _gateway_metadata(response: httpx.Response | None) -> dict:
    if response is None or not response.headers.get("content-type", "").startswith("application/json"):
        return {}
    try:
        data = response.json()
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    meta = data.get("provider_metadata") or data.get("providerMetadata") or {}
    return (meta.get("gateway") or {}) if isinstance(meta, dict) else {}


def gateway_llm_call(client: httpx.Client, cfg: dict, labels: list[str], text: str) -> dict:
    only = cfg["llm"]["provider_only"]
    pinned = _ProviderPin(client, only)
    out = base.llm_call(pinned, cfg, labels, text)
    gw = _gateway_metadata(pinned.response)
    routing = gw.get("routing") or {}
    attempts = [a for m in routing.get("modelAttempts", []) for a in m.get("providerAttempts", [])]
    if attempts:
        out["provider_attempts"] = [(a.get("provider"), a.get("statusCode")) for a in attempts]
        last = attempts[-1]
        if last.get("startTime") and last.get("endTime"):
            out["provider_ms"] = last["endTime"] - last["startTime"]
    if "final_provider" in out:
        reported = routing.get("finalProvider")
        out["final_provider"] = (f"{reported} (via Vercel AI Gateway)" if reported
                                 else f"not reported by the gateway (request pinned to only={only})")
        out["route"] = "Vercel AI Gateway, OpenAI-compatible endpoint"
        out["gateway_cost"] = gw.get("cost")
        out["gateway_market_cost"] = gw.get("marketCost")
        out["generation_id"] = gw.get("generationId")
    return out


def run_split(split: str, pass_no: int | None = None, limit: int | None = None, llm_effort: str | None = None,
              here: Path = HERE, results_dir: Path | None = None, transport: httpx.BaseTransport | None = None,
              environ=None, env_path: Path | None = None) -> Path:
    if split == "test":
        if pass_no is None:
            sys.exit("--pass-no is required on the test split (gateway passes are numbered from 3)")
        if limit:
            sys.exit("--limit is not allowed on the test split")
        if llm_effort:
            sys.exit("--llm-effort is not allowed on the test split")
    frozen = check_frozen(here) if split == "test" else None
    cfg = json.loads((here / CONFIG_NAME).read_text())
    if llm_effort:
        cfg["llm"]["reasoning_effort"] = llm_effort
    manifest = json.loads((here / "manifest.json").read_text())
    labels = manifest["labels"]
    examples = [e for e in manifest["examples"] if e["split"] == split][:limit]

    key, key_source = load_gateway_key(env_path, environ)
    base.KEYS.update(jev=key, llm=key)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = f"-gateway-pass{pass_no}" if split == "test" else "-gateway" + (f"-{llm_effort}" if llm_effort else "")
    out_path = (results_dir or here / "results") / f"{split}-{stamp}{tag}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    callers = {"jev": base.jev_call, "llm": gateway_llm_call}
    spent = 0.0
    batch_ms = {"jev": 0.0, "llm": 0.0}
    t_start = time.perf_counter()
    client_kwargs = {"timeout": cfg["timeout_s"]}
    if transport is not None:
        client_kwargs["transport"] = transport
    with httpx.Client(**client_kwargs) as client, out_path.open("w") as f:
        f.write(json.dumps({"type": "run_header", "split": split, "pass": pass_no, "started_utc": stamp,
                            "variant": cfg.get("variant"), "runner": "rerun_via_gateway.py",
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
    ap = argparse.ArgumentParser(description="Both models through Vercel AI Gateway (declared variant)")
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--pass-no", type=int, default=None, help="test: required; gateway passes are numbered from 3")
    ap.add_argument("--limit", type=int, default=None, help="dev only: first N examples")
    ap.add_argument("--llm-effort", default=None, help="dev only: override reasoning_effort")
    args = ap.parse_args(argv)
    run_split(args.split, args.pass_no, args.limit, args.llm_effort)


if __name__ == "__main__":
    main()
