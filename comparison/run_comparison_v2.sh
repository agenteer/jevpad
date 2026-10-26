#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="${TMPDIR:-/tmp}/jev-decisions-uv-cache"
exec uv run --project comparison python comparison/run_comparison_v2.py "$@"
