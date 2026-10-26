"""Compare four models on bank messages with frozen settings.

Run: uv run python run_four.py --split dev --limit 5
The original temp0 runner and its imports remain unchanged. Keys come only from
AI_GATEWAY_API_KEY in the process environment, never a worktree dotenv file.
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
import rerun_gateway_temp0 as t0

HERE = Path(__file__).resolve().parent
CONFIG_NAME = 'config-gateway-four.json'
FROZEN_NAME = 'FROZEN-gateway-four.json'
FROZEN_FILES = [CONFIG_NAME, 'manifest.json', 'run.py', 'rerun_via_gateway.py',
                'rerun_gateway_temp0.py', 'run_four.py', 'score_four.py', 'ANALYSIS_PLAN.md',
                'netbase.sh', 'freeze_four.py']
MODELS = ('jev', 'llm', 'decisions', 'luna')
ROTATIONS = [MODELS[i:] + MODELS[:i] for i in range(4)]
ORDER = ROTATIONS + [tuple(reversed(row)) for row in ROTATIONS]
FROZEN_FILES += ['run_decisions.py', 'report_four_html.py', 'report_html.py', 'score.py',
                 'score_gateway.py', 'run_comparison_v2.py', 'run_comparison_v2.sh', 'FOUR_MODEL_PLAN.md']


def luna_call(client, cfg, labels, text):
    return t0.llm_call(client, {**cfg, 'llm': cfg['luna']}, labels, text)


def sha_file(name, here=HERE):
    return hashlib.sha256((here / name).read_bytes()).hexdigest()


def check_frozen(here=HERE):
    path = here / FROZEN_NAME
    if not path.exists():
        sys.exit('No Decisions freeze; commit the freeze before test execution')
    frozen = json.loads(path.read_text())
    for name in FROZEN_FILES:
        if frozen['sha256'].get(name) != sha_file(name, here):
            sys.exit(f'{name} changed after the Decisions freeze')
    return frozen


def decisions_call(client, cfg, labels, text):
    m = cfg['decisions']
    body = {'model': m['model'], 'input': text, 'questions': [
        {'type': 'choice', 'name': 'intent', 'instructions': cfg['instruction'],
         'choices': [{'value': label} for label in labels]}],
        'providerOptions': {'gateway': {'only': m['provider_only']}}}
    start = time.perf_counter()
    r = client.post(m['endpoint'], json=body,
                    headers={'Authorization': 'Bearer ' + t0.base.KEYS['decisions']})
    data = t0._response_json(r)
    out = {'http_status': r.status_code, 'elapsed_ms': round((time.perf_counter()-start)*1000, 1),
           'retry_after': r.headers.get('retry-after')}
    if r.status_code != 200 or not data.get('answers'):
        out['error'] = data.get('error') or 'Missing Decisions answers'
        return out
    ans = data['answers'][0]
    out.update(prediction=ans.get('choice') if ans.get('type') == 'choice' else None,
               refusal=ans.get('type') == 'refusal', reasoning_setting=m['reasoning_setting'])
    return out


class Capture:
    def __init__(self, client):
        self.client = client
        self.response = None

    def post(self, *args, **kwargs):
        self.response = self.client.post(*args, **kwargs)
        return self.response


def recorded_call(caller, client, cfg, labels, text):
    capture = Capture(client)
    out = caller(capture, cfg, labels, text)
    data = t0._response_json(capture.response)
    meta = (data.get('provider_metadata') or {}).get('gateway') or {}
    routing = meta.get('routing') or {}
    usage = data.get('usage') or {}
    cost = usage.get('cost', meta.get('cost'))
    market = usage.get('market_cost', meta.get('marketCost'))
    answers = data.get('answers')
    ans = answers[0] if isinstance(answers, list) and answers else (answers or {}).get('intent', {})
    if ans:
        probs = ans.get('probabilities') or {}
        pairs = [(p['value'], p['probability']) for p in probs] if isinstance(probs, list) else list(probs.items())
        out.update(raw_answer=ans, confidence=ans.get('confidence'), probabilities=probs,
                   top3=sorted(pairs, key=lambda p: -p[1])[:3])
    out.update(answered_model=data.get('model'), usage=usage,
               provider_metadata=data.get('provider_metadata'), gateway_routing=routing,
               gateway_cost=cost, gateway_market_cost=market,
               generation_id=data.get('generationId') or data.get('id') or meta.get('generationId'))
    if routing.get('finalProvider'):
        out['final_provider'] = routing['finalProvider']
    attempts = [a for m in routing.get('modelAttempts', []) for a in m.get('providerAttempts', [])]
    if attempts:
        out['provider_attempts'] = [(a.get('provider'), a.get('statusCode')) for a in attempts]
        last = attempts[-1]
        if last.get('startTime') is not None and last.get('endTime') is not None:
            out['provider_ms'] = last['endTime'] - last['startTime']
    return out


def prior_spend(results):
    total = 0.0
    access = results / 'four-dev-probe.json'
    if access.exists():
        d = json.loads(access.read_text())
        total += float(d['gateway_cost'])
    for path in results.glob('*-gateway-four*.jsonl'):
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row['type'] == 'call':
                total += float(row['attempts_gateway_cost'])
    return total


def run_split(split, pass_no=None, limit=None, here=HERE, results_dir=None, transport=None, environ=None, live=False):
    results = results_dir or here / 'results'
    if split == 'test':
        frozen = check_frozen(here)
        if (not live and pass_no not in (1, 2)) or limit is not None:
            sys.exit('Test requires --pass-no 1 or 2 and no --limit')
        # The freeze must exist in HEAD, not merely in the working directory.
        import subprocess
        committed = subprocess.run(['git', 'show', 'HEAD:comparison/' + FROZEN_NAME],
                                   cwd=here, capture_output=True, text=True, check=True)
        if json.loads(committed.stdout) != frozen:
            sys.exit('Commit the Decisions freeze before test execution')
        previous = sorted(results.glob('test-*-gateway-four-rehearsal*.jsonl'))
        if not live and len(previous) != pass_no - 1:
            sys.exit('Exactly two passes in order; existing test results block this pass')
        for prior in previous if not live else []:
            rows = [json.loads(line) for line in prior.read_text().splitlines()]
            if (rows[0].get('pass_no') != 1 or rows[-1].get('type') != 'run_footer'
                    or rows[-1].get('stop_reason') or sum(r['type'] == 'call' for r in rows) != 616):
                sys.exit('Previous pass incomplete; stop and report without rerunning')
    elif limit is None or not 1 <= limit <= 5:
        sys.exit('Dev requires --limit between 1 and 5')
    cfg = json.loads((here / CONFIG_NAME).read_text())
    manifest = json.loads((here / 'manifest.json').read_text())
    labels = manifest['labels']
    examples = [e for e in manifest['examples'] if e['split'] == split][:limit]
    key = (os.environ if environ is None else environ).get('AI_GATEWAY_API_KEY')
    if not key:
        sys.exit('AI_GATEWAY_API_KEY missing from process environment')
    t0.base.KEYS.update({k: key for k in MODELS})
    if split == 'test' and len(examples) != 154:
        sys.exit('Test manifest must contain exactly 154 examples')
    spent = prior_spend(results)
    display_start_spend = spent
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    suffix = ('-live' if live else f'-rehearsal-pass{pass_no}') if split == 'test' else ''
    path = results / f'{split}-{stamp}-gateway-four{suffix}.jsonl'
    results.mkdir(parents=True, exist_ok=True)
    callers = {'jev': t0.base.jev_call, 'llm': t0.llm_call, 'decisions': decisions_call, 'luna': luna_call}
    started = time.perf_counter()
    kwargs = {'timeout': cfg['timeout_s']}
    if transport is not None:
        kwargs['transport'] = transport
    with httpx.Client(**kwargs) as client, path.open('x') as f:
        def write(row):
            f.write(json.dumps(row).replace(key, '[REDACTED]') + '\n')
            f.flush()
        write({'type': 'run_header', 'split': split, 'pass_no': pass_no, 'purpose': 'four-model comparison' if live else 'repeat comparison', 'started_utc': stamp, 'runner': 'run_four.py',
               'config': cfg, 'example_ids': [e['example_id'] for e in examples],
               'sha256': {n: sha_file(n, here) for n in FROZEN_FILES}, 'prior_spend_usd': spent})
        stop = None
        for i, ex in enumerate(examples):
            for position, model in enumerate(ORDER[i % len(ORDER)]):
                if spent + cfg['budget']['reserve_per_call_usd'] > cfg['budget']['cap_usd']:
                    stop = 'Budget reserve would exceed $1'; break
                observed = []
                def caller(c, config, ls, text):
                    out = recorded_call(callers[model], c, config, ls, text)
                    observed.append({k: out.get(k) for k in ('gateway_cost', 'generation_id', 'http_status')})
                    return out
                res = t0.base.call_with_retries(caller, client, cfg, labels, ex['text'])
                known = bool(observed) and len(observed) == res['attempts'] and all(a['gateway_cost'] is not None for a in observed)
                charge = sum(float(a['gateway_cost'] or 0) for a in observed)
                spent += charge
                pred = res.get('prediction')
                valid = res.get('http_status') == 200 and pred in labels and not res.get('refusal')
                write({'type': 'call', 'example_id': ex['example_id'], 'model_key': model,
                       'position': position, 'reference': ex['label'], **res,
                       'valid': valid, 'correct': valid and pred == ex['label'],
                       'attempt_gateway_charges': observed, 'attempts_gateway_cost': charge,
                       'gateway_cost_complete': known})
                if not known or spent > cfg['budget']['cap_usd']:
                    stop = 'Missing gateway cost or spend cap reached'; break
            print(f"{i+1:3}/{len(examples)} messages | {len(MODELS)} models | {time.perf_counter()-started:.0f}s elapsed | this run ${spent-display_start_spend:.4f}", flush=True)
            if stop:
                break
        write({'type': 'run_footer', 'wall_s': round(time.perf_counter()-started, 2),
               'cumulative_gateway_usd': spent, 'stop_reason': stop})
    if stop:
        sys.exit(stop + '; partial evidence saved to ' + str(path.resolve().relative_to(HERE.parent) if path.resolve().is_relative_to(HERE.parent) else path.name))
    print(f'done -> {path.resolve().relative_to(HERE.parent) if path.resolve().is_relative_to(HERE.parent) else path.name} · this run ${spent-display_start_spend:.4f}')
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--split', choices=['dev', 'test'], required=True)
    ap.add_argument('--limit', type=int)
    ap.add_argument('--pass-no', type=int, choices=[1, 2])
    args = ap.parse_args()
    run_split(args.split, pass_no=args.pass_no, limit=args.limit)


if __name__ == '__main__':
    main()
