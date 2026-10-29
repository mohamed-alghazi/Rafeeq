# رفيق | Rafeeq

A municipal-services assistant for the fictional city of Madar. It explains fees, checks application status and prepares inspection requests for human approval. All records are synthetic.

Built for [Advanced Agentic AI Systems Engineering - SDAIA Academy](https://github.com/sdaiaacademy/agentic-ai/), Track 1: **Rafeeq in production**.

## Features

- Policy retrieval with source references and programmatic fee calculation.
- Application lookup restricted to the current applicant.
- Inspection proposals with a separate approval step before booking.
- A bounded agent loop with context, tool-call and estimated spending limits.
- **18 evaluation tasks**, two configurations and **4 tools**, including two over MCP.

## Tools

| Tool | Purpose | MCP | Human approval |
|---|---|---|---|
| `search_policy` | Retrieve relevant policy documents | Yes | No |
| `calculate_fee` | Compute fees using the published synthetic schedule | Yes | No |
| `get_application` | Read an application owned by the current applicant | No | No |
| `propose_inspection` | Create a pending inspection proposal | No | Required before booking |

For example, a 3 m² illuminated sign costs **750 SAR**: 600 SAR base fee plus a 150 SAR surcharge, according to `POL-02`.

## Stack and setup

Python 3.11+, FastAPI, SQLite, HTML/JavaScript, OpenRouter and MCP. The default model is `google/gemma-4-31b-it:free`, following the course labs; live model quality has not been measured yet.

```bash
uv sync --frozen
cp -n .env.example .env
```

Set `OPENROUTER_API_KEY` and a long, random `RAFEEQ_ACCESS_TOKEN` in `.env`. Preserve an existing `.env` when updating. The API key stays server-side; `.env` is excluded from Git.

```bash
uv run --frozen uvicorn rafeeq.api:app --host 127.0.0.1 --port 8000
```

The browser interface uses `RAFEEQ_ACCESS_TOKEN` for access. [Technical guide and cloud setup](docs/TECHNICAL.md).

## Evaluation

The [suite](tasks.jsonl) contains **18 tasks**, exceeding the course minimum of 15: fees, retrieval, application lookup, security, approval and clarification.

**A:** base instructions. **B:** the same setup with an additional instruction to retrieve policies before fee or policy answers. Tools, model and security controls remain the same.

| Configuration | Planned tasks | Live evaluations completed | Pass rate |
|---|---:|---:|---|
| A | 18 | 0 | Not measured |
| B | 18 | 0 | Not measured |

**35 automated tests pass.** These test application behavior and security controls, not live model quality. OpenRouter credentials were unavailable during validation; the live A/B evaluation is still pending.

```bash
uv run --frozen pytest -q
uv run --frozen python -m rafeeq.evaluate tasks.jsonl --config A B --trials 1
```

The first command needs no inference key. The second requires one and saves CSV results, traces, a summary and error analysis under `results/`. Graders check answer values, successful tool execution, policy citations and database state. Runtime errors and pending tasks are reported separately from scored outcomes. Existing results are preserved; a new run requires a new output directory. [Evaluation status](results/README.md).

## Security analysis

**Threat:** an instruction asks the assistant to read another applicant's record and send it to an external address.

| Risk | Enforced protection |
|---|---|
| Access to another applicant's record | Server-owned applicant identity and ownership checks before lookup |
| Sending records to an attacker | No model-facing email or arbitrary network-fetch tool |
| Booking without consent | The model creates a proposal; a separate authenticated endpoint handles approval |
| Executing an incomplete model reply | Truncated replies cannot execute their requested tools |
| Repeating an approved action | A database constraint prevents executing the same approval twice |

**Tested attack:** a controlled-provider test requested `MDR-2001`, belonging to a different synthetic applicant, and attempted an unavailable email tool. Both calls were rejected. Additional tests cover approval ownership, replay and incomplete replies. This validates code-enforced boundaries; the live-model injection task remains pending.

**Lethal trifecta:** application records are potentially private data; user messages and retrieved content are untrusted input; OpenRouter inference is an external destination. No arbitrary network tool is available, but prompts and relevant tool results still reach the inference provider. Only synthetic data is intended for this prototype.

[Security test evidence and reproduction commands](docs/SECURITY.md).

## Course requirements

| Requirement | Evidence | Status |
|---|---|---|
| At least 3 tools, including MCP | 4 tools; retrieval and calculation use MCP | Implemented and tested |
| Context specification, retrieval and a budget rule | `rafeeq/spec.md`, policy search and bounded context | Implemented and tested |
| Human-approved write and execution limits | Separate approval endpoint, step/tool limits and estimated spending reservations | Implemented and tested; actual provider billing is not enforced |
| At least 15 tasks executed on both configurations | 18 tasks and A/B graders; 0 live tasks completed per configuration | **Incomplete: inference key required** |
| Security analysis, attack and defence | Ownership, unavailable-tool, approval and truncated-reply tests | Code controls tested; live-model attack pending |

## Limitations

The demo has one applicant identity, local inspection storage and no production identity system. Scheduling does not account for appointment capacity or public holidays. The web interface does not retain conversation history. Spending reservations are estimates, not verified provider charges. Production use requires separate accounts, stronger data protection and a review of provider processing terms.

## Acknowledgements

Thanks to SDAIA Academy and the course instructor for the practical examples connecting context engineering, tool use, evaluation and security.

[Course requirements](https://github.com/SDAIAAcademy/agentic-ai/tree/main/labs/capstone) · [Synthetic data sources](data/ATTRIBUTION.md) · [Tests](tests/)
