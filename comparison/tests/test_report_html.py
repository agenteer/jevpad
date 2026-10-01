"""The web page score_comparison.py writes: numbers match the scored summary, wording follows the data."""
import copy
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import report_html  # noqa: E402
import score  # noqa: E402
import score_comparison  # noqa: E402
import score_gateway  # noqa: E402

RUN5 = HERE / "results/test-20260930T224309Z-gateway-temp0-pass5.jsonl"
SUMMARY = score_gateway.summarize(RUN5)
TEXTS = report_html.message_texts()


def page(summary=SUMMARY) -> str:
    return report_html.render(summary, TEXTS, RUN5.name)


def visible(html_text: str) -> str:
    text = re.sub(r"<style>.*?</style>", "", html_text, flags=re.S).replace("<wbr>", "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))


def test_run_5_page_shows_the_scored_numbers():
    text = visible(page())
    for expected in (
        "Jev 116 vs GPT-5.4-mini 111 right, of 154", "No clear difference on this sample.",
        "68–81%", "between 68% and 81%", "65–79%", "Both right: 102", "Only Jev right: 14", "Only GPT-5.4-mini right: 9", "Both wrong: 29",
        "which one gets each of the 23 split messages right would be a coin flip",
        "a split of 14 to 9 or more lopsided, either way, comes up about 40 times in 100", "p = 0.4049",
        "exact McNemar's test", "231 ms", "911 ms", "411 ms", "1,620 ms", "2,970 ms", "39.0 s", "155.2 s",
        "No refusals, no retries.", "$0.0067", "$0.0672", "GPT-5.4-mini cost about 10 times as much as Jev at list price.",
        "76 of 83 = 92%", "The other 71 would go to another path; 40 of those were right.",
        "called directly at OpenAI with reasoning turned off; Vercel AI Gateway, the route used here, drops those numbers", "would not be the same kind of number as Jev's", "29 messages where the two gave different answers",
        "“How do I locate my card?”",
    ):
        assert expected in text, expected
    assert page().count("<td class='who'>") == len(SUMMARY["disagreements"]) == 29


def test_page_is_self_contained_and_leaks_no_local_path():
    html_text = page()
    assert "<script" not in html_text and "src=" not in html_text and "<link" not in html_text
    assert "http://" not in html_text and "https://" not in html_text
    assert str(HERE) not in html_text and str(Path.home()) not in html_text


def test_headline_follows_the_p_value_not_this_run():
    clear = copy.deepcopy(SUMMARY)
    clear["models"]["llm"]["correct"] = 100
    clear["paired_all"].update(only_jev=20, only_llm=4, exact_mcnemar_p=round(score.exact_mcnemar(20, 4), 4))
    text = visible(page(clear))
    assert "Jev was more accurate — a clear difference on this sample." in text
    assert "about 0.2 times" not in text and "fewer than 1 time in 100" in text
    assert "That is below the bar" in text

    tied = copy.deepcopy(SUMMARY)
    tied["models"]["llm"]["correct"] = tied["models"]["jev"]["correct"]
    assert "Both models got the same number right." in visible(page(tied))


def test_retries_show_served_time_and_refusals():
    busy = copy.deepcopy(SUMMARY)
    busy["models"]["jev"]["availability"].update(attempts_refused_429=12, examples_needing_retry=12)
    text = visible(page(busy))
    assert "Served time: the one request that succeeded" in text
    assert "HTTP 429 is a server saying" in text and "Jev: 12 refusals, 12 messages retried" in text
    assert "No refusals, no retries." not in text


def test_chance_wording():
    assert report_html.chance_in_100(0.2863) == "about 29 times in 100"
    assert report_html.chance_in_100(0.0496) == "about 5.0 times in 100"
    assert report_html.chance_in_100(0.001) == "fewer than 1 time in 100"
    assert report_html.chance_in_100(1.0) == "almost every time"


def test_score_comparison_writes_the_page_next_to_the_run(tmp_path, capsys, monkeypatch):
    run = tmp_path / RUN5.name
    shutil.copy(RUN5, run)
    monkeypatch.setattr(sys, "argv", ["score_comparison.py", str(run)])
    score_comparison.main()
    out = capsys.readouterr().out
    written = tmp_path / (RUN5.stem + ".report.html")
    assert written.exists() and written.read_text() == page()
    assert "Disagreements: 29" in out and written.as_uri() in out


def test_setup_block_states_the_conditions_of_run_5():
    text = visible(page()).replace("&#x27;", "'")
    assert "How this run was set up" in text
    assert "Both through Vercel AI Gateway, with one key and one retry rule." in text
    assert "Jev was pinned to TypeSafe, its maker; GPT-5.4-mini to OpenAI, its maker." in text
    assert "the same 77 labels" in text and "a strict JSON schema" in text
    assert "answers with the most probable one: on 153 of its 154 answers here." in text
    assert "0: at each step GPT-5.4-mini takes its most likely next word piece" in text
    assert "None: it answers straight away" in text
    assert "One request at a time, taking turns which model went first." in text
    # The setup comes before the results it conditions.
    assert text.index("How this run was set up") < text.index("1. Accuracy")


def test_setup_block_shows_default_temperature_when_unset():
    unset = copy.deepcopy(SUMMARY)
    unset["settings"]["llm_temperature"] = None
    text = visible(page(unset))
    assert "Not set, so the default of 1 applied" in text
    assert "0: at each step GPT-5.4-mini takes its most likely next word piece" not in text


def test_unrecorded_charge_wording_says_not_recorded_not_unreported():
    unrecorded = copy.deepcopy(SUMMARY)
    unrecorded["models"]["llm"]["charged_usd"] = None
    html_text = page(unrecorded)
    text = visible(html_text).replace("&#x27;", "'")
    assert "not reported by the gateway" not in html_text
    assert "Charged by Vercel $0.0067 not recorded by this run" in text
    assert "Jev's charge matches its catalog cost." in text
    assert "This run did not save GPT-5.4-mini 's charge or the generation ID that finds it" in text


def test_recorded_charges_for_both_models():
    both = copy.deepcopy(SUMMARY)
    both["models"]["llm"]["charged_usd"] = both["models"]["llm"]["catalog_cost_usd"]
    text = visible(page(both))
    assert "not recorded by this run" not in text
    assert "In this run both charges match the catalog cost." in text
    promo = copy.deepcopy(both)
    promo["models"]["jev"]["charged_usd"] = 0.0
    text = visible(page(promo))
    assert "Jev was charged $0.0000 against a catalog cost of $0.0067" in text
    assert "GPT-5.4-mini 's charge matches its catalog cost." in text.replace("&#x27;", "'")


def test_95_percent_range_is_rounded_once():
    j = SUMMARY["models"]["jev"]
    assert 0.8145 < j["wilson95"][1] < 0.8147  # unrounded: 0.81462 -> "81", not 0.815 -> "82"
    assert report_html.ci(j) == "68–81%"
    assert "95% CI 68–81%" in score_gateway.to_markdown(SUMMARY)


def test_disagreements_say_where_the_other_both_wrong_messages_went():
    text = visible(page())
    assert "both wrong, with different answers: 6. The other 23 messages both got wrong are not listed" in text
