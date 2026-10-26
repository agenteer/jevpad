"""Run exactly one four-model comparison with frozen settings, score it, and write the report."""
import argparse
import json
import os
from pathlib import Path
import shlex
import time

import run_four as runner
import score_four as scoring
import report_four_html as report


def load_key():
    """Use the environment first, then the repository dotenv; never evaluate shell code."""
    if os.environ.get('AI_GATEWAY_API_KEY'):
        return
    missing = 'Set AI_GATEWAY_API_KEY in your environment or in .env at the repository root.'
    path = runner.HERE.parent / '.env'
    try:
        lines = path.read_text().splitlines()
    except FileNotFoundError:
        raise SystemExit(missing)
    for line in lines:
        line = line.strip()
        if line.startswith('export '):
            line = line[7:].lstrip()
        name, sep, value = line.partition('=')
        if sep and name.strip() == 'AI_GATEWAY_API_KEY':
            try:
                tokens = shlex.split(value, comments=True)
            except ValueError:
                raise SystemExit('Invalid AI_GATEWAY_API_KEY entry in repository .env')
            if len(tokens) != 1 or not tokens[0]:
                raise SystemExit('Invalid AI_GATEWAY_API_KEY entry in repository .env')
            os.environ['AI_GATEWAY_API_KEY'] = tokens[0]
            return
    raise SystemExit(missing)


def artifacts(path, repeat=None, baseline=report.BASELINE_RUN):
    summary = scoring.summarize(path)
    if repeat:
        summary['run_to_run'] = scoring.agreement(path, repeat)
    path.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    path.with_suffix('.table.md').write_text(scoring.to_markdown(summary))
    h,c = scoring.score.load(path)
    output = path.with_suffix('.report.html')
    output.write_text(report.render(summary,h,c,summary.get('run_to_run',{}),report.load_baseline(baseline)))
    return output


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Check the frozen settings without sending requests")
    ap.add_argument('--baseline', default=str(report.BASELINE_RUN), help='Saved baseline path, relative to comparison; empty disables comparison')
    args = ap.parse_args(argv)
    started = time.perf_counter()
    runner.check_frozen()
    if args.check:
        print("Frozen settings: OK")
        return
    load_key()
    print('BANKING77 · 154 messages · four models · one run with frozen settings', flush=True)
    path = runner.run_split('test', live=True)
    output = artifacts(path, baseline=args.baseline)
    print(f'Completed and scored in {time.perf_counter()-started:.0f} seconds.\nHTML report: {output.resolve().relative_to(runner.HERE.parent) if output.resolve().is_relative_to(runner.HERE.parent) else output.name}', flush=True)


if __name__ == '__main__':
    main()
