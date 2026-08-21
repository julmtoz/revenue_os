# Revenue OS

A local, CLI-first operating system for a solo agency selling automation and lead generation to home-service businesses. Revenue OS coordinates lead discovery, scoring, outreach drafting, and site audits through a small Python application with SQLite persistence and approval-gated workflows.

## Recruiter summary

Revenue OS demonstrates backend-oriented Python development, workflow orchestration, browser automation, relational data modeling, CLI design, scheduled jobs, structured logging, and safety controls around external actions.

**Engineering focus:** Python, Typer, SQLite, SQL, Playwright, APScheduler, Streamlit, OpenAI API integration, deterministic mock mode, approval gates, dry-run controls, and operational logging.

**Current status:** Working local system. It is intentionally designed as a local, operator-controlled tool rather than a hosted SaaS product. External sending, file deletion, website editing, and job-application actions are disabled by default.

## What it does

- Discovers and scores home-service business leads using Playwright and fallback geocoding
- Stores leads, email drafts, audits, and operational logs in SQLite
- Generates personalized outreach drafts for review
- Produces website audit and opportunity memos
- Exports leads and drafts for controlled review
- Runs scheduled jobs with errors captured in logs
- Provides a read-only Streamlit dashboard
- Supports deterministic mock mode for safe local testing

## Architecture

- **CLI layer:** Typer commands for initialization, scraping, exports, drafting, audits, scheduling, and preflight checks
- **Agent layer:** Lead hunting, outreach drafting, and audit-offer workflows
- **Data layer:** SQLite schema and typed models for leads, email drafts, audits, and status transitions
- **Operations layer:** APScheduler jobs, JSONL/SQLite logging, preflight checks, and safety controls
- **Interface layer:** Read-only Streamlit dashboard plus optional Telegram command interface

## Safety and configuration

Copy `.env.example` to `.env` and provide local credentials. Secrets and runtime state are intentionally excluded from version control.

The default configuration requires approval and dry-run behavior:

- `DRY_RUN=true`
- `APPROVAL_MODE=true`
- `ALLOW_EXTERNAL_SEND=false`
- `ALLOW_FILE_DELETE=false`
- `ALLOW_WEBSITE_EDIT=false`
- `ALLOW_JOB_APPLY=false`

The project is designed to keep automation reviewable and operator-controlled.

---

## Quick start

```bash
# 1. Create and activate virtualenv
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browser (one-time)
playwright install chromium

# 4. Configure secrets
cp .env.example .env
# Edit .env — set OPENAI_API_KEY, DEFAULT_CITY, DEFAULT_NICHE

# 5. Initialize database
python cli.py init-db

# 6. Verify everything is ready
python cli.py preflight
```

`preflight` checks: database exists, export/log dirs created, OpenAI key present, Playwright detected.

All green → you're ready to run the full pipeline.

---

## The full pipeline

```bash
# Step 1 — Hunt leads
python cli.py scrape --city "Newark" --niche "roofing" --limit 25

# Step 2 — Review what landed
python cli.py export-leads

# Step 3 — Generate outreach drafts
python cli.py generate-emails --limit 20 --status reviewed

# Step 4 — Export drafts for review
python cli.py export-emails

# Step 5 — Produce an audit memo
python cli.py audit --lead-id <id>

# Step 6 — Launch the local dashboard
python cli.py dashboard
```

### Mock mode

Both `generate-emails` and `audit` support `--mock` for deterministic local output without an API key:

```bash
python cli.py generate-emails --limit 5 --mock
python cli.py audit --lead-id 6 --mock
```

---

## CLI reference

| Command | Key options | Description |
|---|---|---|
| `init-db` | — | Create SQLite tables |
| `preflight` | — | Verify environment readiness |
| `scrape` | `--city` `--niche` `--limit` | Discover and score leads |
| `export-leads` | `--status` | Export leads to CSV |
| `generate-emails` | `--limit` `--status` `--mock` | Draft outreach emails |
| `export-emails` | `--status` | Export drafts to CSV |
| `audit` | `--lead-id` `--mock` | Generate an audit memo |
| `schedule` | — | Start scheduled jobs |
| `dashboard` | `--port` | Launch the read-only dashboard |

---

## Lead statuses

Leads move through a ranked pipeline:

| Status | Meaning |
|---|---|
| `new` | Just scraped, not yet reviewed |
| `qualified` | Score ≥ 7.0 with reliable contact information |
| `reviewed` | Needs manual review |
| `stub` | Fallback placeholder, never contact |
| `emailed` | Outreach sent |
| `replied` | Lead responded |
| `interested` | Lead expressed interest |
| `audit_ready` | Audit memo generated |
| `closed_won` | Deal closed |
| `closed_lost` | Deal did not convert |

Scoring considers website presence, phone validity, niche match, city match, and source trust. Fallback stubs are automatically excluded from outreach.

---

## Email sendability labels

| Label | Meaning |
|---|---|
| `sendable` | High personalization and a valid contact path; ready for review |
| `needs_edit` | Some signals are missing; manual editing required |
| `do_not_send` | Stub lead or no valid contact path |

---

## Scrape fallback chain

1. Playwright + Google Maps
2. Nominatim / OpenStreetMap fallback
3. Fallback stubs excluded from outreach

---

## Scheduler

```bash
python cli.py schedule
# Runs until Ctrl+C
```

Jobs:

- **8:00am and 2:00pm** — scrape the configured city and niche
- **9:00am** — draft outreach for workable leads

Job errors are caught and logged so the scheduler can continue running.

---

## Project layout

```
revenue_os/
├── agents/              # Lead hunter, outreach, and audit workflows
├── core/                # Configuration, database, models, logging, scheduler
├── prompts/             # Jinja2 templates for outreach and audits
├── data/                # Local SQLite database, ignored by Git
├── exports/             # CSV exports and audit memos, ignored by Git
├── logs/                # JSONL operational logs, ignored by Git
├── cli.py               # Typer CLI entrypoint
├── dashboard.py         # Streamlit read-only command center
├── requirements.txt
├── .env.example
└── README.md
```

---

## Roadmap

- Add PageSpeed and email-enrichment integrations
- Add controlled Gmail or webhook delivery behind explicit approval
- Containerize for a VPS deployment after ROI validation
- Add a small test suite around scoring, status transitions, and safety controls

Keep it local, lean, and revenue-focused.
