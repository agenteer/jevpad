"""Offline tests for the both-via-gateway rerun. Every HTTP call goes to httpx.MockTransport."""
import copy
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import httpx
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))


def load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gw = load("rerun_via_gateway_under_test", "rerun_via_gateway.py")
base = gw.base
import score  # noqa: E402
import score_gateway  # noqa: E402

FAKE_KEY = "fake-gateway-key"
CONFIG = json.loads((HERE / "config.json").read_text())
CONFIG_GW = json.loads((HERE / "config-gateway.json").read_text())
MANIFEST = json.loads((HERE / "manifest.json").read_text())
LABELS = MANIFEST["labels"]


def fake_provider(sent: list):
    """Answers like the gateway would: Jev on the systemone path, chat completions otherwise."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append({"url": str(request.url), "auth": request.headers.get("authorization"), "body": body})
        if request.url.path.endswith("/systemone"):
            choice = LABELS[0]
            return httpx.Response(200, json={
                "model": "typesafe-ai/jev",
                "answers": {"intent": {"choice": choice, "confidence": 0.9, "probabilities": {choice: 0.9}}},
                "usage": {"input_tokens": 500},
                "provider_metadata": {"gateway": {"cost": "0.000021", "generationId": "gen_jev",
                                                  "routing": {"finalProvider": "typesafe-ai"}}},
            })
        enum = body["response_format"]["json_schema"]["schema"]["properties"]["intent"]["enum"]
        return httpx.Response(200, json={
            "model": body["model"],
            "choices": [{"message": {"content": json.dumps({"intent": enum[1]})}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 10, "total_tokens": 510},
            "provider_metadata": {"gateway": {"cost": "0.000420", "generationId": "gen_llm", "routing": {
                "finalProvider": "openai",
                "modelAttempts": [{"providerAttempts": [
                    {"provider": "openai", "statusCode": 200, "startTime": 1000.0, "endTime": 1350.0}]}]}}},
        })

    return httpx.MockTransport(handler)


def captured_llm_body(module_call, cfg: dict) -> dict:
    sent: list = []
    base.KEYS.update(jev=FAKE_KEY, llm=FAKE_KEY)
    with httpx.Client(transport=fake_provider(sent)) as client:
        module_call(client, cfg, LABELS, "I still have not received my new card.")
    assert len(sent) == 1
    return sent[0]


def test_config_gateway_changes_only_the_llm_route():
    config, config_gw = copy.deepcopy(CONFIG), copy.deepcopy(CONFIG_GW)
    assert config_gw.pop("variant").startswith("both-via-gateway, declared and frozen on ")
    llm_gw, llm = config_gw.pop("llm"), config["llm"]
    rest = {k: v for k, v in config.items() if k != "llm"}
    assert config_gw == rest  # instruction, Jev, retry policy, timeout: identical
    assert llm_gw.pop("endpoint") == "https://ai-gateway.vercel.sh/v1/chat/completions"
    assert llm_gw.pop("model") == "openai/gpt-5.4-mini"
    assert llm_gw.pop("provider_only") == ["openai"]
    assert "paid credits" in llm_gw.pop("note")
    for key in ("endpoint", "model", "note"):
        llm.pop(key)
    assert llm_gw == llm  # system message, reasoning effort, token cap, prices: identical


def test_llm_request_goes_to_the_gateway_with_provider_pin_and_same_prompt():
    sent = captured_llm_body(gw.gateway_llm_call, CONFIG_GW)
    body = sent["body"]
    assert sent["url"] == "https://ai-gateway.vercel.sh/v1/chat/completions"
    assert sent["auth"] == f"Bearer {FAKE_KEY}"
    assert body["model"] == "openai/gpt-5.4-mini"
    assert body["providerOptions"] == {"gateway": {"only": ["openai"]}}
    assert body["reasoning_effort"] == "none"

    # Same body run.py builds for the Sep 24-25 passes, apart from the model name and the pin.
    original = captured_llm_body(base.llm_call, CONFIG)["body"]
    assert original["model"] == "gpt-5.4-mini" and "providerOptions" not in original
    trimmed = {k: v for k, v in body.items() if k not in ("model", "providerOptions")}
    assert trimmed == {k: v for k, v in original.items() if k != "model"}
    assert body["messages"][0] == {"role": "system", "content": CONFIG["llm"]["system"]}
    assert body["response_format"]["json_schema"]["schema"]["properties"]["intent"]["enum"] == LABELS


def test_llm_result_records_the_gateway_route_not_direct_openai():
    base.KEYS.update(jev=FAKE_KEY, llm=FAKE_KEY)
    with httpx.Client(transport=fake_provider([])) as client:
        out = gw.gateway_llm_call(client, CONFIG_GW, LABELS, "Where is my card?")
    assert out["prediction"] == LABELS[1]
    assert out["answered_model"] == "openai/gpt-5.4-mini"
    assert out["final_provider"] == "openai (via Vercel AI Gateway)"
    assert out["gateway_cost"] == "0.000420"
    assert out["provider_ms"] == 350.0
    assert out["cost_basis"] == "usage x list price in config.json"


def test_jev_request_is_unchanged_and_uses_the_same_gateway_key():
    sent = captured_llm_body(base.jev_call, CONFIG_GW)
    assert sent["url"] == CONFIG["jev"]["endpoint"]
    assert sent["auth"] == f"Bearer {FAKE_KEY}"
    assert sent["body"]["providerOptions"] == {"gateway": {"only": ["typesafe-ai"]}}


def write_env(tmp_path: Path, text: str) -> Path:
    env = tmp_path / ".env"
    env.write_text(text)
    return env


def test_key_prefers_ai_gateway_api_key(tmp_path):
    env = write_env(tmp_path, "AI_GATEWAY_API_KEY=from-dotenv\nTYPESAFE_API_KEY=other\n"
                              "TYPESAFE_BASE_URL=https://ai-gateway.vercel.sh/typesafe\n")
    assert gw.load_gateway_key(env, {})[0] == "from-dotenv"
    assert gw.load_gateway_key(env, {"AI_GATEWAY_API_KEY": "from-shell"})[0] == "from-shell"


def test_key_falls_back_to_typesafe_key_on_the_gateway(tmp_path):
    env = write_env(tmp_path, "# Route B\nTYPESAFE_API_KEY=typesafe-on-gateway\n"
                              "TYPESAFE_BASE_URL=https://ai-gateway.vercel.sh/typesafe\n")
    key, source = gw.load_gateway_key(env, {})
    assert key == "typesafe-on-gateway"
    assert source.startswith("TYPESAFE_API_KEY")
    # Base URL from the shell counts too.
    env2 = write_env(tmp_path, "TYPESAFE_API_KEY=typesafe-on-gateway\n")
    assert gw.load_gateway_key(env2, {"TYPESAFE_BASE_URL": "https://ai-gateway.vercel.sh/typesafe"})[0] == "typesafe-on-gateway"


def test_key_refuses_a_typesafe_console_key(tmp_path):
    env = write_env(tmp_path, "TYPESAFE_API_KEY=console-key\nTYPESAFE_BASE_URL=https://api.typesafe.ai\n")
    with pytest.raises(SystemExit) as exc:
        gw.load_gateway_key(env, {})
    assert "console-key" not in str(exc.value)
    with pytest.raises(SystemExit):
        gw.load_gateway_key(tmp_path / "missing.env", {})


def frozen_copy(tmp_path: Path) -> Path:
    for name in gw.FROZEN_FILES + [gw.FROZEN_NAME]:
        shutil.copy2(HERE / name, tmp_path / name)
    return tmp_path


def test_gateway_freeze_verifies_and_covers_the_runner():
    frozen = gw.check_frozen()
    assert frozen["declared_before_any_test_call"] is True
    assert set(frozen["sha256"]) == {"config-gateway.json", "manifest.json", "run.py", "rerun_via_gateway.py"}


@pytest.mark.parametrize("name", ["config-gateway.json", "manifest.json", "run.py", "rerun_via_gateway.py"])
def test_test_split_refuses_when_a_frozen_file_changed(tmp_path, name):
    here = frozen_copy(tmp_path)
    gw.check_frozen(here)
    with (here / name).open("a") as f:
        f.write("\n")
    with pytest.raises(SystemExit, match="changed after the gateway freeze"):
        gw.run_split("test", pass_no=3, here=here, results_dir=tmp_path / "results",
                     transport=fake_provider([]), environ={"AI_GATEWAY_API_KEY": FAKE_KEY})
    assert not (tmp_path / "results").exists()


def test_original_freeze_still_verifies():
    frozen = json.loads((HERE / "FROZEN.json").read_text())
    base.check_frozen()  # exits if config.json, manifest.json or run.py changed
    for name in ("config.json", "manifest.json", "run.py"):
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == frozen["sha256"][name]


def test_offline_test_pass_writes_a_gateway_file_that_score_reads(tmp_path, capsys):
    sent: list = []
    out = gw.run_split("test", pass_no=3, results_dir=tmp_path, transport=fake_provider(sent),
                       environ={"AI_GATEWAY_API_KEY": FAKE_KEY})
    assert re.fullmatch(r"test-\d{8}T\d{6}Z-gateway-pass3\.jsonl", out.name)
    n = sum(1 for e in MANIFEST["examples"] if e["split"] == "test")
    assert len(sent) == 2 * n
    assert {s["url"] for s in sent} == {CONFIG["jev"]["endpoint"], "https://ai-gateway.vercel.sh/v1/chat/completions"}
    assert FAKE_KEY not in out.read_text()
    assert FAKE_KEY not in capsys.readouterr().out

    header = json.loads(out.read_text().splitlines()[0])
    assert header["runner"] == "rerun_via_gateway.py" and header["pass"] == 3
    assert header["frozen"]["declared_before_any_test_call"] is True

    s = score.summarize(out)  # score.py itself, unchanged
    assert s["examples"] == n and s["pass"] == 3
    assert s["models"]["llm"]["answered_model"] == "openai/gpt-5.4-mini"
    assert s["models"]["llm"]["answered"] == n
    assert s["models"]["llm"]["route"] == "OpenAI API (direct)"  # the hard-coded label score_gateway.py replaces

    g = score_gateway.summarize(out)
    assert g["models"]["llm"]["route"] == "Vercel AI Gateway, pinned to the OpenAI provider"
    assert g["models"]["llm"]["charged_usd"] == pytest.approx(0.00042 * n)
    md = score_gateway.to_markdown(g)
    assert "OpenAI API (direct)" not in md and "Vercel promotion" not in md
    assert md.startswith("Variant: both-via-gateway")


def test_test_split_needs_a_pass_number(tmp_path):
    with pytest.raises(SystemExit, match="--pass-no is required"):
        gw.run_split("test", results_dir=tmp_path, transport=fake_provider([]),
                     environ={"AI_GATEWAY_API_KEY": FAKE_KEY})
