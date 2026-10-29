# Full-assistant evaluation status

No live model evaluations have been completed: `OPENROUTER_API_KEY` was unavailable during validation.
The 84 passing automated tests validate application behavior and integration controls, not model answer quality.

| Configuration | Planned tasks | Completed live tasks | Pass rate |
|---|---:|---:|---|
| A | 25 | 0 | Not measured |
| B | 25 | 0 | Not measured |

```bash
uv run --frozen python -m rafeeq.evaluate tasks.jsonl --config A B --trials 1
# Continue matching pending/error tasks without repeating scored outcomes:
uv run --frozen python -m rafeeq.evaluate tasks.jsonl --config A B --trials 1 --resume
```

Use `--max-tasks 5` to limit an invocation to five tasks, then resume later. A task can make several provider requests. Trials are isolated in temporary databases with explicit synthetic verification and inspection fixtures when required.

Artifacts: `progress.json`, `eval-A.csv`, `eval-B.csv`, `summary.json`, `traces.jsonl` and `error-analysis.md`.
`progress.json` is the atomic source of truth; CSVs and summaries are derived from it. An advisory lock prevents concurrent writers.

Resume verifies the progress checksum and the fingerprint of runtime code, policies, tasks, model, configurations and locked dependencies. Source Git commit metadata is recorded as well. Changed inputs require a new `--output` directory. Scored passes/failures are preserved; errored tasks can be retried from fresh isolated fixtures, with prior error types retained.

Passed, failed, error and pending statuses remain distinct. Runtime errors stop further inference; pending tasks and runtime errors do not enter scored pass rates. Repeated-trial success is reported only for a complete scored suite. Progress checksums detect accidental corruption; they are not signatures against a malicious file editor.

Exit codes: **0** complete pass, **1** complete suite with scored failures, **2** incomplete execution or invalid setup. The evaluation runner requires Linux, macOS or WSL for advisory file locking.

The separate local TF-IDF retrieval experiment has executed results in [evaluations/retrieval/results/REPORT.md](../evaluations/retrieval/results/REPORT.md). Those retrieval scores are not full-assistant scores.

The demo defaults to `openrouter/free`. For a controlled live prompt A/B run, set `RAFEEQ_MODEL` to one specific available tool-capable model. A free router may serve different models across calls; serving-model IDs are recorded and that variation limits causal interpretation.
