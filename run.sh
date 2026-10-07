#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source scripts/local_env.sh
if [[ ! -x .venv/bin/python ]]; then
    echo 'Prepará el entorno siguiendo README.md antes de iniciar.' >&2
    exit 1
fi
exec .venv/bin/python main.py
