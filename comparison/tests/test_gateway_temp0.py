"""Offline tests for the temperature-0 variant. Every HTTP call goes to httpx.MockTransport."""
import copy
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

spec = importlib.util.spec_from_file_location("rerun_gateway_temp0_under_test", HERE / "rerun_gateway_temp0.py")
t0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t0)
base, gw = t0.base, t0.gw
import score_gateway  # noqa: E402

FAKE_KEY = "fake-gateway-key"
CONFIG_GW = json.loads((HERE / "config-gateway.json").read_text())
CONFIG_T0 = json.loads((HERE / "config-gateway-temp0.json").read_text())
MANIFEST = json.loads((HERE / "manifest.json").read_text())
LABELS = MANIFEST["labels"]
LLM_CHARGE = 0.0004455


def fake_gateway(sent: list):
    """Answers the way Vercel AI Gateway did in the Sep 29 smoke test: the chat completion carries the
    generation ID as `id` and `generationId`, and the charge in `usage`; there is no provider_metadata."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append({"url": str(request.url), "auth": request.headers.get("authorization"), "body": body})
        if request.url.path.endswith("/systemone"):
            return httpx.Response(200, json={
                "model": "typesafe-ai/jev",
                "answers": {"intent": {"choice": LABELS[0], "confidence": 0.9,
                                       "probabilities": {LABELS[0]: 0.9, LABELS[1]: 0.1}}},
                "usage": {"input_tokens": 1000},
                "provider_metadata": {"gateway": {"cost": "0.000042", "marketCost": "0.000042", "generationId": "gen_jev",
                                                  "routing": {"finalProvider": "typesafe-ai"}}},
            })
        enum = body["response_format"]["json_schema"]["schema"]["properties"]["intent"]["enum"]
        return httpx.Response(200, json={
            "id": "gen_llm", "generationId": "gen_llm", "object": "chat.completion", "model": body["model"],
            "choices": [{"message": {"content": json.dumps({"intent": enum[0]})}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 498, "completion_tokens": 16, "total_tokens": 514,
                      "cost": LLM_CHARGE, "market_cost": LLM_CHARGE, "gateway_cost": LLM_CHARGE},
        })

    return httpx.MockTransport(handler)


def one_call(call, cfg):
    sent: list = []
    base.KEYS.update(jev=FAKE_KEY, llm=FAKE_KEY)
    with httpx.Client(transport=fake_gateway(sent)) as client:
        out = call(client, cfg, LABELS, "I still have not received my new card.")
    assert len(sent) == 1
    return sent[0], out


def test_config_differs_from_run_3_only_in_temperature_and_its_notes():
    t0cfg, gwcfg = copy.deepcopy(CONFIG_T0), copy.deepcopy(CONFIG_GW)
    assert t0cfg.pop("variant").startswith("both-via-gateway-temp0: GPT-5.4-mini at temperature 0")
    gwcfg.pop("variant")
    llm = t0cfg["llm"]
    assert llm.pop("temperature") == 0
    assert "API default of 1" in llm.pop("temperature_note")
    assert "usage.cost" in llm.pop("charge_note")
    assert t0cfg == gwcfg  # route, prompt, schema, reasoning effort, token cap, prices, retries: identical


def test_request_adds_only_temperature_zero_to_run_3s_body():
    sent, _ = one_call(t0.llm_call, CONFIG_T0)
    body = sent["body"]
    assert sent["url"] == "https://ai-gateway.vercel.sh/v1/chat/completions"
    assert body["temperature"] == 0
    assert body["reasoning_effort"] == "none"
    assert body["providerOptions"] == {"gateway": {"only": ["openai"]}}
    run3, _ = one_call(gw.gateway_llm_call, CONFIG_GW)
    assert "temperature" not in run3["body"]
    assert {k: v for k, v in body.items() if k != "temperature"} == run3["body"]


def test_llm_record_keeps_generation_id_and_gateway_charge():
    _, out = one_call(t0.llm_call, CONFIG_T0)
    assert out["prediction"] == LABELS[0]
    assert out["generation_id"] == "gen_llm"
    assert out["gateway_cost"] == LLM_CHARGE and out["gateway_market_cost"] == LLM_CHARGE
    assert out["temperature"] == 0
    assert out["final_provider"] == "not named in the response (request pinned to only=['openai'])"
    assert out["cost"] == pytest.approx((498 * 0.75 + 16 * 4.5) / 1e6)  # catalog cost, as in run.py


def test_run_3_runner_would_not_have_kept_them():
    _, out = one_call(gw.gateway_llm_call, CONFIG_GW)
    assert out["generation_id"] is None and out["gateway_cost"] is None


def test_jev_record_keeps_its_generation_id_and_charge():
    sent, out = one_call(base.jev_call, CONFIG_T0)
    assert "temperature" not in sent["body"]
    assert out["generation_id"] == "gen_jev" and out["cost"] == "0.000042"


def test_freeze_covers_the_runner_and_what_it_loads():
    frozen = t0.check_frozen()
    assert frozen["declared_before_any_test_call"] is True
    assert set(frozen["sha256"]) == {"config-gateway-temp0.json", "manifest.json", "run.py",
                                     "rerun_via_gateway.py", "rerun_gateway_temp0.py"}


def frozen_copy(tmp_path: Path) -> Path:
    for name in t0.FROZEN_FILES + [t0.FROZEN_NAME]:
        shutil.copy2(HERE / name, tmp_path / name)
    return tmp_path


@pytest.mark.parametrize("name", ["config-gateway-temp0.json", "manifest.json", "run.py",
                                  "rerun_via_gateway.py", "rerun_gateway_temp0.py"])
def test_test_split_refuses_when_a_frozen_file_changed(tmp_path, name):
    here = frozen_copy(tmp_path)
    t0.check_frozen(here)
    with (here / name).open("a") as f:
        f.write("\n")
    with pytest.raises(SystemExit, match="changed after the temperature-0 freeze"):
        t0.run_split("test", pass_no=4, here=here, results_dir=tmp_path / "results",
                     transport=fake_gateway([]), environ={"AI_GATEWAY_API_KEY": FAKE_KEY})
    assert not (tmp_path / "results").exists()


def test_offline_test_pass_is_scored_with_both_charges(tmp_path, capsys):
    sent: list = []
    out = t0.run_split("test", pass_no=4, results_dir=tmp_path, transport=fake_gateway(sent),
                       environ={"AI_GATEWAY_API_KEY": FAKE_KEY})
    assert re.fullmatch(r"test-\d{8}T\d{6}Z-gateway-temp0-pass4\.jsonl", out.name)
    n = sum(1 for e in MANIFEST["examples"] if e["split"] == "test")
    assert len(sent) == 2 * n
    assert all(s["body"]["temperature"] == 0 for s in sent if s["url"].endswith("/chat/completions"))
    assert FAKE_KEY not in out.read_text() and FAKE_KEY not in capsys.readouterr().out

    header = json.loads(out.read_text().splitlines()[0])
    assert header["runner"] == "rerun_gateway_temp0.py" and header["config"]["llm"]["temperature"] == 0

    s = score_gateway.summarize(out)
    assert s["settings"]["llm_temperature"] == 0
    assert s["models"]["llm"]["charged_usd"] == pytest.approx(LLM_CHARGE * n)
    assert s["models"]["jev"]["charged_usd"] == pytest.approx(0.000042 * n)
    assert s["models"]["llm"]["charged_answers"] == s["models"]["jev"]["charged_answers"] == n
    md = score_gateway.to_markdown(s)
    assert "temperature 0." in md and "not recorded" not in md and "(gateway-reported)" in md
