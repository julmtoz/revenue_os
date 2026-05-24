# Revenue OS

A local, CLI-first operating system for a solo agency selling automation + lead-gen to home-service businesses.
Three independent agents, one SQLite database, zero SaaS dependencies.

Repository note: this directory is versioned independently from the parent OpenClaw workspace. Runtime state such as `.env`, SQLite databases, logs, exports, backups, virtualenvs, and `__pycache__` should stay untracked.

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

Run these in order on a fresh environment:

```bash
# Step 1 — Hunt leads (Playwright → Google Maps, Nominatim fallback)
python cli.py scrape --city "Newark" --niche "roofing" --limit 25

# Step 2 — Review what landed
python cli.py export-leads

# Step 3 — Generate outreach drafts (OpenAI)
python cli.py generate-emails --limit 20 --status reviewed

# Step 4 — Export drafts for review
python cli.py export-emails

# Step 5 — Produce an audit memo for a high-value lead
python cli.py audit --lead-id <id>

# Step 6 — Launch the local dashboard
python cli.py dashboard
```

### Mock mode (no API key needed)

Both `generate-emails` and `audit` support `--mock` for deterministic local output:

```bash
python cli.py generate-emails --limit 5 --mock
python cli.py audit --lead-id 6 --mock
```

---

## CLI reference

| Command | Key options | Description |
|---------|-------------|-------------|
| `init-db` | — | Create SQLite tables |
| `preflight` | — | Verify env is ready (DB, dirs, key, Playwright) |
| `scrape` | `--city` `--niche` `--limit` | Lead Hunter: Playwright scrape → Nominatim → stub fallback |
| `export-leads` | `--status` | Dump leads table → `exports/leads-*.csv` |
| `generate-emails` | `--limit` `--status` `--mock` | Outreach agent: OpenAI email drafts |
| `export-emails` | `--status` | Dump emails table → `exports/emails-*.csv` |
| `audit` | `--lead-id` `--mock` | Audit agent: fetch site + OpenAI opportunity memo |
| `schedule` | — | Start APScheduler (scrape 8am/2pm, emails 9am) |
| `dashboard` | `--port` | Local read-only Streamlit command center |

---

## Lead statuses

Leads move through a ranked pipeline. Higher rank = further along:

| Status | Meaning |
|--------|---------|
| `new` | Just scraped, not yet reviewed |
| `qualified` | Score ≥ 7.0, reliable contact info |
| `reviewed` | Score 5–7, or thin contact — needs manual check |
| `stub` | Fallback placeholder, never contact |
| `emailed` | Outreach sent |
| `replied` | Lead responded |
| `interested` | Expressed interest |
| `audit_ready` | Audit memo generated |
| `closed_won` | Deal closed |
| `closed_lost` | Not converting |

**Scoring** is weighted across: website presence, phone validity, niche match, city match, source trust.
Nominatim leads carry a −1.0 trust penalty. Fallback stubs carry −8.0 and are permanently excluded from outreach.

---

## Email sendability labels

Every draft gets one of three labels:

| Label | Meaning |
|-------|---------|
| `sendable` | High personalization + score ≥ 7 + valid contact → ready to review and send |
| `needs_edit` | Some signals missing — review before sending |
| `do_not_send` | Stub lead, or no valid contact path — do not send |

---

## Scrape fallback chain

1. **Playwright + Google Maps** — primary source, real business cards with phone numbers
2. **Nominatim (OpenStreetMap)** — fires if Playwright returns nothing; thin coverage for home-service niches
3. **Fallback stubs** — placeholder rows (`source=fallback_stub`) when both above return nothing; excluded from all outreach automatically

---

## Scheduler

```bash
python cli.py schedule
# Runs until Ctrl+C
```

Jobs:
- **8:00am + 2:00pm** — `lead_scrape`: scrapes `DEFAULT_CITY` / `DEFAULT_NICHE` for 25 leads
- **9:00am** — `generate_emails`: drafts up to `DAILY_OUTREACH_CAP` emails for workable leads

Job errors are caught and logged to the `logs` SQLite table — the scheduler stays running even if a job fails.

---

## Project layout

```
revenue_os/
├── agents/
│   ├── lead_hunter/      # Playwright scrape + Nominatim fallback + scoring
│   ├── outreach/         # OpenAI email draft generation
│   └── audit_offer/      # Site fetch + OpenAI opportunity memos
├── core/
│   ├── config.py         # Settings dataclass, env vars, scoring weights
│   ├── db.py             # SQLite schema + upsert helpers
│   ├── logger.py         # JSONL + SQLite logging
│   ├── models.py         # Lead, EmailDraft, Audit dataclasses + status rank
│   └── scheduler.py      # APScheduler job wiring
├── prompts/              # Jinja2 templates for outreach + audit
├── data/                 # SQLite DB (revenue_os.db)
├── exports/              # CSV dumps + audit markdown files
│   └── audits/           # lead-{id}.md opportunity memos
├── logs/                 # JSONL action logs (actions-YYYY-MM-DD.jsonl)
├── cli.py                # Typer CLI entrypoint
├── dashboard.py          # Streamlit read-only command center
├── requirements.txt
├── .env.example
└── README.md
```

---

## Configuration (.env)

```bash
OPENAI_API_KEY=sk-...          # Required for generate-emails and audit
DEFAULT_CITY=Newark            # Default scrape target
DEFAULT_NICHE=roofing          # Default scrape niche
OPENAI_MODEL_EMAIL=gpt-4.1-mini
OPENAI_MODEL_AUDIT=gpt-4.1-mini
OPENAI_MODEL_SCORING=gpt-4o-mini
DAILY_OUTREACH_CAP=25          # Max drafts per scheduler run

# Scoring weight overrides (optional)
WEIGHT_HAS_WEBSITE=1
WEIGHT_MISSING_WEBSITE=-2
WEIGHT_HAS_PHONE=1
WEIGHT_VALID_PHONE=1.5
WEIGHT_NICHE_MATCH=2
WEIGHT_CITY_MATCH=2
WEIGHT_STUB_PENALTY=-8
```

---

## Post-v1 ideas

- Enrich leads with PageSpeed scores, Hunter email lookup
- Wire Gmail/Instantly for controlled sending (with `sendable` guard)
- Add Telegram/Slack webhook for scheduler alerts
- Containerize for VPS once ROI is validated

Keep it local, lean, and revenue-focused.
