# Share a hosted demo

[Project overview](../README.md)

`render.yaml` prepares this repository for a free Render web service. A hosting account is required. AI chat needs an inference key; public local policy search does not. No public service has been deployed from this workspace.

## Render setup

1. Sign in to [Render](https://dashboard.render.com/) and connect the GitHub account that can access this private repository.
2. Create a **Blueprint** from `mohamed-alghazi/Rafeeq`, using branch `main`. Render reads `render.yaml`.
3. Enter `OPENROUTER_API_KEY` and a long, random `RAFEEQ_ACCESS_TOKEN` in the service's secret environment variables. Never add them to GitHub source files.
4. Review the selected plan and deploy. The included configuration selects the free plan, without paid persistent storage.
5. When the service is live, use the HTTPS address displayed by Render. Check `/health`, then test a real chat request before sharing it.

A tester needs the site address and the **site access code** (`RAFEEQ_ACCESS_TOKEN`). The OpenRouter API key stays on Render and is never shared with testers.

## Tester flow

1. Open the service and enter the site access code to start an isolated session.
2. The public policy-search button works without an access code or inference key. AI chat requires the site access code and a configured provider key; public questions do not require applicant verification.
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
- The shared access code is an invitation gate for a synthetic demo, not separate production user accounts. Verification lockout is per session.
- Set an appropriate spending limit on the provider account. Local spending reservations are estimates, and each chat turn can make several inference requests.
- Only public/synthetic information belongs in this demo. Prompts and selected tool results reach the external provider.

A deployment is verified only after the actual hosted service starts and passes the representative fee, verification and approval checks. A committed configuration alone is not a deployed website.
