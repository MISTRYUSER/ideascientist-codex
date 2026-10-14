#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
.venv/bin/python scripts/download_public_vault.py
.venv/bin/python -m ideascientist.vault.import_public --db data/idea_vault.db
.venv/bin/python -m ideascientist.vault.index keyword --db data/idea_vault.db --keyword-out data/keyword_index.db --readers 2
