"""Freeze the owner-selected Decisions experiment before any test calls.

Requires committed owned sources; refuses existing freezes or test results.
"""
import argparse
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone
import run_four as runner


def prepare(here, jev_model):
    if (here / runner.FROZEN_NAME).exists() or list((here / 'results').glob('test-*-gateway-four*.jsonl')):
        raise ValueError('Existing freeze or test results; refusing to overwrite')
    cfg = json.loads((here / runner.CONFIG_NAME).read_text())
    if cfg['jev']['model'] != jev_model:
        raise ValueError('Owner-selected Jev model must match config')
    status = subprocess.run(['git', 'status', '--porcelain', '--', *runner.FROZEN_FILES,
                             'freeze_four.py'], cwd=here, check=True, capture_output=True, text=True)
    if status.stdout.strip():
        raise ValueError('Commit owned source files before freezing')
    return {'frozen_utc': datetime.now(timezone.utc).isoformat(),
            'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=here, text=True).strip(),
            'owner_selected_jev_model': jev_model, 'declared_before_any_test_call': True,
            'sha256': {n: runner.sha_file(n, here) for n in runner.FROZEN_FILES},
            'plan': 'ANALYSIS_PLAN.md, applied independently to each of the six pairs; first-pass table and second-pass agreement; a separate comparison supplies the main results.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--jev-model', required=True, help='Exact model explicitly selected by owner')
    args = ap.parse_args()
    frozen = prepare(runner.HERE, args.jev_model)
    with (runner.HERE / runner.FROZEN_NAME).open('x') as f:
        f.write(json.dumps(frozen, indent=2)+'\n')


if __name__ == '__main__':
    main()
