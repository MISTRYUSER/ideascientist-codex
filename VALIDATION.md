# Local validation

Validated on Apple Silicon macOS with Python 3.12.14 and Codex CLI 0.155.1 on October 14, 2026. Cloud execution and child-process authentication have not been exercised.

- 14 adapter tests pass; dependency check, shell syntax checks, and changed adapter-module static checks pass.
- All 30 public data shards match official size/SHA-256 metadata: 6,584,935,447 compressed bytes, 2,669,631 parsed JSON records.
- SQLite `papers`, `metadata_results_masked`, and `public_proposals` each contain 2,669,631 rows. `paper_full_text` remains empty by design.
- Native FTS index contains 2,669,631 records; full construction took 685 seconds locally. Targeted queries find Foam-Agent, OpenFOAMGPT, ChatCFD and related records.
- Actual Codex CLI requests returned structured external tool calls; native IdeaScientist executed searches, annotation reading, plan/gap/candidate writing and adversarial review.
- Actual CLI model-service 429 errors were observed. The bridge now spaces calls and applies bounded cooldown/retry; a live 429 recovered and the run continued beyond the previous failure point.
- The CFD topic input is derived from the supplied thesis proposal, without the original DOCX or personal identity metadata. Two candidate critiques identify substantial overlap with established invalidation/intermediate-reuse methods. Novelty is unconfirmed.

The final conditional engineering proposal completed locally at 17:37 Asia/Shanghai on October 14, 2026. Its 14 required report fields parse correctly; six inline source IDs resolve to stored papers and existing reader digests. It explicitly preserves both revise verdicts and was committed as a conditional engineering hypothesis, not a reviewer-survived novelty claim. The report is retained as a local deliverable, separate from this public source repository. This is an ideation workflow, not an OpenFOAM execution or a reproduction of the trained IdeaScientist benchmark. Failed attempts and original logs are retained locally, and artifact seeding creates a fresh continuation without overwriting them.
