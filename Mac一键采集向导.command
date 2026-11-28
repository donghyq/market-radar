#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1
if ! python3 -c 'import sys; raise SystemExit(int(sys.version_info < (3, 10)))'; then
    printf '%s\n' '需要 Python 3.10 或更新版本。' >&2
    exit 1
fi
exec python3 -X utf8 run_radar.py "$@"
