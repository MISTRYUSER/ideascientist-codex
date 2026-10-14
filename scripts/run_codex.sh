#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ $# -lt 1 ]]; then echo 'Usage: bash scripts/run_codex.sh /path/to/problem.txt'; exit 2; fi
[[ -f "$1" ]] || { echo "Problem file not found: $1"; exit 2; }
export IDEA_VAULT_DB="${IDEA_VAULT_DB:-data/idea_vault.db}"
export IDEASCIENTIST_KEYWORD_INDEX="${IDEASCIENTIST_KEYWORD_INDEX:-data/keyword_index.db}"
[[ -f "$IDEA_VAULT_DB" && -f "$IDEASCIENTIST_KEYWORD_INDEX" ]] || { echo 'Run bash scripts/prepare_public_data.sh first'; exit 2; }
codex login status
mkdir -p logs
PORT="${CODEX_BRIDGE_PORT:-8765}"
export IDEASCIENTIST_BASE_URL="http://127.0.0.1:$PORT/v1"
export IDEASCIENTIST_MODEL=codex-cli
export IDEASCIENTIST_HTTP_TIMEOUT=360
export IDEASCIENTIST_MAX_RETRIES=2
export IDEASCIENTIST_READER_FULLTEXT_TOK_CAP=0
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
if ! curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    .venv/bin/python -u -m ideascientist.serving.codex_bridge --port "$PORT" > logs/codex_bridge.log 2>&1 &
    BRIDGE_PID=$!
    trap 'kill "$BRIDGE_PID" 2>/dev/null || true' EXIT
    for _ in {1..50}; do
        curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
        kill -0 "$BRIDGE_PID" 2>/dev/null || { cat logs/codex_bridge.log; exit 1; }
        sleep 0.1
    done
fi
.venv/bin/python scripts/run_ideation.py --model codex-cli --problem-file "$1" --run-dir runs "${@:2}"
