#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PYTHON="${PYTHON_BIN:-python3}"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3,10), "Python >=3.10 required; set PYTHON_BIN"'
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install -e '.[public]'
.venv/bin/python -m pip check
command -v codex >/dev/null || { echo 'Install the official Codex CLI: npm install -g @openai/codex'; exit 1; }
codex login status
.venv/bin/python -c 'from ideascientist.serving.codex_bridge import require_chatgpt_login; require_chatgpt_login()'
.venv/bin/python -m unittest discover -s tests -v
