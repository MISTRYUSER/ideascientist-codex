# IdeaScientist + Codex

This private copy adds a Codex CLI inference bridge and imports the public Svalbard Idea Vault into the native SQLite retrieval pipeline. Original upstream: https://github.com/jiarui-liu/IdeaScientist, revision `82a98a0`. The original CC BY-NC 4.0 code license remains in force.

## Quick start (Linux or macOS)

Requires Python >=3.10, `curl`, the official Codex CLI, a working Codex login, and enough disk space for the compressed corpus, SQLite database and FTS index. Reserve at least 80 GB free disk for the full dataset. No GPU is required for this keyword-retrieval + Codex inference path.

```bash
npm install -g @openai/codex
codex login --device-auth    # if this machine is not already authenticated
bash scripts/setup_codex.sh
bash scripts/prepare_public_data.sh
bash scripts/run_codex.sh examples/cfd-diagnosis-stopping.txt
```

Use `PYTHON_BIN=python3.12 bash scripts/setup_codex.sh` if `python3` is too old. Rewrite the example problem before a real research run. Each run saves the proposal to `runs/<timestamp>_<slug>/outputs/report.json`, with plans, paper digests and model-call logs alongside it.

For the supplied CFD thesis topic, use `IDEASCIENTIST_CUTOFF_DATE=2027-01-01 bash scripts/run_codex.sh examples/cfd-diagnosis-stopping.txt` to include the public release's 2026 literature. This is a practical proposal run, not the paper's temporal benchmark. The source DOCX and personal identity details are not included in the repository; only the research problem and constraints are retained.

The bridge uses the Codex CLI's default model; set `CODEX_MODEL` to choose an available model. It uses ChatGPT login and does not require an API key. Temperature and output-token settings from the original harness are only approximate instructions here, not API-level controls. Each bridge call is an ephemeral Codex run: full history is resent and no conversation session is reused. This can consume substantial Codex quota and is slower than a dedicated API backend.

One bridge supports one harness run, with up to four simultaneous inference requests and four external tool calls per model turn. Use a separate `CODEX_BRIDGE_PORT` for simultaneous independent research runs. Excess concurrent requests receive 429 rather than waiting past the client's deadline. Built-in Codex shell, web, browser, plugin, and delegation tools are disabled: the external IdeaScientist harness performs its own tool calls. Saved API-key authentication is rejected; a valid ChatGPT login is required.

Temporary HTTP 429/5xx errors are retried once by the launcher configuration. To continue from artifacts after an interrupted run without overwriting its logs, add `--seed-run-dir runs/<previous_run>` to `run_codex.sh`. This copies saved plans, gaps, candidates and paper digests into a new run and starts a fresh orchestrator that continues missing phases; it is not an exact replay of the old conversation. Original attempt logs remain available separately.

The bridge spaces CLI inference starts by 45 seconds by default (`CODEX_BRIDGE_MIN_INTERVAL`) and backs off on CLI model-service 429 errors for 60/120 seconds (`CODEX_BRIDGE_RATE_BACKOFF`). It makes at most three CLI attempts within an overall 300-second request deadline; the harness HTTP timeout is 360 seconds. A visible remaining weekly quota does not rule out short-term model rate limits. Failed CLI requests/events are saved under ignored `logs/bridge-failures/` for diagnosis.

## Codex Cloud

Select this private repository in a Codex Cloud environment. Allow the package registries, Hugging Face data/CDN hosts, and the Codex authentication/inference destinations required by your environment. The full corpus is downloaded in the cloud; local Mac files and login caches are not uploaded.

**First check `codex login status` inside the cloud environment.** The outer cloud agent's access does not prove that a child `codex exec` process is authenticated. This adapter has been exercised locally; nested CLI authentication in Codex Cloud must be verified separately. If `codex exec` is unavailable or unauthenticated, complete supported login or use the upstream API backend with a separately configured credential. Do not commit authentication files or secrets.

For an initial cloud check, import a subset instead of the full corpus:

```bash
.venv/bin/python scripts/download_public_vault.py
.venv/bin/python -m ideascientist.vault.import_public --limit 10000 --db data/smoke_vault.db
.venv/bin/python -m ideascientist.vault.index keyword --db data/smoke_vault.db --keyword-out data/smoke_keyword.db --readers 2
IDEA_VAULT_DB=data/smoke_vault.db IDEASCIENTIST_KEYWORD_INDEX=data/smoke_keyword.db IDEASCIENTIST_CUTOFF_DATE=2027-01-01 bash scripts/run_codex.sh examples/memory-retrieval.txt
```

The cutoff override is for the integration check: the first downloaded records include 2026 papers. Normal runs keep the upstream cutoff of January 1, 2026. This smoke check is not a reproduction of the paper's benchmark.

## Data provenance and limitations

The downloader pins `Jerry999/SvalbardIdeaVault` at `64ab36be959afab06066f8c1e7ea292dba9362e5`. It downloads all 30 compressed shards (6,584,935,447 bytes) and verifies their sizes and SHA-256 hashes against the checked-in public manifest. Interrupted transfers resume. Dataset: https://huggingface.co/datasets/Jerry999/SvalbardIdeaVault.

The public release contains 2,669,631 generated annotations, not original paper full text and not the training-time structured vault. Import preserves bibliographic dates, public proposal text, split, and generation timestamp; section text is mapped into the native record fields without model-generated additions. Unavailable structured fields and citation edges are not reconstructed. The native `paper_full_text` table stays empty. Readers receive an explicit annotation notice. A report generated with this data is an exploratory proposal requiring original-paper checks and empirical validation, not a verified scientific discovery or a reproduction of trained role adapters.

Import is resumable and skips already imported arXiv IDs. Keyword indexes should only be built after import has finished, and reads should only begin after indexing has finished. Do not start concurrent import writers.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
```

Tests cover tool-call roundtrips, malformed/unknown calls, duplicate import, annotation access, reader dispatch, and date-cutoff exclusion. Live integration results are recorded separately in `VALIDATION.md`.
