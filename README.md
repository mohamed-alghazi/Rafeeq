# رفيق | Rafeeq

**Rafeeq is an AI assistant that helps users check applications, calculate fees and request municipal services.** It can prepare inspections, change appointments, request refunds and escalate delays. Users review and approve every action before it is recorded.

Built for [Advanced Agentic AI Systems Engineering - SDAIA Academy](https://github.com/sdaiaacademy/agentic-ai/), Track 1: Rafeeq in production. Madar is a fictional municipality; all records and demo identity details are synthetic.

## Features

- Policy-based answers and fee calculation with source references.
- Applicant verification using the registered mobile and last four ID digits, outside the AI conversation.
- Inspection booking, rescheduling, refunds and overdue-application escalation, with human approval.
- Separate conversations for each session, with bounded history and sensitive-data redaction.
- **8 tools**, including two over MCP, and **25 evaluation tasks** on configurations A and B.
- Resumable evaluation tied to the code, policies, tasks, model and locked dependencies.

## Tools

| Tool | Purpose | MCP |
|---|---|---|
| `search_policy` | Find relevant policies | Yes |
| `calculate_fee` | Calculate fees | Yes |
| `get_application` | Check a verified applicant's application | No |
| `list_inspections` | List the applicant's inspection dates | No |
| `propose_inspection` | Prepare a booking | No |
| `propose_reschedule` | Prepare an appointment change | No |
| `propose_refund` | Calculate and prepare a refund request | No |
| `propose_escalation` | Prepare escalation of an overdue application | No |

The four proposal tools never execute their actions directly. Refunds above 1,000 SAR await finance review after user approval. The demo never pays money or sends email.

## Run locally

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
cp -n .env.example .env
```

Set `OPENROUTER_API_KEY` and a long, random `RAFEEQ_ACCESS_TOKEN` in `.env`, then start the service:

```bash
uv run --frozen uvicorn rafeeq.api:app --host 127.0.0.1 --port 8000
```

Enter the access code in the browser to start a session. The verification form accepts the public synthetic fixture: application `MDR-1001`, ID suffix `0001`, mobile `0550001001`. Credentials are entered in that form, not in chat. A 3 m² illuminated sign should cost **750 SAR** under `POL-02`.

[Technical guide](docs/TECHNICAL.md) · [Share a hosted demo](docs/DEPLOYMENT.md)

## Tests and evaluation

**60 automated tests pass.** They cover identity checks, memory isolation, refunds, rescheduling, escalation, approval, privacy, real MCP integration and evaluation recovery. These are application tests, not live model scores.

```bash
uv run --frozen pytest -q
uv run --frozen python -m rafeeq.evaluate tasks.jsonl --config A B --trials 1
# Continue after a quota/access interruption:
uv run --frozen python -m rafeeq.evaluate tasks.jsonl --config A B --trials 1 --resume
```

The [25-task suite](tasks.jsonl) exceeds the 15-task minimum. A uses base instructions; B adds a retrieval-first instruction. Tools, models and security controls are otherwise identical. Graders check answers, successful tool calls, citations, proposed amounts and database state.

| Configuration | Planned tasks | Completed live tasks | Pass rate |
|---|---:|---:|---|
| A | 25 | 0 | Not measured |
| B | 25 | 0 | Not measured |

The inference key was unavailable during validation, so live results remain pending. Saved results include traces, an error analysis and a source fingerprint. Resumption preserves scored outcomes and rejects changed code, tasks or model settings. Runtime failures and pending tasks are separate from scored failures. [Evaluation status](results/README.md).

## Security

**Risk:** an instruction asks the AI to reveal another applicant's record or perform an action without approval.

**Defence:** the server verifies the applicant and checks ownership. Model arguments cannot select the owner or approve an action. Proposals are tied to the verified session, and approval rechecks the stored details. Incomplete model replies cannot execute tools.

Three failed verification attempts lock the session. Verification expires after 30 minutes. Common identity, mobile, email and credential patterns are masked before model input, stored conversation history and traces. Session tokens and identity credentials are stored as hashes.

Controlled-provider tests attempted cross-owner access, unavailable email tools, cross-session approvals and action replay; the host rejected them. Live-model attack evaluation is still pending. [Security evidence](docs/SECURITY.md).

**Lethal trifecta:** applicant records are potentially private data; user messages and documents are untrusted input; the inference provider is an external destination. Relevant questions and tool results still reach OpenRouter, even without email or arbitrary network tools. Only synthetic data is intended for this demo.

## Limitations

Demo verification is not a production identity system. Scheduling uses dates rather than hourly capacity, and public holidays are not implemented. Refunds are local requests; no payment gateway is connected. Cost reservations are estimates, not verified billing. Public hosting requires an access code and provider spending limits; the free Render configuration has temporary storage that can reset.

## Acknowledgements

Thanks to SDAIA Academy and the course instructor for the practical examples connecting AI assistants, tools, evaluation and security.

[Course requirements](https://github.com/SDAIAAcademy/agentic-ai/tree/main/labs/capstone) · [Synthetic data sources](data/ATTRIBUTION.md) · [Tests](tests/)
