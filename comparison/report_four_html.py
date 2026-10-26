"""A plain-language report of four models on the same bank messages.

Reads saved answers and frozen settings without sending requests.
"""
import argparse
import json
import math
import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from html import escape
from pathlib import Path

import report_html as old
import score
import score_four as scoring
import score_gateway

NAMES = {'jev': 'Jev', 'llm': 'GPT-5.4-mini', 'decisions': 'Decisions API (GPT-6 Luna)', 'luna': 'GPT-6 Luna'}
BASELINE_RUN = Path('results/test-20260930T224309Z-gateway-temp0-pass5.jsonl')
TITLE = 'Jev, GPT-5.4-mini, Decisions API and GPT-6 Luna'
CSS = """
main{max-width:2300px}.answers .big{font-size:34px}.answers .say{font-size:27px}
:root{--decisions:#008675;--luna:#8453bc}.decisions{background:var(--decisions)}.luna{background:var(--luna)}
.metric{display:grid;grid-template-columns:410px minmax(0,1fr) 440px;align-items:center;gap:24px;margin:22px 0}
.model{font-weight:650}.track{height:36px;background:var(--panel);position:relative;border-radius:6px}
.fill{height:100%;border-radius:6px}.whisker{position:absolute;top:16px;height:4px;background:#111}
.whisker:before,.whisker:after{content:'';position:absolute;top:-7px;height:18px;border-left:3px solid #111}
.whisker:after{right:0}.value{font-variant-numeric:tabular-nums;font-size:25px}
.pairs{display:grid;grid-template-columns:1fr 1fr;gap:28px 48px}.pair{min-width:0;padding:20px 24px;background:var(--panel);border-radius:12px}
.pair h3{font-size:27px;margin:0 0 8px}.pair p{font-size:24px;margin:8px 0}.pair .bar{height:42px;margin:12px 0 8px}.pair .seg{font-size:24px}.pair .legend{font-size:23px;gap:8px 24px}
.pair .muted{font-size:22px}.filters{display:grid;grid-template-columns:1fr 1fr;gap:40px}.filters .compact{font-size:23px}.explain{max-width:1900px}.settings{max-width:none}.dis{table-layout:fixed;font-size:22px}.dis th,.dis td{padding:12px 18px}.dis thead th{font-size:21px}.dis th:first-child{width:25%}.dis th:nth-child(2){width:15%}
@media(max-width:1200px){.metric{grid-template-columns:300px minmax(0,1fr)}.value{grid-column:2}.pairs,.filters{grid-template-columns:1fr}}

.stage.differed{gap:26px}
.differed-intro{font-size:28px;line-height:1.35;color:var(--muted)}
.split-pairs{display:grid;gap:14px}.split-row{display:grid;grid-template-columns:650px minmax(0,1fr) 440px;align-items:center;gap:28px;font-size:28px;line-height:1.2}
.split-label{font-weight:600}.split-bar{display:flex;height:48px;border-radius:6px;overflow:hidden;background:var(--panel)}
.split-segment{display:flex;align-items:center;justify-content:center;font-size:28px;font-weight:700;color:#fff;min-width:0}
.split-counts{display:flex;gap:24px;font-size:28px;font-weight:700}.split-chart{display:grid;grid-template-columns:minmax(0,1fr) 110px;align-items:center;gap:20px}
.split-verdict{font-size:28px}.split-examples{display:grid;grid-template-columns:minmax(0,1fr) 320px repeat(4,200px);align-items:center;gap:14px 20px;font-size:26px;line-height:1.25}
.example-heading{font-size:24px;font-weight:600}.example-mark{font-size:36px;text-align:center;font-weight:700}.example-mark.wrong{color:var(--muted);font-weight:400}.example-message{padding:14px 0;border-top:1px solid var(--line)}
.split-examples code{font-size:24px}
.example-rule{font-size:24px;color:var(--muted);line-height:1.3}
/* Presentation panels share the same four model colours as the details. */
*{box-sizing:border-box}html{scroll-behavior:auto}main{padding-top:0}
.stage{min-height:100vh;margin:0;padding:76px 24px 64px;border-top:0;display:flex;flex-direction:column;justify-content:center;gap:42px;position:relative;border-bottom:2px solid var(--line)}
.stage .eyebrow{font-size:26px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);font-weight:650}
.stage h1,.stage h2{font-size:76px;line-height:1.12;letter-spacing:-.035em;margin:0;max-width:2100px}
.stage .support{font-size:30px;line-height:1.4;margin:0;color:var(--muted)}
.stage .stage-date{font-size:30px;color:var(--muted)}
.stage .metric{grid-template-columns:380px minmax(0,1fr) 500px;gap:40px;margin:30px 0}
.stage .model{font-size:36px;line-height:1.2}.stage .track{height:58px;background:#eae8e2}
.stage .whisker{top:27px}.stage .value{font-size:64px;line-height:1.1;font-weight:650;letter-spacing:-.025em}
.stage .value small{display:block;font-size:26px;font-weight:400;letter-spacing:0;margin-top:12px;color:var(--muted)}
.chips{display:grid;grid-template-columns:1fr 1fr;gap:30px}.chip{background:var(--panel);padding:38px 42px;border-radius:16px;border-left:10px solid var(--model-color);min-height:200px;display:flex;flex-direction:column;justify-content:center;gap:18px}
.chip .chip-name{font-size:40px;font-weight:650;line-height:1.2}.chip .chip-line{font-size:28px;line-height:1.35}
.two-ways{display:grid;grid-template-columns:1fr 1fr;gap:48px}.route-card{background:var(--panel);border-top:10px solid var(--model-color);border-radius:16px;padding:42px 48px}
.route-card h3{font-size:40px;line-height:1.2;margin:0 0 34px}.stat-row{display:flex;align-items:baseline;justify-content:space-between;gap:20px;padding:24px 0;border-top:1px solid var(--line)}
.stat-row .number small{font-size:26px;font-weight:400;letter-spacing:0;color:var(--muted);margin-left:16px}
.stat-row .label{font-size:28px}.stat-row .number{font-size:72px;font-weight:650;line-height:1.2;letter-spacing:-.025em}
.confidence-rows{display:grid;gap:30px}.confidence-row{border-left:10px solid var(--model-color);border-radius:12px;background:var(--panel);padding:32px 40px;display:grid;grid-template-columns:420px 200px 1fr;align-items:center;gap:32px}
.confidence-row .model{font-size:36px}.confidence-row .threshold{font-size:64px;font-weight:650}.confidence-row .kept{font-size:56px;line-height:1.2;font-weight:650}
.no-confidence{font-size:28px;color:var(--muted)}.details-divider{margin:0;padding:110px 0 45px;border-top:6px solid var(--ink)}.details-divider h2{font-size:64px;margin:0}
.compact{max-width:none}#panel-2 .support{font-size:44px;line-height:1.25;font-weight:600;color:var(--ink)}.threshold small{display:block;font-size:24px;font-weight:400;letter-spacing:0}
a{color:#245ca3;text-underline-offset:4px}.price-source{white-space:nowrap}.sources code{overflow-wrap:anywhere}
@media(max-width:1500px){.stage h1,.stage h2{font-size:54px}.stage .metric{grid-template-columns:290px 1fr 340px;gap:26px}.stage .value{font-size:56px}.stage .model{font-size:28px}.chip .chip-name{font-size:32px}.chip .chip-line{font-size:24px}.stat-row .number{font-size:56px}.confidence-row{grid-template-columns:280px 150px 1fr}.confidence-row .kept{font-size:44px}}
@media(max-width:1000px){.stage{min-height:auto;padding:60px 0}.stage .metric{grid-template-columns:1fr 1fr}.stage .model{grid-column:1/-1}.stage .value{grid-column:2}.chips,.two-ways{grid-template-columns:1fr}.confidence-row{grid-template-columns:1fr}.stage .support{font-size:24px}}
@media print{#panel-2 .support{font-size:24px}.stage{min-height:0;break-after:page;padding:24px 0;gap:24px}.stage h1,.stage h2{font-size:44px}.stage .metric{grid-template-columns:220px 1fr 260px;gap:18px}.stage .value,.stat-row .number,.confidence-row .kept{font-size:56px}.stage .model,.chip .chip-name,.route-card h3{font-size:24px}.stage .support,.stage .value small,.stat-row .label,.chip .chip-line,.stage-date{font-size:18px}.chip,.route-card{padding:24px}.confidence-row{grid-template-columns:200px 100px 1fr;padding:20px;gap:16px}.confidence-row .threshold{font-size:40px}.details-divider{break-before:page}body{-webkit-print-color-adjust:exact;print-color-adjust:exact}.pair,.chip,.route-card,.confidence-row{break-inside:avoid}}
/* Real presentation screens: 1920×1080 and 1480×1010 CSS pixels at 2×. */
.stage{padding:40px 24px;gap:26px}
.stage .metric{grid-template-columns:300px minmax(0,1fr) 460px;gap:28px;margin:22px 0}
.stage .model,.chip-name,.route-card h3,.stat-row .number,.split-label,.split-verdict,.example-heading,.split-counts,.key-number{white-space:nowrap}
.stage .value{white-space:nowrap}.stage .value small{font-size:26px;margin-top:6px;white-space:nowrap}
#panel-2 .support{font-size:28px;white-space:nowrap}
.split-row{grid-template-columns:490px minmax(0,1fr) 360px;gap:24px}
.split-examples{grid-template-columns:minmax(0,1fr) 290px repeat(4,180px);gap:12px 16px}
.split-examples code{white-space:nowrap}
.route-card{padding:30px 32px}.route-card h3{font-size:36px}.stat-row{padding:20px 0}.stat-row .number{font-size:64px}
.stage.differed{gap:20px}
#panel-7{gap:12px;padding-top:32px;padding-bottom:32px}
.decision-intro{font-size:28px;line-height:1.3}
.decision-message{font-size:30px;line-height:1.3;margin-bottom:14px;display:flex;justify-content:space-between;gap:24px}
.correct-label{font-size:26px;white-space:nowrap;align-self:center}
.decision-cards{display:grid;grid-template-columns:1fr 1fr;gap:24px}
.decision-card{border-top:6px solid var(--model-color);background:var(--panel);border-radius:10px;padding:16px 24px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px 20px;align-items:center}
.decision-model{font-size:30px;font-weight:650;color:var(--model-color)}
.decision-pick{grid-column:1/-1;font-size:26px;white-space:nowrap}
.decision-pick .example-mark{font-size:30px}
.decision-pick code,.correct-label code{font-size:24px}.probability-row code{font-size:inherit}
.decision-score{grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;font-size:26px;line-height:1.1}
.score-number{font-size:56px;font-weight:650}
.probability-heading{grid-column:1/-1;font-size:24px;color:var(--muted)}
.probability-row{grid-column:1/-1;display:flex;justify-content:space-between;gap:20px;font-size:28px;line-height:1.2;white-space:nowrap}
.confidence-rows{gap:12px}.confidence-row{grid-template-columns:220px minmax(0,1fr);padding:14px 24px;gap:24px}
.confidence-row .model{font-size:28px}.threshold-summary{font-size:28px;white-space:nowrap}
.decision-note{font-size:24px;line-height:1.3}.example-rule{font-size:24px}
.right-wrong{table-layout:fixed}.right-wrong th{white-space:nowrap;font-size:24px;overflow-wrap:normal}
.right-wrong th:first-child{width:29%}.right-wrong th:not(:first-child){width:17.75%}

.right-wrong thead th:not(:first-child){text-align:center}
.right-wrong td{font-size:36px;text-align:center;font-variant-numeric:tabular-nums}
.right-wrong .clear{background:var(--panel)}.matrix-legend{font-size:24px}
@media(max-width:1500px){
.stage{gap:24px;padding:32px 12px}.stage h1,.stage h2{font-size:54px}
.stage .metric{grid-template-columns:240px minmax(0,1fr) 420px;gap:24px;margin:20px 0}
#panel-2 .support{font-size:24px}.split-row{grid-template-columns:400px minmax(0,1fr) 280px;gap:20px;font-size:24px}
.split-verdict{font-size:24px}.split-chart{grid-template-columns:minmax(0,1fr) 100px;gap:12px}
.split-examples{grid-template-columns:minmax(0,1fr) 290px repeat(4,165px);gap:10px 12px;font-size:24px}
.example-heading{font-size:24px}.split-examples code{font-size:24px}
.route-card h3{font-size:28px}.stat-row .number{font-size:56px}
.confidence-row{grid-template-columns:180px minmax(0,1fr);gap:20px;padding:12px 18px}
.confidence-row .model,.threshold-summary{font-size:24px}
.decision-card{padding:14px 18px;gap:6px 12px}.decision-pick{font-size:24px}.decision-message{font-size:28px}
.probability-row{font-size:26px}.right-wrong th{font-size:24px}.right-wrong th:first-child{width:28%}
}

/* Group boundaries remain clear at 1920×1080 and 1480×1010 CSS pixels. */
.stage{gap:48px}
.stage>.eyebrow{margin-bottom:-32px}
#panel-1 .stage-date{margin-top:-32px}
.stage .metric{margin:16px 0}
.chip{gap:12px}.chips{gap:16px}
.stage.differed{gap:16px}
.stage.differed>.eyebrow{margin-bottom:0}
.examples-group{margin-top:32px;display:grid;gap:16px}
.group-heading{font-size:26px;font-weight:650;line-height:1.3;margin:0}
.split-examples{grid-template-columns:minmax(0,1fr) 280px repeat(4,160px);gap:0 12px}
.split-examples>.example-heading{padding-bottom:18px}
.split-examples>.example-message{padding:12px 0}
#panel-7{gap:12px;padding:24px}
#panel-7>.eyebrow{margin-bottom:0}
.decision-example{display:grid;gap:12px;margin-top:24px}
.decision-message{margin:0}
.decision-card{display:flex;flex-direction:column;align-items:stretch;gap:8px;padding:14px 20px}
.decision-card-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}
.decision-score{display:flex;align-items:center;gap:16px;font-size:24px}
.decision-model{font-size:28px}
.probability-row{font-size:26px;gap:12px}
.probability-row>span:first-child{display:flex;align-items:center;gap:10px}
.probability-row>span:first-child:before{content:'';width:14px;height:14px;flex:none;background:var(--model-color)}
.part-1{--segment-color:color-mix(in srgb,var(--model-color) 40%,white)}
.part-2{--segment-color:#c5c5c1}
.probability-row.part-1>span:first-child:before,.probability-row.part-2>span:first-child:before{background:var(--segment-color)}
.distribution{margin-top:4px}
.distribution-axis{display:flex;justify-content:space-between;font-size:24px;line-height:1.2;margin-bottom:4px;color:var(--muted)}
.distribution-bar{display:flex;height:28px;border-radius:4px;overflow:hidden}
.distribution-segment{background:var(--segment-color,var(--model-color));height:100%}
.threshold-group{margin-top:36px;display:grid;gap:12px}
.confidence-row{padding:10px 20px}
.decision-note{line-height:1.25}
.decision-pick,.threshold-summary{line-height:1.2}
@media(max-width:1500px){
.split-examples{grid-template-columns:minmax(0,1fr) 280px repeat(4,160px);gap:0 12px}
.split-row{grid-template-columns:390px minmax(0,1fr) 280px}
.split-pairs{gap:10px}.split-bar{height:40px}
.decision-score{gap:10px}.decision-model{font-size:26px}
.probability-row{font-size:24px}
#panel-7{padding:10px 12px;gap:10px}
.decision-card{padding:12px 16px;gap:6px}
.decision-card-heading{gap:10px}
#panel-1 .support,#panel-5 .support{font-size:26px}
#panel-5 .support a{white-space:nowrap}
.decision-intro{font-size:26px}
.group-heading{font-size:24px}
.threshold-group{margin-top:38px}
}

"""


def eastern_start(record):
    started = datetime.strptime(record['started_utc'], '%Y%m%dT%H%M%S%fZ').replace(tzinfo=timezone.utc)
    return started.astimezone(ZoneInfo('America/New_York'))


def load_baseline(path=BASELINE_RUN):
    """Resolve saved baselines relative to comparison; None/empty disables comparison."""
    if path is None or str(path) == '':
        return None
    path = Path(path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    return score_gateway.summarize(path) if path.is_file() else None


def table(headings, rows, cls='compact'):
    return '<table class="'+cls+'"><thead><tr>'+''.join('<th>'+escape(h)+'</th>' for h in headings)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table>'


def section(title, content):
    return '<section><h2>'+escape(title)+'</h2>'+content+'</section>'


def verdict(a, b, pair):
    if pair['exact_mcnemar_p'] < old.CLEAR_BAR and pair['only_a'] != pair['only_b']:
        leader, other = (a,b) if pair['only_a'] > pair['only_b'] else (b,a)
        return f'{NAMES[leader]} clearly ahead of {NAMES[other]} on this sample'
    return 'No clear difference on this sample'


def accuracy_answer(s):
    models = s['models']
    counts = [v['correct'] for v in models.values()]
    headline = f"Between {min(counts)} and {max(counts)} of {models['jev']['total']} right."
    clear = [verdict(*pair.split('/'), sets['all'])+'.' for pair,sets in s['pairs'].items()
             if sets['all']['exact_mcnemar_p'] < old.CLEAR_BAR and sets['all']['only_a'] != sets['all']['only_b']]
    return headline, ' '.join(clear) if clear else 'No clear difference between any two models on this sample.'


def answer_cards(s):
    timed = [(v['usable_ms']['median'],m) for m,v in s['models'].items() if v['usable_ms']['median'] is not None]
    if timed:
        fast, slow = min(timed), max(timed)
        speed = (f'{NAMES[fast[1]]} answered fastest: {old.ms(fast[0])} typical.', f'{NAMES[slow[1]]} was slowest: {old.ms(slow[0])}. Typical means the middle answer time; 1,000 milliseconds (ms) is one second.')
    else:
        speed = ('No usable answers to time.', '')
    j,l=s['models']['jev'],s['models']['llm']
    cost=(f"Jev cost {old.usd(j['charged_usd'])} for {j['total']} messages.",
          f"GPT-5.4-mini cost {old.times_as_much(l['charged_usd'],j['charged_usd'])} as much." if j['charged_usd'] and l['charged_usd'] is not None else 'Gateway charges are incomplete.')
    return '<div class="answers">'+''.join(f"<div class='card'><h2>{title}</h2><p class='big'>{escape(big)}</p><p class='say'>{escape(say)}</p></div>" for title,(big,say) in [('Accuracy',accuracy_answer(s)),('Speed',speed),('Cost',cost)])+'</div>'


def metric(model, value, maximum, words, interval=None):
    width=100*value/maximum if maximum else 0
    whisker=''
    if interval:
        lo,hi=interval
        whisker=f"<span class='whisker' style='left:{100*lo:.4f}%;width:{100*(hi-lo):.4f}%'></span>"
    accessible_words = ' '.join(re.sub(r'<[^>]*>', ' ', words).split())
    return f"<div class='metric'><div class='model'>{NAMES[model]}</div><div class='track' role='img' aria-label='{escape(NAMES[model]+': '+accessible_words)}'><div class='fill {model}' style='width:{width:.4f}%'></div>{whisker}</div><div class='value'>{words}</div></div>"


def pair_card(a,b,v):
    split=v['only_a']+v['only_b']
    p=v['exact_mcnemar_p']
    bars=old.bar([(f'Only {NAMES[a]} right',v['only_a'],a),(f'Only {NAMES[b]} right',v['only_b'],b)],split)
    lead=max(v['only_a'],v['only_b'])
    coin=(f"If neither had an accuracy advantage, a coin flip for each of these {split} split messages would give {lead} to {split-lead} or a more lopsided split, either way, {old.chance_in_100(p)} (p = {p:.4f})."
          if split else f"There are no split messages to tell them apart; a coin-flip test gives p = {p:.4f} ({old.chance_in_100(p)}).")
    return '<div class="pair"><h3>'+escape(NAMES[a]+' / '+NAMES[b])+'</h3>'+bars+f"<p class='muted'>Both right: {v['both_correct']} · both wrong: {v['both_wrong']}</p><p><b>{escape(verdict(a,b,v))}.</b></p><p>{escape(coin)}</p></div>"


def setup(header):
    cfg=header['config']
    chat='Temperature is how much chance goes into the choice of words; 0 takes the most likely next word piece rather than sampling (identical answers are not guaranteed). Reasoning effort controls how much internal thinking the chat model does; none requests no extra thinking. A token is a word piece. '+ '; '.join(f"{NAMES[m]}: temperature {cfg[m]['temperature']}, reasoning {cfg[m]['reasoning_effort']}, {cfg[m]['max_completion_tokens']}-token answer limit" for m in ('llm','luna'))
    rows=[('Route','All four through Vercel AI Gateway, a service that forwards requests to the model makers. The provider (the company answering) was fixed: Jev to TypeSafe, its maker; the other three to OpenAI, their maker.'),
          ('What each was asked',f"All four got the same customer message, instruction and 77 labels: “{cfg['instruction']}” Jev and Decisions API got a typed Choice question, which asks for one label from an allowed list. The two chat models got the same system message (an instruction about their task); replies had to use one of the 77 labels in a fixed data format (a strict JSON label schema)."),
          ('How Jev picks','Jev gives labels probabilities (how likely it thinks each label is) and chooses the most probable label; its choice has no randomness or extra thinking setting.'),
          ('Temperature and reasoning',chat+'. Decisions API uses API-default reasoning (parameter omitted); no temperature is set.'),
          ('Order','One request at a time, in a balanced eight-message cycle; each model appears twice in each position.'),
          ('Retries',f"Up to {cfg['retry_policy']['max_attempts']} attempts: if a service is busy, the run waits and tries again, the same way for every model. Waits increase from 1 to 16 seconds; a service’s requested wait is honoured, up to 30 seconds."),
          ('Frozen settings','FROZEN-gateway-four.json contains hashes refreshed for this export, not a new pre-test declaration. The saved run header retains the original run hashes.'),
          ('Model version',"The version behind the typesafe-ai/jev alias cannot be confirmed.")]
    return section('How this run was set up',"<table class='settings'><tbody>"+''.join('<tr><th>'+escape(k)+'</th><td>'+escape(v).replace('typesafe-ai/jev','<code>typesafe-ai/jev</code>')+'</td></tr>' for k,v in rows)+'</tbody></table><p>'+api_links(header)+'</p>')


def confidence(call):
    """Use the API's saved answer confidence, not a rounded label distribution."""
    value=call.get('confidence')
    if value is None:
        value=(call.get('raw_answer') or {}).get('confidence')
    return value


def speed_details(s,calls):
    models=s['models'];rows=[]
    for title,key in [('Median (typical answer)','median'),('p95 (slow end)','p95'),('Worst (slowest single answer)','worst')]:
        rows.append([title,*[old.ms(v['usable_ms'][key]) for v in models.values()]])
    rows.append(['Total wait (seconds)',*[f"{sum(c['total_ms'] for c in calls if c['model_key']==m and c.get('http_status')==200 and c.get('valid') and not c.get('refusal'))/1000:.1f} s" for m in models]])
    rows.append(['Usable answers timed',*[v['usable_ms']['n'] for v in models.values()]])
    maximum=max((v['usable_ms']['median'] or 0 for v in models.values()),default=0)
    text="<p>Times below are in milliseconds (ms): 1,000 ms is one second. Time to a usable answer counts from the first try to the answer, including any refusals and waits before each retry. Unanswered or refused messages have no usable answer to time.</p>"
    text+="<ul class='explain'><li><b>Median</b> — the middle answer: half came faster, half slower.</li><li><b>p95</b> — 95 of every 100 answers were at least this fast. It rests on the slowest "+'; '.join(f"{max(0,v['usable_ms']['n']-max(1,math.ceil(.95*v['usable_ms']['n']))+1)} for {NAMES[m]}" for m,v in models.items())+", so treat it as rough.</li><li><b>Worst</b> — the single slowest answer in the run. One slow answer can come from the network, not the model.</li><li><b>Total wait</b> — all usable answer times added up, as if you waited for each in turn.</li></ul>"
    text+=table(['',*NAMES.values()],rows)
    text+=''.join(metric(m,v['usable_ms']['median'] or 0,maximum,f"{old.ms(v['usable_ms']['median'])} median · {old.ms(v['usable_ms']['p95'])} p95") for m,v in models.items())
    text+="<p><b>HTTP 429</b> is a server saying “too many requests, try later”; the comparison then waits and tries again. Those waits count here too. "+'; '.join(f"{NAMES[m]}: {v['availability']['attempts_refused_429']} HTTP 429 responses, {v['availability']['retries']} retries" for m,v in models.items())+'.</p>'
    if not any(v['availability']['retries'] for v in models.values()):
        text+='<p><b>No retries.</b> Every request finished on its first try; a model declining to give an answer is separate from a busy server refusing a request.</p>'
    else:
        text+='<p><b>Served time</b> counts only the one request that succeeded.</p>'+table(['Served time',*NAMES.values()],[[key,*[old.ms(v['served_ms'][key]) for v in models.values()]] for key in ('median','p95','worst')])
    for m,provider in [('jev',"TypeSafe, Jev's maker"),('decisions','OpenAI')]:
        v=models[m]
        if v['provider_ms']['median'] is not None:
            text+=f"<p><b>Where {NAMES[m]}'s time went</b> — of its median {old.ms(v['served_ms']['median'])} for the successful request, the gateway reports a median of {old.ms(v['provider_ms']['median'])} spent at {provider}; the rest is the network and the gateway.</p>"
    return text+'<p>Times are measured from the computer that ran the comparison, one request at a time; another network gives other times.</p>'


def cost_details(s):
    models=s['models']
    text="<ul class='explain'><li><b>Catalog cost</b> — the tokens each model reported using, times its published list price (a token is a word piece; the prices are written in the run's settings). It is what the run would cost at list price, so all four models are priced the same way.</li><li><b>Charged by Vercel</b> — what Vercel AI Gateway reported charging for each answer, added up, including every attempt. The comparison saves it with every answer, together with the answer's generation ID, which finds the same charge in Vercel's dashboard.</li></ul>"
    text+=table(['',*NAMES.values()],[[title,*[old.usd(v[key]) if v[key] is not None else 'not saved by this run' for v in models.values()]] for title,key in [('Catalog cost for all messages','catalog_cost_usd'),('Charged by Vercel','charged_usd')]])
    for m,v in models.items():
        if v['charged_usd'] is None:
            text+=f"<p>This run did not save a complete charge for {NAMES[m]}; Vercel's dashboard shows it.</p>"
        else:
            text+=f"<p>{NAMES[m]}'s charge "+('matches its catalog cost.' if old.usd(v['charged_usd'])==old.usd(v['catalog_cost_usd']) else 'differs from its catalog cost, as shown above.')+'</p>'
    return text+"<p>Vercel AI Gateway’s reported charge for each call, saved with the answer. <a href='#price-sources'>Prices and usage</a>.</p>"


def confidence_details(s,header,calls):
    names="Jev and Decisions API" if any(c['model_key']=='decisions' and confidence(c) is not None for c in calls) else "Jev"
    text=f"<p>With each answer, {names} return a probability between 0 and 1, called confidence. You can keep only the answers at or above a threshold and send the rest somewhere else, such as a person or a second model.</p><div class='filters'>"
    for m in ('jev','decisions'):
        cs=[c for c in calls if c['model_key']==m and c['example_id'] in header['example_ids']]
        available=[c for c in cs if confidence(c) is not None]
        text+='<div><h3>'+escape(NAMES[m])+'</h3>'
        if not available:
            text+='<p>This run did not save '+escape(NAMES[m])+"’s per-answer probability.</p></div>"
            continue
        n=s['models'][m]['total'];right=s['models'][m]['correct']
        rows=[[f"No filter (all attempts: {s['models'][m]['answered']} answered; {len(s['models'][m]['refusals'])} declined)",n,right,old.whole_pct(right,n)]]
        for threshold in (.5,.8,.95):
            kept=[c for c in available if confidence(c)>=threshold];k=sum(bool(c.get('correct')) for c in kept)
            rows.append([f'{threshold:g} or higher',len(kept),k,old.whole_pct(k,len(kept))])
        text+=table(['Confidence filter','Messages included','Right among included','% right'],rows)
        text+=f"<ul class='explain'><li>At {threshold:g}, {NAMES[m]} keeps {len(kept)} of {n} messages as answers and {k} of them are right. The other {n-len(kept)} messages would go to another path; {right-k} of those were right.</li><li><b>Not a calibration claim.</b> Confidence {threshold:g} does not mean {threshold*100:g}% right: here {k} of {len(kept)} = {old.whole_pct(k,len(kept))} were. This is what happened on these messages; measure it on your own before relying on a threshold.</li></ul></div>"
    text+="</div><p><b>Why there is no GPT-5.4-mini or GPT-6 Luna column:</b> This run did not save comparable label probabilities for either chat model. Chat models can report how likely their word pieces were when supported by their endpoint and settings; Vercel AI Gateway, the route used here, does not supply those numbers in these saved answers. Even then, a number built up from the word pieces that spell out a label changes when the format of the prompt changes, so it would not be the same kind of number as Jev's or Decisions API's.</p>"
    return section('Confidence as a filter',"<div id='confidence-details'>"+text+'</div>')


def disagreement_intro(header,calls,count):
    by={(c['example_id'],c['model_key']):c for c in calls};counts=[0]*5;same_wrong=0
    for i in header['example_ids']:
        cs=[by.get((i,m),{}) for m in scoring.MODELS]
        if len({c.get('prediction') for c in cs})>1:
            counts[sum(bool(c.get('correct')) for c in cs)]+=1
        elif not any(c.get('correct') for c in cs):
            same_wrong+=1
    text=f"<p>{count} messages where at least two models gave different answers are listed: "+'; '.join(f"{counts[k]} with {k} {'model' if k==1 else 'models'} right" for k in range(4))+f". The other {len(header['example_ids'])-count} messages, where all four gave the same answer, are not listed; {same_wrong} of those had the same wrong answer. The correct label is the dataset's own. "
    saved=[NAMES[m] for m in ('jev','decisions') if any(c['model_key']==m and confidence(c) is not None for c in calls)]
    if saved:
        text+='Confidence is shown after the answer for '+ ' and '.join(saved)+'. '
    return text+"<span class='okk'>Green</span> matches the correct label; <span class='badk'>red</span> does not.</p>"



def external(url, label):
    return f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'


def prices(header):
    # Use the run's saved config, including its checked dates, not today's prices.
    return {m: header['config'][m].get('catalog_price_per_million', header['config'][m].get('price_per_million')) for m in scoring.MODELS}


def price_link(header, model, label='price source'):
    # One historical source field includes an explanatory parenthesis with a local filename.
    url = prices(header)[model]['source'].split()[0]
    return external(url, label)


def token_totals(header, calls):
    ids = set(header['example_ids'])
    totals = {m: {'input_tokens': 0, 'output_tokens': 0, 'calls': 0} for m in scoring.MODELS}
    for call in calls:
        if call['example_id'] not in ids:
            continue
        row = totals[call['model_key']]
        usage = call.get('usage') or {}
        for key in ('input_tokens', 'output_tokens'):
            alias = 'prompt_tokens' if key == 'input_tokens' else 'completion_tokens'
            row[key] += usage.get(key, usage.get(alias)) or 0
        row['calls'] += 1
    return totals


def cost_why(header, calls):
    rates = prices(header); totals = token_totals(header, calls)
    d,l = totals['decisions'],totals['luna']
    if rates['decisions']['input'] == rates['luna']['input'] and d['calls'] and l['calls']:
        di,li=d['input_tokens']/d['calls'],l['input_tokens']/l['calls']
        if di > li:
            return f'Same input-token price; Decisions API uses more input ({di:,.0f} vs {li:,.0f} tokens/message).'
    return 'Charges reflect each route’s token usage and input/output prices.'


def api_links(header):
    return ' · '.join([external('https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-decisions', 'Vercel Decisions endpoint'),
                      price_link(header, 'decisions', 'OpenAI Decisions guide'),
                      external('https://vercel.com/docs/ai-gateway/models-and-providers/provider-options', 'Vercel provider options')])


def price_usage_details(header, calls):
    rates=prices(header);totals=token_totals(header,calls)
    rows=[]
    for m in scoring.MODELS:
        p=rates[m];t=totals[m]
        rate=lambda key: price_link(header,m,f"${p[key]:g}")
        rows.append([escape(NAMES[m]),rate('input'),rate('output'),escape(p['checked']),f"{t['input_tokens']:,}",f"{t['output_tokens']:,}"])
    return "<div id='price-sources'><h3>Prices and token usage</h3><p>USD per million tokens; checked dates are from the saved settings. Usage totals are the saved per-answer input and output counts.</p>"+table(['Model','Input price','Output price','Price checked','Input tokens','Output tokens'],rows)+"<p>"+escape(cost_why(header,calls))+" Output prices differ; the totals above show both sides of the charge.</p></div>"


def sources(header):
    manifest=json.loads((Path(__file__).resolve().parent/'manifest.json').read_text())
    rows=[]
    for m in scoring.MODELS:
        rows.append([escape(NAMES[m]),'<code>'+escape(header['config'][m]['model'])+'</code>',price_link(header,m, 'Published prices')+' · checked '+escape(prices(header)[m]['checked'])])
    return section('Sources',"<div class='sources'>"+table(['Model','Model ID','Price source'],rows)+"<p>Data: "+external(manifest['source'],'BANKING77 (PolyAI, CC BY 4.0)')+".</p><p>APIs: "+api_links(header)+".</p><p>Measured charges: Vercel AI Gateway’s reported charge for each call, saved with the answer.</p></div>")


def split_examples(header, calls):
    """Prefer two-right splits, then fill with one/three-right splits, in run order."""
    by={(c['example_id'],c['model_key']):c for c in calls}
    groups={2:[],1:[]}
    for i in header['example_ids']:
        cs=[by.get((i,m),{}) for m in scoring.MODELS]
        right=sum(bool(c.get('correct')) for c in cs)
        if right in (1,2,3):
            groups[2 if right==2 else 1].append((i,cs))
    chosen=groups[2][:3]
    return chosen+groups[1][:3-len(chosen)], len(chosen)<3


def differed_panel(s, header, calls, short):
    rows=[]
    for pair,sets in s['pairs'].items():
        a,b=pair.split('/');v=sets['all'];total=v['only_a']+v['only_b']
        words='no clear difference'
        if v['exact_mcnemar_p'] < old.CLEAR_BAR and v['only_a'] != v['only_b']:
            words=short[a if v['only_a']>v['only_b'] else b]+' clearly ahead'
        segments=''.join(f"<span class='split-segment {m}' style='width:{100*count/total if total else 0:.4f}%' aria-label='Only {escape(short[m])} right: {count}'></span>" for m,count in [(a,v['only_a']),(b,v['only_b'])])
        counts=''.join(f"<span style='color:var(--{m})'>{count}</span>" for m,count in [(a,v['only_a']),(b,v['only_b'])])
        rows.append(f"<div class='split-row' data-pair='{pair}'><div class='split-label'>{escape(short[a]+' vs '+short[b])}</div><div class='split-chart'><div class='split-bar'>{segments}</div><div class='split-counts'>{counts}</div></div><div class='split-verdict'>{escape(words)}</div></div>")
    examples,fallback=split_examples(header,calls);texts=old.message_texts()
    cells=["<div class='example-heading'>Customer message</div><div class='example-heading'>Correct label</div>"]
    cells.extend(f"<div class='example-heading' style='color:var(--{m});text-align:center'>{escape(short[m])}</div>" for m in scoring.MODELS)
    for i,cs in examples:
        text=texts.get(i,'');text=text[:69].rstrip()+'…' if len(text)>70 else text
        ref=next((c['reference'] for c in cs if 'reference' in c),'unknown')
        cells.append(f"<div class='example-message' data-example='{escape(i)}'>{escape(text)}</div><div>{old.label(ref)}</div>")
        cells.extend(f"<div class='example-mark{' right' if c.get('correct') else ' wrong'}'{f" style='color:var(--{m})'" if c.get('correct') else ''} aria-label='{escape(short[m])}: {'right' if c.get('correct') else 'wrong'}'>{'✓' if c.get('correct') else '✗'}</div>" for m,c in zip(scoring.MODELS,cs))
    rule='Examples: the first three messages where the four models split two and two'
    if fallback:
        rule='Examples: first two-and-two splits; filled to three with one-and-three splits, each in message order'
    return "<div class='differed-intro'>Messages where one model was right and the other wrong — the only ones that tell two models apart.</div><div class='split-pairs'>"+''.join(rows)+"</div><div class='examples-group'><h3 class='group-heading'>Examples</h3><div class='split-examples'>"+''.join(cells)+"</div><div class='example-rule'>"+rule+'</div></div>'


def decision_example(header, calls):
    """The first differing picks in message order, independent of call order."""
    by = {(c['example_id'], c['model_key']): c for c in calls}
    for i in header['example_ids']:
        j, d = by.get((i, 'jev')), by.get((i, 'decisions'))
        if j and d and j.get('prediction') is not None and d.get('prediction') is not None and j['prediction'] != d['prediction']:
            return i, (j, d)
    return None


def probability_pairs(call):
    values = call.get('probabilities')
    if values is None:
        values = (call.get('raw_answer') or {}).get('probabilities', {})
    pairs = values.items() if isinstance(values, dict) else ((v['value'], v['probability']) for v in values)
    return sorted(pairs, key=lambda v: -v[1])


def top_probabilities(call):
    return probability_pairs(call)[:2]


def distribution_parts(call):
    """Saved mass, with displayed remainder balancing independently rounded top two.

    The bar normalizes saved mass to unit width, independently of display rounding.
    """
    pairs = probability_pairs(call)
    top = pairs[:2]
    other = math.fsum(value for _, value in pairs[2:])
    hundredths = [int((Decimal(str(value)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) for _, value in top]
    displayed = [f'{value / 100:.2f}' for value in hundredths]
    displayed.append(f'{(100 - sum(hundredths)) / 100:.2f}')
    return top, len(pairs) - len(top), other, displayed


def decision_example_html(header, calls):
    example = decision_example(header, calls)
    if example is None:
        return "<div class='example-rule'>No example: Jev and the Decisions API never picked different labels in this run.</div>"
    i, cs = example
    text = old.message_texts().get(i, '')
    result = f"<div class='decision-example' data-decision-example='{escape(i)}'><h3 class='group-heading example-rule'>Example: the first message where Jev and the Decisions API disagreed.</h3><div class='decision-message'>“{escape(text)}” <span class='correct-label'>Correct label: <code>{escape(cs[0]['reference'])}</code></span></div><div class='decision-cards'>"
    for m, c in zip(('jev', 'decisions'), cs):
        mark = f"<span class='example-mark right' style='color:var(--{m})'>✓</span>" if c.get('correct') else "<span class='example-mark wrong'>✗</span>"
        top, count, other, displayed = distribution_parts(c)
        labels = [f'<code>{escape(label)}</code>' for label, _ in top] + [f'all other {count} labels together']
        total = math.fsum(value for _, value in top) + other
        axis = '1.00 total' if math.isclose(total, 1, abs_tol=1e-9) else f'1.00 (normalized from {total:.2f})'
        bars = ''.join(f"<span class='distribution-segment part-{j}' style='width:{value / total * 100:.8f}%' title='{escape(label)}: {value:.8f}'></span>" for j, (label, value) in enumerate([*top, (f'all other {count} labels', other)]))
        probs = ''.join(f"<div class='probability-row part-{j}' title='Displayed probabilities balance rounding to sum to 1.00'><span>{label}</span><span class='key-number'>{value}</span></div>" for j, (label, value) in enumerate(zip(labels, displayed)))
        conf = confidence(c)
        conf_text = f"<span class='score-number key-number'>{conf:.2f}</span>" if conf is not None else 'not saved'
        result += f"<div class='decision-card' style='--model-color:var(--{m})'><div class='decision-card-heading'><div class='decision-model'>{'Jev' if m == 'jev' else 'Decisions API'}</div><div class='decision-score'>Confidence score {conf_text}</div></div><div class='decision-pick'>Pick: <code>{escape(c['prediction'])}</code> {mark}</div><div class='distribution'><div class='distribution-axis'><span>0</span><span>{axis}</span></div><div class='distribution-bar' role='img' aria-label='Full label probability distribution, from 0 to 1'>{bars}</div></div>{probs}</div>"
    return result + "</div><div class='example-rule concentration-rule'>Concentrated on one label → high confidence score. Spread across many → low.</div></div>"



def right_wrong_matrix(s):
    cells = {}
    for pair, sets in s['pairs'].items():
        a, b = pair.split('/')
        v = sets['all']
        clear = v['exact_mcnemar_p'] < old.CLEAR_BAR
        cells[a, b] = (v['only_a'], clear)
        cells[b, a] = (v['only_b'], clear)
    rows = ''
    for a in scoring.MODELS:
        rows += f"<tr><th scope='row'>{escape(NAMES[a])}</th>"
        for b in scoring.MODELS:
            value, clear = cells.get((a, b), ('—', False))
            content = f'<strong>{value}</strong>' if clear else str(value)
            rows += f"<td data-row='{a}' data-column='{b}' class='matrix-number{' clear' if clear else ''}'>{content}</td>"
        rows += '</tr>'
    return "<div id='right-wrong-matrix'><h3>Right where the other was wrong</h3><table class='right-wrong'><thead><tr><th scope='col'>Row model / column model</th>" + ''.join(f"<th scope='col'>{escape('Decisions API' if m == 'decisions' else NAMES[m])}</th>" for m in scoring.MODELS) + "</tr></thead><tbody>" + rows + "</tbody></table><div class='matrix-legend'><strong>Bold</strong> = clear difference (p &lt; .05), both directions marked.</div><p>Read across a row: how many messages that model got right where the column's model was wrong. Mirror cells give the other direction.</p></div>"


def presentation(s, header, calls, when):
    models=s['models'];n=models['jev']['total']
    short={**NAMES,'decisions':'Decisions API'}
    def panel(number,title,body,support=''):
        return f"<section class='stage' id='panel-{number}' aria-labelledby='panel-title-{number}'><div class='eyebrow'>{number:02d} / 07</div><h2 id='panel-title-{number}'>{title}</h2>"+body+("<div class='support'>"+support+'</div>' if support else '')+'</section>'
    def bar(m,value,maximum,number,caption='',interval=None):
        result=metric(m,value,maximum,number,interval)
        result=result.replace(NAMES[m],short[m])
        if caption:
            result=result.replace(number+'</div></div>',number+'<small>'+caption+'</small></div></div>')
        return result
    lines={'jev':'TypeSafe decision model','decisions':'OpenAI decision API on GPT-6 Luna','llm':'OpenAI chat model','luna':'The same model as the Decisions API, called normally'}
    chips='<div class="chips">'+''.join(f"<div class='chip' style='--model-color:var(--{m})'><div class='chip-name'>{NAMES[m]}</div><div class='chip-line'>{escape(lines[m])}</div></div>" for m in scoring.MODELS)+'</div>'
    out=[panel(1,'What was tested',f"<div class='stage-date'>{TITLE} · {when}</div>"+chips,f"{n} bank customer messages · {len(json.loads((Path(__file__).resolve().parent/'manifest.json').read_text())['labels'])} possible labels · same instruction for all four · through Vercel AI Gateway")]
    clear=[]
    for pair,sets in s['pairs'].items():
        a,b=pair.split('/');v=sets['all']
        if v['exact_mcnemar_p'] < old.CLEAR_BAR and v['only_a'] != v['only_b']:
            leader,other=(a,b) if v['only_a'] > v['only_b'] else (b,a)
            clear.append(f'{short[leader]} ahead of {short[other]}')
    headline=('On this sample: '+ '; '.join(clear)+ ('; no other clear differences' if len(clear) < len(s['pairs']) else '')) if clear else 'No clear difference on this sample'
    out.append(panel(2,'Right answers','<div>'+''.join(bar(m,v['correct'],v['total'],f"<span class='key-number'>{v['correct'] / v['total'] * 100:.0f}%</span><small>{v['correct']} of {v['total']} right</small>", '95% confidence interval: '+old.ci(v),v['wilson95']) for m,v in models.items())+'</div>',escape(headline)))
    out.append(panel(3,'Where they differed',differed_panel(s,header,calls,short)).replace("class='stage'","class='stage differed'"))
    maximum=max((v['usable_ms']['median'] or 0 for v in models.values()),default=0)
    order=sorted(models,key=lambda m: models[m]['usable_ms']['median'] if models[m]['usable_ms']['median'] is not None else math.inf)
    out.append(panel(4,'Speed','<div>'+''.join(bar(m,models[m]['usable_ms']['median'] or 0,maximum,old.ms(models[m]['usable_ms']['median'])) for m in order)+'</div>','Typical answer time; lower is faster'))
    maximum=max((v['charged_usd'] or 0 for v in models.values()),default=0);base=models['jev']['charged_usd']
    out.append(panel(5,f'Cost for {n} messages','<div>'+''.join(bar(m,v['charged_usd'] or 0,maximum,old.usd(v['charged_usd']),f"{v['charged_usd']/base:.1f}× Jev" if v['charged_usd'] is not None and base else 'Ratio unavailable') for m,v in models.items())+'</div>',escape(cost_why(header,calls))+" <a href='#price-sources'>Prices and usage ↗</a>"))
    cards=''
    for m in ('decisions','luna'):
        v=models[m]
        stats=[('Right answers',f"<span class='key-number'>{v['correct'] / v['total'] * 100:.0f}%</span><small>{v['correct']} of {v['total']}</small>"),('Median time',old.ms(v['usable_ms']['median'])),('Cost',old.usd(v['charged_usd']))]
        cards+=f"<div class='route-card' style='--model-color:var(--{m})'><h3>{NAMES[m]}</h3>"+''.join(f"<div class='stat-row'><span class='label'>{label}</span><span class='number'>{number}</span></div>" for label,number in stats)+'</div>'
    out.append(panel(6,'Same model, two ways',"<div class='two-ways'>"+cards+'</div>',escape(verdict('decisions','luna',s['pairs']['decisions/luna']['all']))))
    rows=''
    for m in ('jev','decisions'):
        available=[c for c in calls if c['model_key']==m and c['example_id'] in header['example_ids'] and confidence(c) is not None]
        kept=[c for c in available if confidence(c)>=.95];right=sum(bool(c.get('correct')) for c in kept)
        words=f"<b class='key-number'>{len(kept)} of {n}</b> messages · <b class='key-number'>{right} of those right</b>" if available else 'Confidence not saved'
        rows+=f"<div class='confidence-row' style='--model-color:var(--{m})'><div class='model'>{short[m]}</div><div class='threshold-summary'>{words}</div></div>"
    body = "<div class='decision-intro'>With every answer, a decision model returns a probability for each label and a confidence score for its pick.</div>" + decision_example_html(header,calls) + "<div class='threshold-group'><h3 class='group-heading'>At a confidence score of 0.95 or higher</h3><div class='confidence-rows'>" + rows + f"</div><div class='decision-note'>All {n} messages were attempted; the Decisions API answered {models['decisions']['answered']} and declined {len(models['decisions']['refusals'])}. A threshold is what you'd choose in your own app, e.g. act automatically above it and send the rest to a person.</div><div class='decision-note'>Each model's score is on its own scale: read each row on its own, and a 0.95 score doesn't mean 95% right.</div><div class='decision-note'>GPT-5.4-mini and GPT-6 Luna: no comparable confidence · <a href='#confidence-details'>Confidence details ↓</a></div></div>"
    out.append(panel(7,'What a decision model gives you',body))
    return ''.join(out)


def render(summary, header, calls, repeat, historical=None):
    s=summary
    local=eastern_start(header)
    when=f"{local.day} {local.strftime('%B %Y')}, {local.strftime('%I:%M').lstrip('0')} {local.strftime('%p').lower()} ET"
    html=["<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",'<title>'+TITLE+'</title><style>'+old.CSS+CSS+'</style></head><body><main>', presentation(s,header,calls,when), "<div class='details-divider' id='details'><h2>Details and sources</h2></div>", '<h1>'+TITLE+'</h1>',f"<p class='run'>Run on {when} · BANKING77 · {s['models']['jev']['total']} messages · 77 labels</p>","<p class='run'>"+" · ".join(escape(NAMES[m])+" <code>"+escape(header['config'][m]['model'])+"</code>" for m in scoring.MODELS)+"</p>",answer_cards(s)]
    bars=''.join(metric(m,v['correct'],v['total'],f"{v['correct']} of {v['total']} right · 95% confidence interval {old.ci(v)}",v['wilson95']) for m,v in s['models'].items())
    j=s['models']['jev'];n=j['total'];lo,hi=j['wilson95']
    bars="<p class='explain'><b>95% confidence interval</b> — the range the real accuracy most likely falls in if you tested many more messages like these. "+f"Jev got {old.pct(j['correct'], n)} of these {n} right, but its accuracy on messages like them is most likely somewhere between {lo*100:.0f}% and {hi*100:.0f}%. With only {n} messages the range is wide, about ±{round((hi-lo)*50)} points. The black line on each bar shows that range.</p>"+bars
    bars += "<h3>How to read the 95% confidence interval</h3><p>On bank messages like these, the model's real accuracy is most likely within this interval.</p><p>" + external('https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Wilson_score_interval', 'Wilson score interval') + f": if many independent samples of {n} messages were drawn from the same population and an interval built this way each time, about 95% of them would contain the true accuracy; the true accuracy is fixed, the interval varies.</p><p>These {n} messages are two per intent from the BANKING77 test set, a balanced rather than random sample, so the interval is approximate.</p>"
    if any(v['never_answered'] or v['refusals'] for v in s['models'].values()):
        bars+='<p>Refusals and unanswered messages count as wrong.</p>'
    pair=s['pairs']['jev/llm']['all'];split=pair['only_a']+pair['only_b'];lead=max(pair['only_a'],pair['only_b']);p=pair['exact_mcnemar_p']
    bars+="<h3>Message by message</h3><p>All four models were given the same messages, so the fairest comparison looks at them one at a time, two models at a time. Each message falls in one of four groups: both right, only the first right, only the second right, or both wrong.</p><p class='explain'>The messages both got right and those both got wrong say nothing about which model is better: they treated them the same. Only the split messages where exactly one model was right can tell them apart.</p>"
    bars+=f"<p class='explain'><b>How lopsided is {pair['only_a']} to {pair['only_b']} for Jev and GPT-5.4-mini?</b> If the two models were equally good, which one gets each of the {split} split messages right would be a coin flip. Flip {split} coins, and a split of {lead} to {split-lead} or more lopsided, either way, comes up {old.chance_in_100(p)} (this number is called the <b>p-value</b>: p = {p:.4f}). The usual bar for calling a difference clear is below 5 in 100. "+("That is below the bar, so this counts as a clear difference on this sample. " if p<old.CLEAR_BAR else "That is above the bar, so this sample does not show a clear difference. ")+"Being above the bar does not prove the two are equally good; more messages might show one. The name of this test, if you want to look it up: exact McNemar's test. Each of the six pairs is checked separately against the same bar, with no stricter bar for checking several pairs; this makes a chance finding somewhere among the six more likely. It does not establish an overall winner.</p>"
    bars+='<div class="pairs">'+''.join(pair_card(*pair.split('/'),v['all']) for pair,v in s['pairs'].items())+'</div>'
    bars += right_wrong_matrix(s)
    html.append(section('1. Accuracy',bars))
    html.append(section('2. Speed',speed_details(s,calls)))
    maximum=max((v['charged_usd'] or 0 for v in s['models'].values()),default=0)
    base=s['models']['jev']['charged_usd'];bars=''
    for m,v in s['models'].items():
        cost=v['charged_usd'];ratio=f'{cost/base:.1f}× Jev' if cost is not None and base else 'ratio unavailable'
        bars+=metric(m,cost or 0,maximum,f'{old.usd(cost)} · {ratio}')
    html.append(section('3. Cost',cost_details(s)+price_usage_details(header,calls)+bars+"<p>× Jev shows each charge divided by Jev’s.</p>"))
    html.append(confidence_details(s,header,calls))
    rows=[]
    for title,key in [('Right answers','correct'),('Median time','usable_ms'),('Gateway charge','charged_usd')]:
        values=[s['models'][m][key] for m in ('decisions','luna')]
        rows.append([title,*[old.ms(v['median']) if key=='usable_ms' else old.usd(v) if key=='charged_usd' else f"{v} of {s['models']['jev']['total']}" for v in values]])
    html.append(section('4. Same model, two ways: Decisions API vs GPT-6 Luna',table(['',NAMES['decisions'],NAMES['luna']],rows)+'<p><b>'+escape(verdict('decisions','luna',s['pairs']['decisions/luna']['all']))+'.</b></p>'))
    if historical:
        baseline_date = eastern_start(historical)
        date_label = f"{baseline_date.day} {baseline_date.strftime('%B %Y')}"
        rows=[]
        for m in ('jev','llm'):
            before,now=historical['models'][m],s['models'][m]
            rows.append([NAMES[m],f"{before['correct']} of {before['total']}",f"{now['correct']} of {now['total']}",old.ms(before['usable_ms']['median']),old.ms(now['usable_ms']['median'])])
        html.append(section('5. Compared with the run on '+date_label,table(['Model','That run: right','This run: right','That run: median','This run: median'],rows)+'<p>Separate runs and network conditions; timing is descriptive.</p>'))
    html.append(setup(header))
    html.append(sources(header))
    texts=old.message_texts();by={(c['example_id'],c['model_key']):c for c in calls};rows=[]
    for i in header['example_ids']:
        cs=[by.get((i,m),{}) for m in scoring.MODELS]
        if len({c.get('prediction') for c in cs}) <= 1:
            continue
        ref=next((c['reference'] for c in cs if 'reference' in c),'unknown')
        cells=[escape(i)+'<br>'+escape(texts.get(i,'')),old.label(ref)]
        for c in cs:
            conf=confidence(c) if c.get('model_key') in ('jev','decisions') else None
            suffix=f" <span class='conf'>{conf:.2f}</span>" if conf is not None else ''
            cells.append(("<span class='okk'>✓</span> " if c.get('correct') else "<span class='badk'>✗</span> ")+old.label(c.get('prediction'))+suffix)
        rows.append(cells)
    html.append(section('Messages with different answers',disagreement_intro(header,calls,len(rows))+table(['Message','Correct label',*NAMES.values()],rows,'dis')))
    html.append('<footer>Source: saved responses · original run hashes in the saved header</footer></main>')
    html.append('''<script>
  addEventListener('keydown', e => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const key = e.key;
    if (key === 'f' || key === 'F') {
      if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(() => {});
    }
  });
</script></body></html>''')
    return ''.join(html)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('path',type=Path)
    ap.add_argument('--repeat',type=Path)
    ap.add_argument('--baseline', default=str(BASELINE_RUN), help='Saved baseline path, relative to comparison; empty disables comparison')
    args=ap.parse_args()
    s=scoring.summarize(args.path);header,calls=score.load(args.path)
    page=render(s,header,calls,{},load_baseline(args.baseline))
    output=args.path.with_suffix('.report.html');output.write_text(page)
    print(output.name)


if __name__ == '__main__':
    main()
