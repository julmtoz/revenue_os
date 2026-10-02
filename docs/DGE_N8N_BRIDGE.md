# Digital Growth Engine ↔ n8n Bridge

This branch turns Revenue OS into a reusable execution service for Project 5.

## Architecture

- **ChatGPT** — conversational command/control layer
- **n8n** — durable workflow engine, scheduling, connectors, approvals, retries
- **Revenue OS** — local business logic: lead discovery, scoring, audits, outreach drafts, mission/approval state
- **HubSpot** — CRM source of truth
- **Airtable** — DGE evidence/state/experiments handoff
- **Gmail** — draft and human review surface

HubSpot and Airtable writes are future integration work; this sprint verifies the existing local SQLite core and n8n bridge.

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
| POST | `/v1/research` | Run bounded web research through the existing research agent |
| POST | `/v1/market-intelligence/scout/queries` | Generate bounded niche/signal queries with explicit context |
| POST | `/v1/market-intelligence/scout` | Optional synchronous scout through the same research/evidence services |
| POST | `/v1/market-intelligence/evidence/batch` | Persist a batch of market evidence and return a scored shortlist |
| GET | `/v1/market-intelligence/shortlist` | Read the current evidence-ranked market shortlist |
| GET | `/v1/market-intelligence/evidence` | Inspect stored evidence for one niche |
| GET | `/v1/leads` | List scored leads |
| POST | `/v1/leads/hunt` | Run bounded lead discovery |
| POST | `/v1/audits` | Build an opportunity audit |
| GET | `/v1/outreach/drafts` | Read the reviewable draft queue |
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

1. Manual trigger or POST `/webhook/dge/lead-research`
2. Set market/city/niche
3. Health check
4. Lead hunt
5. Read qualified leads
6. Generate mock outreach drafts scoped to the lead IDs from this run; existing local drafts are deduplicated
7. Read approval queue
8. Return a compact `HUMAN_REVIEW` result with counts and `external_send_performed=false`

Webhook intake defaults to synthetic lead discovery (`mock=true`). Explicit `mock=false` enables public lead discovery, while draft generation remains mock-only. Synthetic leads have `source=mock` and `do_not_send` drafts. Drafting never marks a lead `emailed`.

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


## DGE-02: safe Gmail draft handoff

Import `n8n/workflows/dge-02-safe-gmail-draft-handoff.json`.

This workflow only selects drafts that Revenue OS has marked `sendable` **and** that have a real lead email, then creates a Gmail draft. It does not send the message. Gmail remains the human review surface.

## DGE-03: Demand Scout V1

Import `n8n/workflows/dge-03-demand-scout-v0.json`.

The workflow expands a starter set of service-business niches across three evidence classes per niche—demand/spend, hiring, and competition—calls the Revenue OS research agent, persists the evidence in SQLite, computes source/evidence/signal-diversity scores, returns a five-market shortlist, and marks the output `HUMAN_REVIEW`.

POST `/webhook/dge/demand-scout` with `{"niches":["roofing"]}` for the bounded smoke run. Omit niches to generate the existing ten-niche default. The workflow uses HTTP Request, Split Out, and Aggregate nodes; it does not depend on the JavaScript task runner. Each `/v1/research` response retains `context.niche` and `context.signal_type` and includes an explicit success flag. Failed research is counted and excluded from scored evidence.

Research uses Brave, local SearXNG (`SEARXNG_URL`), DuckDuckGo, then Bing HTML. Cached results have the same list shape and result count as fresh results. The shortlist returns up to five markets, depending on how many have been persisted. Scores measure source/evidence/signal diversity, not verified demand or ROI. Human review remains required.

## Windows validation and operation

Use the existing Docker stack and volume. Diagnose with `docker ps -a`, `docker logs`, and `/healthz` before restarting stopped services. Never remove the n8n volume or database. The approved workflows are identified by `dgeLeadResearchToDrafts01`, `dgeSafeGmailDraftHandoff02`, and `dgeDemandScout03`.

Import only the three DGE files through the installed n8n CLI. Imported files are intentionally inactive. Publish DGE-01 and DGE-03 individually and restart n8n to register their production webhooks; wait for `/healthz/readiness` and webhook registration before testing. Leave DGE-02 inactive until the intended existing Gmail credential is selected. It explicitly uses Gmail `resource=draft`, `operation=create`, plain text, and has no send node.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check api.py market_api.py agents/research/research_agent.py agents/outreach/generator.py agents/lead_hunter/lead_hunter.py agents/market_intelligence/service.py tests scripts/smoke_dge.py
.\.venv\Scripts\python.exe -m compileall -q api.py market_api.py agents core orchestrator tests scripts/smoke_dge.py
.\.venv\Scripts\python.exe -u scripts/smoke_dge.py --repeat-scout
```

The smoke script creates a synthetic lead/local draft and performs only a one-niche research run and optional repeat. It never executes Gmail. If `DGE_API_KEY` is configured, pass it through a runtime n8n credential and the script environment; never commit real keys in workflow JSON. Existing placeholder keys must be replaced only in the local instance.

Verified on IT-Cybermatoz, 2026-10-02: both services healthy; DGE-01 created one synthetic lead and one local draft; repeats created no duplicate draft. DGE-03 researched three roofing signals with zero failures, added 25 rows (30 to 55 roofing evidence rows), returned two existing markets under the Top-5 limit, and ended in `HUMAN_REVIEW`. A repeat inserted zero rows and kept the shortlist unchanged. DGE-02 was structurally validated and remained inactive without a credential binding. No external messages were sent. The full ten-niche run was not launched.

Runtime databases, copied n8n databases, transient state, and retained local debug scripts are ignored. Local user data is preserved.
