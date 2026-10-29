# Try Rafeeq

[Open the demo](https://rafeeq-demo-pcbf.onrender.com/) · [Project overview](../README.md)

Rafeeq is an AI assistant for a fictional municipality. All example applications and identity details are made up.

## Search without signing in

Type a policy question and select **Search policies**. This searches the policy documents directly without an AI-provider request. The A/B selector changes the local search method.

## Start an AI conversation

Click **Start demo**, write a question and select **Ask AI**.

Ask “What is the fee for a 3 m² illuminated sign?” The expected amount is 750 SAR with source POL-02. Follow-up questions use the current session's conversation.

## Try an application request

Use the separate verification form:

| Field | Synthetic value |
|---|---|
| Application | `MDR-1001` |
| Last four ID digits | `0001` |
| Registered mobile | `0550001001` |

The same fictional applicant owns these applications:

- `MDR-1001`: under review; suitable for checking status, inspection proposals and overdue escalation.
- `MDR-1002`: rejected; a refund request should calculate 650 SAR.
- `MDR-1003`: withdrawn before review; a 1,280 SAR refund request must wait for finance review after user approval.

Example requests:

- “Check application MDR-1001.”
- “Prepare an inspection for MDR-1001 on a future Sunday–Thursday date.”
- “Show my inspection dates, then prepare a change to another working date.”
- “Prepare a refund request for MDR-1002.”

A proposed action appears in the approval section. Review the application, date and amount, then approve or reject it. The demo records approved actions locally; it never pays money or emails anyone.

## Sessions and shared sample data

Your conversation and pending requests belong to the current session. After refreshing the page or opening a new tab, click **Start demo** to begin a new conversation.

The fictional application records are shared, so an earlier visitor may already have created an inspection or refund. A duplicate-action rejection is expected in that case. Sample data may reset between visits.

Use the fictional verification details listed above when trying application requests.
