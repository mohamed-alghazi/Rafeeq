# Deployment guide

[Project overview](../README.md)

`render.yaml` defines a free Render web service. AI chat requires an inference key; local policy search runs without one. The public demo is at https://rafeeq-demo-pcbf.onrender.com/. Usage instructions are in the [visitor guide](USER_GUIDE.md).

## Render setup

1. Sign in to [Render](https://dashboard.render.com/) and connect the GitHub account that can access this private repository.
2. Create a **Blueprint** from `mohamed-alghazi/Rafeeq`, using branch `main`. Render reads `render.yaml`.
3. Set `OPENROUTER_API_KEY` in the service's secret environment variables. `RAFEEQ_ACCESS_TOKEN` is optional and protects the separate private-session API.
4. Review the selected plan and deploy. The included configuration selects the free plan, without paid persistent storage.
5. Check `/health`, then run the functional checks below at the service's HTTPS address.

`POST /api/visitors` creates an anonymous session when **Start demo** is selected. Browser sessions do not use `RAFEEQ_ACCESS_TOKEN`. The application imposes no per-visitor or daily quotas; provider availability and limits still apply.

## Functional checks

| Check | Expected result |
|---|---|
| `GET /health` | HTTP 200 and `status: ok` |
| Start demo | A new session opens |
| Search for illuminated-sign fees | Policy `POL-02` is returned |
| Ask for the fee of a 3 m² illuminated sign | 750 SAR, citing `POL-02` |
| Verify the synthetic applicant below | Application requests become available |
| Prepare a future inspection | The proposal waits for approval |

Synthetic verification fixture:

| Field | Synthetic value |
|---|---|
| Application | `MDR-1001` |
| Last four ID digits | `0001` |
| Registered mobile | `0550001001` |

The same applicant owns `MDR-1002` (rejected, refund 650 SAR), `MDR-1003` (withdrawn before review, refund 1,280 SAR), `MDR-1004` (withdrawn during review) and `MDR-1005` (duplicate payment).

`MDR-2001` belongs to another synthetic applicant. The first applicant must not be able to read or modify it. Separate sessions isolate conversation history and pending approvals; the underlying demo application records are shared synthetic fixtures.

Refunds above 1,000 SAR remain pending finance after approval. The demo does not pay money or contact an actual municipality.

## Hosting limitations

- Free Render storage is temporary. `/tmp/rafeeq-demo.sqlite` can disappear after a restart or redeploy; sessions, actions and history can reset. It is unsuitable for real records.
- Free services can sleep when inactive. The first request may take longer.
- Visitors use anonymous session tokens, not production user accounts. Verification lockout is per session. Private-session tokens still require the private API access code.
- Inference costs depend on provider pricing. Local spending reservations are estimates, and each chat turn can make several inference requests.
- Only public/synthetic information belongs in this demo. Prompts and selected tool results reach the external provider.

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
