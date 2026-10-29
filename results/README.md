# Live evaluation status

No live model evaluations have been executed: `OPENROUTER_API_KEY` was unavailable during validation.
The 35 passing automated tests validate code and integration controls, not model answer quality.

| Configuration | Planned tasks | Completed live evaluations | Pass rate |
|---|---:|---:|---|
| A | 18 | 0 | Not measured |
| B | 18 | 0 | Not measured |

After configuring the key:

```bash
uv run --frozen python -m rafeeq.evaluate tasks.jsonl --config A B --trials 1
```

The runner writes `eval-A.csv`, `eval-B.csv`, `summary.json`, `traces.jsonl` and `error-analysis.md`.
Each task records passed, failed, error or pending status. Runtime errors stop further requests and leave the rest pending.
Scored pass rates exclude pending tasks and runtime errors; incomplete coverage stays visible.
Progress is saved after each task. Existing runs cannot be overwritten; use `--output results/run-2` for another run.
No automatic resumption is implemented.

Exit codes: **0** for a complete passing suite, **1** for a complete suite with scored failures, and **2** for incomplete execution or invalid setup.
