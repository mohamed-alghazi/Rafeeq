# Technical guide

[Project overview](../README.md)

## Local setup

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
cp -n .env.example .env
```

Preserve an existing `.env`. Set `OPENROUTER_API_KEY` and a long, randomly generated `RAFEEQ_ACCESS_TOKEN` in that file; never commit it.
The API key authenticates requests to the inference provider. The access token protects the local application's chat and approval endpoints.

```bash
uv run --frozen uvicorn rafeeq.api:app --host 127.0.0.1 --port 8000
uv run --frozen python -m rafeeq ask "What is the fee for a 3 m² illuminated sign?"
```

The default provider is OpenRouter and the default model is `google/gemma-4-31b-it:free`. Set `RAFEEQ_MODEL` to another tool-capable model if availability changes. Optional OpenAI support uses `RAFEEQ_PROVIDER=openai`, `OPENAI_API_KEY` and an appropriate `RAFEEQ_MODEL`.

## Managed cloud setup

Use the existing checkout; do not create a Git worktree unless explicitly requested.

```bash
cd /workspace/Rafeeq
bash scripts/setup.sh
export UV_CACHE_DIR=/workspace/.uv-cache
uv run --frozen uvicorn rafeeq.api:app --host 127.0.0.1 --port 8000
```

The idempotent setup script installs locked dependencies and creates `.env` with a generated access token only if the file is absent. Supply the inference key through environment secrets. Installation and startup instructions are saved in the environment draft; saving instructions does not execute them or publish the environment. Running processes must be restarted in a new task.

`GET /health` reports service availability and credential presence, not provider authorization. A representative functional request should produce 750 SAR with `POL-02` for an illuminated 3 m² sign. Protected requests use `Authorization: Bearer <local-access-token>`.

## Engineering decisions

| Layer | Decision |
|---|---|
| Prompt | `rafeeq/spec.md` defines scope, evidence use, language and permissions. |
| Context | Keyword retrieval from three small policy documents; no embedding service needed. |
| Context limits | 24,000 characters per request and 5,000 per tool result. The optional history helper retains at most 12 messages within 8,000 characters. The browser sends one question at a time. |
| Harness | At most 8 model requests, 12 tool calls and 800 output tokens per request. MCP requests have a 20-second timeout. API and evaluation runs have a 180-second timeout. |
| Spending | Reserve an estimated USD 0.006 before each request, with a USD 0.05 run ceiling. This is not verified billing; provider pricing and spending limits must also be checked. |
| Loop | Request tools, execute allowed calls, return results and continue until an answer or a stop condition. Incomplete replies cannot execute tools. |
| Approval state | Pending → approved/rejected in SQLite. Model tools cannot call the approval executor. Ownership and the saved date are rechecked at execution. |
| MCP | Read-only policy retrieval and fee calculation over stdio; lookup and proposal creation run locally. |

Inspection dates use Riyadh's current date and require a future Sunday–Thursday in `YYYY-MM-DD` format. Public holidays and appointment capacity are not implemented.

## Automated tests

```bash
uv run --frozen pytest -q
```

The full suite includes arithmetic, real MCP subprocess integration, ownership, approval/replay, incomplete replies, evaluation graders and result preservation. Tests use synthetic fixtures and temporary databases. MCP tests require a runtime that permits child-process pipes.

Controlled-provider tests supply predetermined responses to exercise program boundaries. They are separate from live inference and write any evaluation fixtures into temporary test directories.

## Live evaluation

```bash
uv run --frozen python -m rafeeq.evaluate tasks.jsonl --config A B --trials 1
```

The suite requires at least 15 tasks and unique IDs. The supplied suite has 18. A uses the base specification; B adds one retrieval-first instruction. All other controls are held constant.

Grading checks:

- Numeric boundaries: 0 inside 300 and 750 inside 1750 do not match.
- Successful required tools, attempted or denied tools where specified, and prohibited tool attempts.
- Fee calculation output and the quoted fee, required policy citations and forbidden disclosures.
- Database state: inspection proposals remain pending and no inspection is booked without approval.

The runner saves progress after every task and stops after a runtime/provider error instead of exhausting the remaining quota. It does not store raw provider exception text. CSV statuses distinguish passed, failed, error and pending. Pass rates use scored completed tasks only. All-trial success is reported only for a fully scored suite; a single trial does not establish repeated-trial reliability.

Outputs include CSVs, traces, metadata, task/spec hashes and a category-level error-analysis report. The report lists failed checks and observed A/B changes; causal conclusions still require inspecting the answers and traces. Previous results are not overwritten. Use a separate `--output` directory for another run; automatic resume is not implemented.

Missing credentials create no result files. Exit codes are 0 for a complete pass, 1 for scored failures and 2 for incomplete execution or invalid setup. Live results remain pending until credentials are available.

## Data and deployment limits

All supplied records are synthetic. Questions and relevant tool results are transmitted to OpenRouter and its serving provider. The local demo uses one applicant identity; its access token is not a production account system. Runtime SQLite files and `.env` are excluded from Git. The audit table stores proposal/decision identifiers without conversation transcripts or credentials.

Production deployment requires independent user authentication, data-protection controls, provider suitability review, rate limiting and real scheduling integration.
