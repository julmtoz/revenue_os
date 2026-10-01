# Digital Growth Engine ↔ n8n Bridge

This branch turns Revenue OS into a reusable execution service for Project 5.

## Architecture

- **ChatGPT** — conversational command/control layer
- **n8n** — durable workflow engine, scheduling, connectors, approvals, retries
- **Revenue OS** — local business logic: lead discovery, scoring, audits, outreach drafts, mission/approval state
- **Google Sheets / CRM** — optional visibility and handoff layer

The rule is simple: **n8n coordinates; Revenue OS decides and executes bounded local actions.**

## Start the bridge

```bash
python -m pip install -r requirements.txt
uvicorn api:app --host 127.0.0.1 --port 8787
```

For Docker-hosted n8n on the same Windows machine, use the host-reachable address for Revenue OS (for Docker Desktop this is commonly `host.docker.internal:8787`).

Set `DGE_API_KEY` in Revenue OS and send the same value as the `X-DGE-API-Key` header from n8n.

## V1 endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Bridge/safety status |
| GET | `/v1/summary` | Revenue OS daily summary |
| POST | `/v1/missions` | Queue a mission |
| GET | `/v1/missions/{id}` | Read mission state |
| GET | `/v1/leads` | List scored leads |
| POST | `/v1/leads/hunt` | Run bounded lead discovery |
| POST | `/v1/audits` | Build an opportunity audit |
| POST | `/v1/outreach/drafts` | Create drafts only |
| GET | `/v1/approvals` | Read pending approvals |
| POST | `/v1/approvals/{id}/decision` | Approve/reject a queued action |

## Safety defaults

Revenue OS already defaults to:

- `DRY_RUN=true`
- `APPROVAL_MODE=true`
- `ALLOW_EXTERNAL_SEND=false`
- `ALLOW_WEBSITE_EDIT=false`

The bridge preserves those boundaries. V1 creates drafts and queues work; it does not send outreach.

## DGE-01: lead research → draft queue

Import `n8n/workflows/dge-01-lead-research-to-drafts.json` into n8n.

Flow:

1. Manual trigger
2. Set market/city/niche
3. Health check
4. Lead hunt
5. Read qualified leads
6. Generate outreach drafts in mock mode by default
7. Read approval queue
8. Return a compact result

This is intentionally the smallest useful slice. Once it runs end-to-end, add:
- demand-signal collection,
- Google Sheets evidence logging,
- CRM handoff,
- human approval buttons,
- Gmail draft creation,
- reply classification,
- client onboarding.

## Reusable agency patterns we are borrowing

We are adopting proven patterns rather than copying whole third-party systems:

- webhook/API entry points
- human-in-the-loop approval gates
- lead normalization and scoring
- CRM/Sheet logging
- Gmail draft-before-send
- retries/error workflows
- deduplication before outbound actions
- structured webhook responses

These map cleanly onto Revenue OS's existing mission, approval, lead, audit, and draft objects.
