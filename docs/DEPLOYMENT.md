# Share a hosted demo

[Project overview](../README.md)

`render.yaml` prepares this repository for a free Render web service. A hosting account is required. AI chat needs an inference key; public local policy search does not. Public demo URL: https://rafeeq-demo-pcbf.onrender.com/. Visitors use [the visitor guide](USER_GUIDE.md); the setup steps below are for hosting the service.

## Render setup

1. Sign in to [Render](https://dashboard.render.com/) and connect the GitHub account that can access this private repository.
2. Create a **Blueprint** from `mohamed-alghazi/Rafeeq`, using branch `main`. Render reads `render.yaml`.
3. Enter `OPENROUTER_API_KEY` and a long, random `RAFEEQ_ACCESS_TOKEN` in the service's secret environment variables. Never add them to GitHub source files.
4. Review the selected plan and deploy. The included configuration selects the free plan, without paid persistent storage.
5. When the service is live, use the HTTPS address displayed by Render. Check `/health`, then test a real chat request before sharing it.

Visitors click **Start demo** and do not need a code, account or API key. Anonymous sessions are created by `POST /api/visitors`. The optional `RAFEEQ_ACCESS_TOKEN` remains private and protects the separate private-session API. Keep it, the OpenRouter key and hosting-account credentials out of visitor instructions. No additional per-visitor or daily quotas are imposed by this application; the inference provider's own availability and limits still apply.

Visitor-facing instructions: [USER_GUIDE.md](USER_GUIDE.md).

## Tester flow

1. Open the service and click **Start demo** to start an isolated visitor session.
2. The public policy-search button works without an access code or inference key. AI chat uses the provider key configured on the server; public questions do not require applicant verification.
3. For application actions, use the separate verification form. The intentionally public synthetic applicant is:

| Field | Synthetic value |
|---|---|
| Application | `MDR-1001` |
| Last four ID digits | `0001` |
| Registered mobile | `0550001001` |

The same applicant owns `MDR-1002` (rejected, refund 650 SAR), `MDR-1003` (withdrawn before review, refund 1,280 SAR), `MDR-1004` (withdrawn during review) and `MDR-1005` (duplicate payment).

`MDR-2001` belongs to another synthetic applicant. The first applicant must not be able to read or modify it. Separate sessions isolate conversation history and pending approvals; the underlying demo application records are shared synthetic fixtures.

Before approving an action, review its application, date or calculated amount. Large refunds remain pending finance. This demo never pays money or contacts an actual municipality.

## Hosting limitations

- Free Render storage is temporary. `/tmp/rafeeq-demo.sqlite` can disappear after a restart or redeploy; sessions, actions and history can reset. It is unsuitable for real records.
- Free services can sleep when inactive. The first request may take longer.
- Visitors use anonymous session tokens, not production user accounts. Verification lockout is per session. Private-session tokens still require the private API access code.
- Set an appropriate spending limit on the provider account. Local spending reservations are estimates, and each chat turn can make several inference requests.
- Only public/synthetic information belongs in this demo. Prompts and selected tool results reach the external provider.

A deployment is verified only after the actual hosted service starts and passes the representative fee, verification and approval checks. A committed configuration alone is not a deployed website.


## AI chat errors

In Render's Environment settings, set `RAFEEQ_MODEL=openrouter/free` for the free-router demo default. Keep the API key under `OPENROUTER_API_KEY`, and enter only the key value, without `Bearer`, quotes or a variable-name prefix. Save changes and redeploy the latest commit.

`/health` reports whether a key is present, plus the selected provider and model. `provider_configured=true` does not prove that the provider accepts the key or has remaining quota.

| Error code | Action |
|---|---|
| `provider_configuration_error` | Check the selected provider, key variable and model ID. |
| `provider_key_rejected` | Replace the rejected provider key in Render's secret environment settings. |
| `provider_credits_required` | Check the provider account balance and model pricing. |
| `provider_access_denied` | Check key permissions, model access and provider restrictions. |
| `provider_model_unavailable` | Select an available tool-capable model, or the free router for demo use. |
| `provider_rate_limited` | Wait before retrying or check the provider's free quota. |
| `provider_request_rejected` | Check model/tool compatibility and request settings. |
| `provider_connection_failed` / `provider_timeout` | Check provider reachability or retry after an outage. |
| `assistant_runtime_error` | Check Render logs for the safe error code and exception types; the failure is not necessarily from the provider. |

Raw provider error bodies, keys and credentials are not returned or logged by the diagnostic handler. Local policy search remains available without inference.
