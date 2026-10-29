# Security evidence

[Project overview](../README.md)

## Threat and defence

An attacker asks the assistant to retrieve another applicant's record and send it to an external email address. The model may follow an untrusted instruction, so enforcement belongs to the host program.

- **Private data:** synthetic application records. The server supplies the applicant identity; model arguments cannot select another owner.
- **Untrusted input:** user questions and retrieved text. These are data, not permission to access another record or execute a write.
- **External destination:** OpenRouter receives questions and relevant tool results. Email and arbitrary network-fetch tools are unavailable.

These are the three exposure points considered in the lethal-trifecta analysis. Removing an email tool does not eliminate inference-provider exposure.

## Reproduce the attack checks

From the project directory, after `uv sync --frozen`:

```bash
uv run --frozen pytest -q \
  tests/test_system.py::test_unavailable_tools_and_cross_owner \
  tests/test_system.py::test_approval_ownership_and_replay \
  tests/test_regressions.py::test_incomplete_reply_cannot_create_proposal
```

| Attempt | Enforced boundary | Observed result |
|---|---|---|
| Request `MDR-2001` as the demo applicant | Ownership check in `Store.application` | Rejected without returning the other record's status |
| Request `send_email` | Explicit dispatch allowlist | Rejected; no email tool exists |
| Book through a proposal before approval | Proposal and executor are separate | No inspection exists before the human decision |
| Approve another owner's proposal or replay a decision | Owner check, pending-state check and database constraint | Rejected |
| Submit a truncated reply containing a proposal tool call | Finish-reason check before tool execution | No proposal or inspection created |

These tests use temporary databases, synthetic records and controlled provider responses. They exercise the real MCP and host boundaries without an inference key. They do not measure how often a live model follows an injection, or establish a live attack success rate.

## Live coverage and remaining risks

The `injection`, `other-status` and `scope` cases are included in `tasks.jsonl`. Their live A/B outcomes are pending until a usable OpenRouter key is available. No undefended live control was run, so there is no measured before/after leak rate.

This is a synthetic multi-session demo with two fixture applicant identities and a shared site access code. Production use requires independent accounts, storage protection, provider-processing review and operational controls. A successful handler test is evidence for that boundary, not a claim that the whole system is secure.


## Additional session and privacy coverage

`tests/test_features.py` checks credential normalisation, three-attempt lockout, verification expiry, owner-switch rejection, cross-session action denial, memory isolation/redaction, and concealed validation errors. It also covers refund amounts and finance gating, stale rescheduling, duplicate-action prevention, and verified escalation.

Verification credentials are entered outside chat and stored as salted hashes. Conversation memory contains bounded redacted text, not raw verification fields or tool transcripts. Session-token hashes scope memory and action approvals. The shared code and public demo fixture credentials are not production authentication. Redaction is pattern-based and cannot guarantee removal of every possible sensitive detail.
