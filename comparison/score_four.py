"""Score four-model results with every declared example in every denominator.

Pairwise wording uses unrounded exact McNemar p independently per pair;
these are unadjusted comparisons, not a general-winner claim.
"""
import argparse
from itertools import combinations
import json
from pathlib import Path
import statistics

import score

MODELS = ('jev', 'llm', 'decisions', 'luna')


def summarize(path):
    header, calls = score.load(Path(path))
    ids = header['example_ids']
    cfg = header['config']
    by = {m: {} for m in MODELS}
    for c in calls:
        if c['example_id'] in by[c['model_key']]:
            raise ValueError('Duplicate model/example result')
        by[c['model_key']][c['example_id']] = c
    def valid(c):
        return c.get('http_status') == 200 and c.get('valid') and not c.get('refusal')
    def right(c):
        return bool(valid(c) and c.get('prediction') == c.get('reference'))
    def timings(values):
        return {'n': len(values), 'median': statistics.median(values) if values else None,
                'p95': score.pct(values, 95), 'worst': max(values) if values else None}
    out = {'file': Path(path).name, 'split': header['split'], 'examples': len(ids), 'models': {}, 'pairs': {}}
    for m in MODELS:
        cs = [by[m].get(i, {}) for i in ids]
        answered = [c for c in cs if valid(c)]
        k = sum(right(c) for c in cs)
        attempts = [a for c in cs for a in c.get('attempt_log', [])]
        def catalog(c):
            if m != 'decisions':
                return score.catalog_cost(c, 'llm' if m == 'luna' else m, {**cfg, 'llm': cfg[m]} if m == 'luna' else cfg)
            u = c.get('usage') or {}
            return (u.get('input_tokens') or 0) * cfg[m]['catalog_price_per_million']['input'] / 1e6
        complete = all(c.get('gateway_cost_complete') for c in cs)
        out['models'][m] = {
            'correct': k, 'total': len(ids), 'answered': len(answered),
            'correct_of_answered': f'{k}/{len(answered)}', 'wilson95': score.wilson(k, len(ids)),
            'never_answered': [i for i,c in zip(ids,cs) if not valid(c)],
            'refusals': [i for i,c in zip(ids,cs) if c.get('refusal')],
            'served_ms': timings([c['elapsed_ms'] for c in answered]),
            'usable_ms': timings([c['total_ms'] for c in answered]),
            'provider_ms': timings([c['provider_ms'] for c in answered if c.get('provider_ms') is not None]),
            'catalog_cost_usd': sum(catalog(c) for c in cs),
            'charged_usd': sum(c.get('attempts_gateway_cost', 0) for c in cs) if complete else None,
            'availability': {'attempts_total': len(attempts),
                'attempts_refused_429': sum(a.get('status') == 429 for a in attempts),
                'timeouts_or_connection': sum(a.get('status') is None for a in attempts),
                'retries': sum(max(0, c.get('attempts', 1)-1) for c in cs),
                'retry_after_sent': any(a.get('retry_after') for a in attempts),
                'refusal_message': next((a.get('error') for a in attempts if a.get('status') == 429), None)},
        }
    for a,b in combinations(MODELS, 2):
        def paired(selected):
            both = only_a = only_b = neither = 0
            for i in selected:
                ar,br = right(by[a].get(i, {})), right(by[b].get(i, {}))
                both += ar and br
                only_a += ar and not br
                only_b += br and not ar
                neither += not ar and not br
            p = score.exact_mcnemar(only_a, only_b)
            return {'n': len(selected), 'both_correct': both, 'only_a': only_a, 'only_b': only_b,
                    'both_wrong': neither, 'exact_mcnemar_p': p,
                    'wording': (f'{a if only_a > only_b else b} better at accuracy on this sample'
                                if p < .05 and only_a != only_b else 'no clear difference on this sample')}
        out['pairs'][f'{a}/{b}'] = {'all': paired(ids), 'both_answered': paired(
            [i for i in ids if valid(by[a].get(i, {})) and valid(by[b].get(i, {}))])}
    return out


def to_markdown(s):
    lines = [f"{s['split']} split: {s['examples']} examples. Unanswered/refused examples count wrong.", '',
             '| Model | Correct / all | Correct / answered | Wilson 95% | Served median / p95 / worst (ms) | Usable median / p95 / worst (ms) | Gateway USD |',
             '|---|---|---|---|---|---|---|']
    for m, v in s['models'].items():
        ts = lambda name: ' / '.join(('—' if v[name][k] is None else f'{v[name][k]:.0f}') for k in ('median', 'p95', 'worst'))
        lo, hi = v['wilson95']
        lines.append(f"| {m} | {v['correct']}/{v['total']} | {v['correct_of_answered']} | {lo:.1%}–{hi:.1%} | {ts('served_ms')} | {ts('usable_ms')} | {format(v['charged_usd'], '.4g') if v['charged_usd'] is not None else 'unknown'} |")
    lines += ['', 'p95 is rough at this n. Pairwise exact two-sided McNemar tests (unadjusted):']
    for pair, v in s['pairs'].items():
        for subset, r in v.items():
            lines.append(f"- {pair}, {subset}: n={r['n']}, both right={r['both_correct']}, only first={r['only_a']}, only second={r['only_b']}, both wrong={r['both_wrong']}, p={r['exact_mcnemar_p']:.6g}; {r['wording']}.")
    lines += ['', 'Availability and catalog cost (separate from gateway charge):']
    for m,v in s['models'].items():
        lines.append(f"- {m}: {json.dumps(v['availability'])}; unanswered={v['never_answered']}; refusals={v['refusals']}; catalog USD={v['catalog_cost_usd']:.4g}.")
    return '\n'.join(lines) + '\n'


def agreement(first, repeat):
    _, a = score.load(Path(first))
    _, b = score.load(Path(repeat))
    out = {}
    for model in MODELS:
        left = {c['example_id']: c.get('prediction') for c in a if c['model_key'] == model and c.get('valid')}
        right = {c['example_id']: c.get('prediction') for c in b if c['model_key'] == model and c.get('valid')}
        common = sorted(left.keys() & right.keys())
        changed = [i for i in common if left[i] != right[i]]
        out[model] = {'compared': len(common), 'same_answer': len(common)-len(changed), 'changed_ids': changed}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('path')
    ap.add_argument('--repeat')
    ap.add_argument('--md')
    ap.add_argument('--json')
    args = ap.parse_args()
    s = summarize(args.path)
    md = to_markdown(s)
    if args.repeat:
        s['run_to_run'] = agreement(args.path, args.repeat)
        md += '\nRun-to-run agreement: ' + json.dumps(s['run_to_run']) + '\n'
    print(md)
    if args.md:
        Path(args.md).write_text(md)
    if args.json:
        Path(args.json).write_text(json.dumps(s, indent=2)+'\n')


if __name__ == '__main__':
    main()
