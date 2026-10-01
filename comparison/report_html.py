"""One self-contained web page for a scored comparison run, made to be read on screen.

score_comparison.py writes it next to the results file. Every number comes from the summary that
score_gateway.summarize() builds (the same numbers as the printed table), plus the message texts
from manifest.json. Every sentence that states a result is computed from those numbers, so the page
reads correctly for any run, not just the one it was first written against.

Reads only the saved answers; it calls no model.
"""
from __future__ import annotations

import html
import json
import math
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
JEV, LLM = "Jev", "GPT-5.4-mini"
CLEAR_BAR = 0.05  # the usual bar for "clear": p below 5 in 100


def e(value) -> str:
    return html.escape(str(value))


def ms(value) -> str:
    return "—" if value is None else f"{value:,.0f} ms"


def usd(value) -> str:
    return "—" if value is None else f"${value:.4f}"


def pct(k: int, n: int) -> str:
    return "—" if not n else f"{k / n * 100:.1f}%"


def whole_pct(k: int, n: int) -> str:
    return "—" if not n else f"{round(k / n * 100)}%"


def ci(model: dict) -> str:
    lo, hi = model["wilson95"]
    return f"{lo * 100:.0f}–{hi * 100:.0f}%"


def chance_in_100(p: float) -> str:
    """0.2863 -> 'about 29 times in 100'."""
    if p >= 0.995:
        return "almost every time"
    if 0.04 <= p < 0.06:  # near the bar, rounding to a whole number would blur which side it is on
        return f"about {p * 100:.1f} times in 100"
    if p * 100 >= 0.5:
        return f"about {round(p * 100)} times in 100"
    return "fewer than 1 time in 100"


def label(name) -> str:
    """A dataset label in code type, breakable after each underscore so long labels wrap."""
    if name is None:
        return "<span class='muted'>no answer</span>"
    return "<code>" + e(name).replace("_", "_<wbr>") + "</code>"


def nowrap_names(text: str) -> str:
    """Keep "GPT-5.4-mini" on one line; browsers otherwise break it at a hyphen."""
    return text.replace(LLM, f"<span class='nm'>{LLM}</span>")


def run_time(started_utc: str) -> str:
    try:
        t = datetime.strptime(started_utc, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return started_utc
    return f"{t.day} {t.strftime('%B %Y, %H:%M')} UTC"


def times_as_much(big: float, small: float) -> str:
    r = big / small
    return f"about {r:.0f} times" if r >= 3 else f"about {r:.1f} times"


# ---------------------------------------------------------------- the three answers


def accuracy_answer(s: dict) -> tuple[str, str]:
    j, l, pa = s["models"]["jev"], s["models"]["llm"], s["paired_all"]
    n = j["total"]
    score = f"{JEV} {j['correct']} vs {LLM} {l['correct']} right, of {n}"
    if j["correct"] == l["correct"]:
        return f"{score}", "Both models got the same number right."
    if pa["exact_mcnemar_p"] < CLEAR_BAR:
        better = JEV if j["correct"] > l["correct"] else LLM
        return score, f"{better} was more accurate — a clear difference on this sample."
    return score, "No clear difference on this sample."


def speed_answer(s: dict) -> tuple[str, str]:
    j, l = s["models"]["jev"]["usable_ms"]["median"], s["models"]["llm"]["usable_ms"]["median"]
    if j is None or l is None:
        return "—", "No answers to time."
    head = f"{JEV} {ms(j)} vs {LLM} {ms(l)} for a typical answer"
    if max(j, l) / min(j, l) < 1.1:
        return head, "About the same speed."
    faster, ratio = (JEV, l / j) if j < l else (LLM, j / l)
    return head, f"{faster} answered faster, about {ratio:.1f} times as fast."


def cost_answer(s: dict) -> tuple[str, str]:
    j, l = s["models"]["jev"]["catalog_cost_usd"], s["models"]["llm"]["catalog_cost_usd"]
    n = s["models"]["jev"]["total"]
    head = f"{JEV} {usd(j)} vs {LLM} {usd(l)} for {n} messages"
    if not j or not l or max(j, l) / min(j, l) < 1.1:
        return head, "About the same cost."
    dearer, cheaper, big, small = (LLM, JEV, l, j) if l > j else (JEV, LLM, j, l)
    return head, f"{dearer} cost {times_as_much(big, small)} as much as {cheaper} at list price."


# ---------------------------------------------------------------- how the run was set up

GATEWAY_HOST = "ai-gateway.vercel.sh"
PROVIDER_NAMES = {"typesafe-ai": "TypeSafe", "openai": "OpenAI", "azure": "Azure"}
NOT_RECORDED = "not recorded by this run"


def providers(only) -> str:
    return " or ".join(PROVIDER_NAMES.get(p, p) for p in (only or [])) or "no provider pinned"


def route_words(st: dict) -> str:
    def one(host, only, name):
        if host == GATEWAY_HOST:
            return f"{name} through Vercel AI Gateway, pinned to {providers(only)}"
        if host == "api.openai.com":
            return f"{name} directly at OpenAI's own API"
        return f"{name} at {host}"
    if st["jev_host"] == st["llm_host"] == GATEWAY_HOST:
        return (f"Both through Vercel AI Gateway, with one key and one retry rule. {JEV} was pinned to "
                f"{providers(st['jev_provider_only'])}, its maker; {LLM} to {providers(st['llm_provider_only'])}, its maker.")
    return one(st["jev_host"], st["jev_provider_only"], JEV) + "; " + one(st["llm_host"], st["llm_provider_only"], LLM) + "."


def temperature_words(t) -> str:
    if t is None:
        return (f"Not set, so the default of 1 applied: each label was drawn at random, weighted by how likely {LLM} "
                "found it, so the same message can get a different label on another run.")
    if t == 0:
        return (f"0: at each step {LLM} takes its most likely next word piece, so it gives its most likely label "
                "instead of a random draw.")
    return f"{t:g}: each label was drawn at random, weighted by how likely {LLM} found it."


def reasoning_words(effort) -> str:
    if effort is None:
        return "Not set (the API default)."
    if effort == "none":
        return "None: it answers straight away, with no hidden thinking step first."
    return f"{effort}: it may think before it answers."


def setup_section(s: dict) -> str:
    st = s.get("settings")
    if not st:
        return ""
    top = st["jev_top_probability_choice"]
    k, m = top["choice_is_top"], top["answers_with_probabilities"]
    jev_pick = (f"{JEV} gives every label a probability and answers with the most probable one: "
                + (f"every time here ({k} of {m}), so nothing is left to chance." if k == m and m
                   else f"on {k} of its {m} answers here."))
    schema = (f"; its reply could only be one of the {st['labels']} labels (a strict JSON schema)"
              if st.get("llm_system_message") else "")
    prompt = (f"Both got the same customer message, the same one-sentence instruction and the same {st['labels']} labels. "
              f"{JEV} got them as one Choice question. {LLM} also got a one-line system message saying it sorts bank "
              f"support messages{schema}.")
    order = ("One request at a time" if st.get("concurrency") == 1 else f"Up to {st.get('concurrency')} requests at once") + (
        ", taking turns which model went first." if st.get("alternating_order") else ".")
    rows = [
        ("Route", route_words(st)),
        ("What each was asked", prompt),
        (f"How {JEV} picks", jev_pick),
        (f"{LLM}'s temperature", "How much chance goes into its choice of words. " + temperature_words(st["llm_temperature"])),
        (f"{LLM}'s reasoning effort", reasoning_words(st["llm_reasoning_effort"])),
        ("Order", order),
    ]
    body = "".join(f"<tr><th>{nowrap_names(e(k))}</th><td>{nowrap_names(e(v))}</td></tr>" for k, v in rows)
    return f"<section class='setup'><h2>How this run was set up</h2><table class='settings'><tbody>{body}</tbody></table></section>"


# ---------------------------------------------------------------- sections


def bar(segments: list[tuple[str, int, str]], total: int) -> str:
    parts = []
    for name, count, cls in segments:
        if count:
            parts.append(f"<div class='seg {cls}' style='flex:{count} 1 0'><span>{count}</span></div>")
    legend = "".join(f"<span class='key'><i class='{cls}'></i>{e(name)}: <b>{count}</b></span>"
                     for name, count, cls in segments)
    described = ", ".join(f"{name} {count}" for name, count, _ in segments)
    return (f"<div class='bar' role='img' aria-label='{e(described)} (of {total})'>{''.join(parts)}</div>"
            f"<p class='legend'>{legend}</p>")


def accuracy_section(s: dict) -> str:
    j, l, pa = s["models"]["jev"], s["models"]["llm"], s["paired_all"]
    n = j["total"]
    split = pa["only_jev"] + pa["only_llm"]
    p = pa["exact_mcnemar_p"]
    half = lambda m: round((m["wilson95"][1] - m["wilson95"][0]) * 50)
    rows = "".join(
        f"<tr><th>{name}</th><td class='num'><b>{m['correct']}</b> of {n}</td><td class='num'>{pct(m['correct'], n)}</td>"
        f"<td class='num'>{ci(m)}</td></tr>"
        for name, m in ((JEV, j), (LLM, l)))
    unanswered = ""
    if j["never_answered"] or l["never_answered"]:
        unanswered = (f"<p>A message a model never answered counts as wrong: {JEV} left {len(j['never_answered'])} unanswered, "
                      f"{LLM} {len(l['never_answered'])}.</p>")
    out = [
        "<section><h2>1. Accuracy: how many did each get right?</h2>",
        f"<table class='compact'><thead><tr><th></th><th>Right</th><th>As a percentage</th><th>95% range</th></tr></thead><tbody>{rows}</tbody></table>",
        f"<p class='explain'><b>95% range</b> — the range the real accuracy most likely falls in if you tested many more messages like these. "
        f"{JEV} got {pct(j['correct'], n)} of these {n} right, but its accuracy on messages like them is most likely somewhere between "
        f"{j['wilson95'][0] * 100:.0f}% and {j['wilson95'][1] * 100:.0f}%. "
        f"With only {n} messages the range is wide, about ±{half(j)} points.</p>",
        unanswered,
        f"<h3>Message by message</h3>",
        f"<p>Both models answered the same {n} messages, so the fairest comparison looks at them one at a time. Each message falls in one of four groups:</p>",
        bar([("Both right", pa["both_correct"], "both"), (f"Only {JEV} right", pa["only_jev"], "jev"),
             (f"Only {LLM} right", pa["only_llm"], "llm"), ("Both wrong", pa["both_wrong"], "none")], n),
        f"<p class='explain'>The {pa['both_correct']} messages both got right and the {pa['both_wrong']} both got wrong say nothing about which model is better: "
        f"they treated them the same. Only the {split} messages where exactly one model was right can tell them apart.</p>",
    ]
    if split:
        out.append(bar([(f"Only {JEV} right", pa["only_jev"], "jev"), (f"Only {LLM} right", pa["only_llm"], "llm")], split))
        lead = max(pa["only_jev"], pa["only_llm"])
        verdict = ("That is below the bar, so this counts as a clear difference on this sample."
                   if p < CLEAR_BAR else
                   "That is above the bar, so this sample does not show a clear difference. "
                   "It does not prove the two are equally good; more messages might show one.")
        out.append(
            f"<p class='explain'><b>How lopsided is {pa['only_jev']} to {pa['only_llm']}?</b> If the two models were equally good, "
            f"which one gets each of the {split} split messages right would be a coin flip. Flip {split} coins, and a split of "
            f"{lead} to {split - lead} or more lopsided, either way, comes up {chance_in_100(p)} "
            f"(this number is called the <b>p-value</b>: p = {p:.4f}). The usual bar for calling a difference clear is below 5 in 100. "
            f"{verdict} The name of this test, if you want to look it up: exact McNemar's test.</p>")
    else:
        out.append("<p class='explain'>The two models were right on exactly the same messages, so there is nothing here to tell them apart.</p>")
    out.append("</section>")
    return "".join(out)


def speed_section(s: dict) -> str:
    j, l = s["models"]["jev"], s["models"]["llm"]
    n = j["total"]
    refused = j["availability"]["attempts_refused_429"] + l["availability"]["attempts_refused_429"]
    retried = j["availability"]["examples_needing_retry"] + l["availability"]["examples_needing_retry"]
    no_retries = refused == 0 and retried == 0
    measure = "usable_ms"
    k = n - max(1, math.ceil(0.95 * j[measure]["n"])) + 1 if j[measure]["n"] else 0

    def row(title: str, key: str, fmt=ms) -> str:
        return (f"<tr><th>{title}</th><td class='num'>{fmt(j[measure][key])}</td><td class='num'>{fmt(l[measure][key])}</td></tr>")

    rows = [row("Median (typical answer)", "median"), row("p95 (slow end)", "p95"), row("Worst (slowest single answer)", "worst"),
            f"<tr><th>Total wait for all {n} answers</th><td class='num'>{j['sum_usable_s']:.1f} s</td><td class='num'>{l['sum_usable_s']:.1f} s</td></tr>"]
    if not no_retries:
        rows.insert(0, "<tr><th colspan='3' class='sub'>Time to a usable answer, retries included</th></tr>")
        rows += ["<tr><th colspan='3' class='sub'>Served time: the one request that succeeded</th></tr>",
                 f"<tr><th>Median / p95 / worst</th><td class='num'>{ms(j['served_ms']['median'])} / {ms(j['served_ms']['p95'])} / {ms(j['served_ms']['worst'])}</td>"
                 f"<td class='num'>{ms(l['served_ms']['median'])} / {ms(l['served_ms']['p95'])} / {ms(l['served_ms']['worst'])}</td></tr>",
                 f"<tr><th>Requests refused with HTTP 429</th><td class='num'>{j['availability']['attempts_refused_429']}</td><td class='num'>{l['availability']['attempts_refused_429']}</td></tr>",
                 f"<tr><th>Messages that needed a retry</th><td class='num'>{j['availability']['examples_needing_retry']}</td><td class='num'>{l['availability']['examples_needing_retry']}</td></tr>"]
    out = [
        "<section><h2>2. Speed: how long did each take to answer?</h2>",
        f"<table class='compact'><thead><tr><th></th><th>{JEV}</th><th>{LLM}</th></tr></thead><tbody>{''.join(rows)}</tbody></table>",
        "<ul class='explain'>",
        f"<li><b>Median</b> — the middle answer: half came faster, half slower. {JEV}'s was {ms(j[measure]['median'])}, {LLM}'s {ms(l[measure]['median'])}.</li>",
        f"<li><b>p95</b> — 95 of every 100 answers were at least this fast ({ms(j[measure]['p95'])} for {JEV}, {ms(l[measure]['p95'])} for {LLM}). "
        f"With {n} answers it rests on the slowest {k}, so treat it as rough.</li>",
        f"<li><b>Worst</b> — the single slowest answer in the run: {ms(j[measure]['worst'])} for {JEV}, {ms(l[measure]['worst'])} for {LLM}. One slow answer can come from the network, not the model.</li>",
        f"<li><b>Total wait</b> — all {n} answer times added up, as if you waited for each in turn: {j['sum_usable_s']:.1f} s for {JEV}, {l['sum_usable_s']:.1f} s for {LLM}.</li>",
    ]
    if no_retries:
        out.append("<li><b>No refusals, no retries.</b> Every request was answered on its first try, so the time to a usable answer is simply "
                   "how long that one request took. (When a server is busy it can refuse with HTTP 429, “too many requests”, and the "
                   "runner waits and tries again; that waiting would count here too.)</li>")
    else:
        out.append(f"<li><b>Time to a usable answer</b> counts from the first try to the answer, including any refusals and the waits before each retry. "
                   f"<b>Served time</b> counts only the one request that succeeded. <b>HTTP 429</b> is a server saying “too many requests, try later”; "
                   f"the runner then waits and tries again. {JEV}: {j['availability']['attempts_refused_429']} refusals, "
                   f"{j['availability']['examples_needing_retry']} messages retried; {LLM}: {l['availability']['attempts_refused_429']} refusals, "
                   f"{l['availability']['examples_needing_retry']} messages retried.</li>")
    if j.get("provider_ms_median") is not None:
        out.append(f"<li><b>Where {JEV}'s time went</b> — of its median {ms(j['served_ms']['median'])}, the gateway reports a median of "
                   f"{ms(j['provider_ms_median'])} spent at TypeSafe, Jev's maker; the rest is the network and the gateway.</li>")
    out.append("<li>Times are measured from the computer that ran the comparison, one request at a time; another network gives other times.</li>")
    out.append("</ul></section>")
    return "".join(out)


def cost_section(s: dict) -> str:
    j, l = s["models"]["jev"], s["models"]["llm"]
    n = j["total"]
    charged = lambda m: usd(m["charged_usd"]) if m.get("charged_usd") is not None else NOT_RECORDED
    notes = []
    missing = [name for name, m in ((JEV, j), (LLM, l)) if m.get("charged_usd") is None]
    same = [name for name, m in ((JEV, j), (LLM, l))
            if m.get("charged_usd") is not None and usd(m["charged_usd"]) == usd(m["catalog_cost_usd"])]
    differ = [f"{name} was charged {usd(m['charged_usd'])} against a catalog cost of {usd(m['catalog_cost_usd'])}"
              for name, m in ((JEV, j), (LLM, l))
              if m.get("charged_usd") is not None and usd(m["charged_usd"]) != usd(m["catalog_cost_usd"])]
    if len(same) == 2:
        notes.append("In this run both charges match the catalog cost.")
    elif same:
        notes.append(f"{same[0]}'s charge matches its catalog cost.")
    if differ:
        notes.append("; ".join(differ) + ".")
    for name in missing:
        notes.append(f"This run did not save {name}'s charge or the generation ID that finds it; Vercel's dashboard shows it.")
    return "".join([
        "<section><h2>3. Cost: what did the run cost?</h2>",
        f"<table class='compact'><thead><tr><th></th><th>{JEV}</th><th>{LLM}</th></tr></thead><tbody>"
        f"<tr><th>Catalog cost for all {n} messages</th><td class='num'>{usd(j['catalog_cost_usd'])}</td><td class='num'>{usd(l['catalog_cost_usd'])}</td></tr>"
        f"<tr><th>Charged by Vercel</th><td class='num'>{charged(j)}</td><td class='num'>{charged(l)}</td></tr>"
        "</tbody></table>",
        "<ul class='explain'>",
        "<li><b>Catalog cost</b> — the tokens each model reported using, times its published list price "
        "(the prices are written in the run's settings). It is what the run would cost at list price, so the two models are priced the same way.</li>",
        "<li><b>Charged by Vercel</b> — what Vercel AI Gateway reported charging for each answer, added up. The runner saves it with every answer, "
        "together with the answer's generation ID, which finds the same charge in Vercel's dashboard.</li>",
        f"<li>{nowrap_names(e(' '.join(notes)))}</li>" if notes else "",
        "</ul></section>",
    ])


def confidence_section(s: dict) -> str:
    j = s["models"]["jev"]
    n, correct = j["total"], j["correct"]
    rows = [f"<tr class='base'><th>No filter (every answer)</th><td class='num'>{n}</td><td class='num'>{correct}</td><td class='num'>{whole_pct(correct, n)}</td></tr>"]
    for t in s["jev_confidence_sidebar"]:
        rows.append(f"<tr><th>{t['threshold']:g} or higher</th><td class='num'>{t['kept']}</td>"
                    f"<td class='num'>{t['correct_among_kept']}</td><td class='num'>{whole_pct(t['correct_among_kept'], t['kept'])}</td></tr>")
    top = s["jev_confidence_sidebar"][-1]
    rest, rest_right = n - top["kept"], correct - top["correct_among_kept"]
    return "".join([
        "<section><h2>4. Jev's confidence as a filter</h2>",
        f"<p>With each answer, {JEV} returns a confidence between 0 and 1. You can keep only the answers at or above a threshold and send the rest "
        "somewhere else, such as a person or a second model.</p>",
        "<table class='compact'><thead><tr><th>Keep answers with confidence</th><th>Answers kept</th><th>Right among kept</th><th>% right</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>",
        "<ul class='explain'>",
        f"<li>At {top['threshold']:g}, {JEV} keeps {top['kept']} of {n} answers and {top['correct_among_kept']} of them are right. "
        f"The other {rest} would go to another path; {rest_right} of those were right.</li>",
        f"<li><b>Not a calibration claim.</b> Confidence {top['threshold']:g} does not mean {top['threshold'] * 100:g}% right: here "
        f"{top['correct_among_kept']} of {top['kept']} = {whole_pct(top['correct_among_kept'], top['kept'])} were. "
        "This is what happened on these messages; measure it on your own before relying on a threshold.</li>",
        f"<li><b>Why there is no {LLM} column:</b> {no_llm_confidence(s)}</li>",
        "</ul></section>",
    ])


def no_llm_confidence(s: dict) -> str:
    via_gateway = (s.get("settings") or {}).get("llm_host") == GATEWAY_HOST
    route = ("Vercel AI Gateway, the route used here, drops those numbers" if via_gateway
             else "this run did not ask for them")
    return (f"{LLM} can report how likely its words were only when it is called directly at OpenAI with reasoning "
            f"turned off; {route}. And even then, its number is built up from the word pieces that spell out the label "
            f"and changes when the format of the prompt changes, so it would not be the same kind of number as {JEV}'s.")


def disagreement_section(s: dict, texts: dict[str, str]) -> str:
    items = []
    for d in s["disagreements"]:
        jr, lr = d["jev"] == d["reference"], d["llm"] == d["reference"]
        who = JEV if jr else LLM if lr else "Neither"
        items.append((0 if jr else 1 if lr else 2, d, jr, lr, who))
    items.sort(key=lambda x: (x[0], x[1]["example_id"]))
    counts = {w: sum(1 for i in items if i[4] == w) for w in (JEV, LLM, "Neither")}
    rows = []
    for number, (_, d, jr, lr, who) in enumerate(items, 1):
        conf = "" if d["jev_confidence"] is None else f" <span class='conf'>{d['jev_confidence']:.2f}</span>"
        rows.append(
            f"<tr><td class='num'>{number}</td><td class='msg'>“{e(texts.get(d['example_id'], d['example_id']))}”</td>"
            f"<td>{label(d['reference'])}</td>"
            f"<td class='{'ok' if jr else 'bad'}'>{label(d['jev'])}{conf}</td>"
            f"<td class='{'ok' if lr else 'bad'}'>{label(d['llm'])}</td>"
            f"<td class='who'>{who}</td></tr>")
    n = len(items)
    same_wrong = s["paired_all"]["both_wrong"] - counts["Neither"]
    not_listed = (f" The other {same_wrong} messages both got wrong are not listed: there, both gave the same wrong answer."
                  if same_wrong > 0 else "")
    return "".join([
        f"<section><h2>5. Every disagreement: {n} messages where the two gave different answers</h2>",
        f"<p>Only {JEV} right: {counts[JEV]} · only {LLM} right: {counts[LLM]} · both wrong, with different answers: {counts['Neither']}.{not_listed} "
        f"The correct label is the dataset's own. Jev's confidence is shown after its answer. "
        "<span class='okk'>Green</span> matches the correct label; <span class='badk'>red</span> does not.</p>",
        "<table class='dis'><colgroup><col style='width:3%'><col style='width:27%'><col style='width:20%'><col style='width:21%'><col style='width:18%'><col style='width:11%'></colgroup>",
        f"<thead><tr><th>#</th><th>Customer message</th><th>Correct label</th><th>{JEV} (confidence)</th><th>{LLM}</th><th>Who was right</th></tr></thead>",
        f"<tbody>{''.join(rows)}</tbody></table></section>",
    ])


CSS = """
:root{color-scheme:light;--ink:#111;--muted:#3d3d3b;--line:#b9b8b3;--bg:#fcfcfb;--panel:#f1f0ec;
--jev:#2a78d6;--llm:#eb6834;--both:#6b6a66;--none:#d6d5cf;--ok:#e3f3e3;--okk:#0a6b0a;--bad:#fbe6e4;--badk:#a32222}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:26px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1800px;margin:0 auto;padding:40px 56px 80px}
h1{font-size:52px;line-height:1.15;margin:0 0 8px}
.run{color:var(--muted);font-size:24px;margin:0 0 32px;overflow-wrap:anywhere}
h2{font-size:38px;margin:0 0 16px}h3{font-size:30px;margin:28px 0 8px}
section{margin:56px 0 0;padding-top:40px;border-top:3px solid var(--line)}
.answers{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:28px;margin:0}
.card{background:var(--panel);border-radius:16px;padding:28px 32px}
.card h2{font-size:26px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 8px}
.card .big{font-size:36px;font-weight:700;line-height:1.2;margin:0 0 10px}
.card .say{font-size:28px;margin:0}
table{border-collapse:collapse;width:100%;margin:12px 0 20px}
th,td{border-bottom:2px solid var(--line);padding:12px 16px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
thead th{font-size:22px;color:var(--muted);border-bottom:3px solid var(--ink)}
.compact{width:100%;max-width:1500px}
.compact td,.compact th{padding:12px 28px 12px 0}
.num{font-variant-numeric:tabular-nums;white-space:nowrap}
th.sub{font-size:22px;color:var(--muted);padding-top:20px}
tr.base th,tr.base td{color:var(--muted)}
.explain{max-width:1500px}
ul.explain{padding-left:1.1em}ul.explain li{margin:0 0 10px}
.muted{color:var(--muted)}
.bar{display:flex;gap:3px;height:64px;margin:16px 0 8px;max-width:1500px}
.seg{display:flex;align-items:center;justify-content:center;border-radius:6px;color:#fff;font-weight:700;font-size:28px;min-width:48px}
.seg.none{color:var(--ink)}
.jev{background:var(--jev)}.llm{background:var(--llm)}.both{background:var(--both)}.none{background:var(--none)}
.legend{display:flex;flex-wrap:wrap;gap:8px 32px;font-size:24px;margin:0 0 16px}
.key i{display:inline-block;width:22px;height:22px;border-radius:4px;margin-right:8px;vertical-align:-3px}
code{font:0.92em ui-monospace,Menlo,Consolas,monospace}
.dis{font-size:23px}.dis th,.dis td{padding:10px 12px}
.dis .msg{font-size:24px}
td.ok{background:var(--ok)}td.bad{background:var(--bad)}
.ok code{color:var(--okk);font-weight:700}.bad code{color:var(--badk)}
.okk{color:var(--okk);font-weight:700}.badk{color:var(--badk);font-weight:700}
.conf{white-space:nowrap;color:var(--muted)}
.who{font-weight:700}.nm,.run code{white-space:nowrap}
section.setup{margin-top:40px;padding-top:28px}
.settings{max-width:1500px;font-size:24px;margin:4px 0 0}.settings th{width:1%;white-space:nowrap;padding:10px 32px 10px 0;color:var(--muted);font-weight:600}
.settings td{padding:10px 0}
footer{margin-top:48px;color:var(--muted);font-size:24px}
@media (max-width:1100px){.answers{grid-template-columns:1fr}main{padding:24px 16px}.compact{width:100%}}
"""


def render(s: dict, texts: dict[str, str], results_name: str) -> str:
    j, l = s["models"]["jev"], s["models"]["llm"]
    n = j["total"]
    cards = []
    for title, (big, say) in (("Accuracy", accuracy_answer(s)), ("Speed", speed_answer(s)), ("Cost", cost_answer(s))):
        cards.append(f"<div class='card'><h2>{title}</h2><p class='big'>{nowrap_names(e(big))}</p><p class='say'>{nowrap_names(e(say))}</p></div>")
    run = f"Run {s['pass']} · " if s.get("pass") is not None else ""
    return "".join([
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>Jev vs GPT-5.4-mini</title><style>{CSS}</style></head><body><main>",
        f"<h1>{JEV} vs {LLM} on {n} bank messages</h1>",
        f"<p class='run'>{run}{e(run_time(s['started_utc']))} · {JEV} <code>{e(j['answered_model'])}</code>, {nowrap_names(LLM)} <code>{e(l['answered_model'])}</code> · "
        f"answers from <code>results/{e(results_name)}</code></p>",
        f"<div class='answers'>{''.join(cards)}</div>",
        setup_section(s), accuracy_section(s), speed_section(s), cost_section(s), confidence_section(s), disagreement_section(s, texts),
        f"<footer>Made by score_comparison.py from the saved answers in results/{e(results_name)}; no model was called to make this page. "
        "The same numbers are printed as a table in the terminal.</footer>",
        "</main></body></html>\n",
    ])


def message_texts(manifest: Path = HERE / "manifest.json") -> dict[str, str]:
    return {ex["example_id"]: ex["text"] for ex in json.loads(manifest.read_text())["examples"]}


def report_path(results_file: Path) -> Path:
    return results_file.with_suffix(".report.html")


def write(summary: dict, results_file: Path) -> Path:
    out = report_path(results_file)
    out.write_text(render(summary, message_texts(), results_file.name), encoding="utf-8")
    return out
