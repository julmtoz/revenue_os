# Changelog

## [Phase 2] — 2026-05-23
### Added
- Kill switch (`pause-all` / `resume`) — instant system halt
- Retry logic in BaseAgent (max 2 retries with 2s delay)
- Telegram notification system (`core/notifier.py`)
- Database and config backup system (`core/backup.py`)
- API cost tracker per agent/model/day (`core/cost_tracker.py`)
- Agent contracts (YAML specs) for all 6 active agents
- Prompt library (`prompts/library.yaml`) with 6 reusable prompt templates
- Post-mission evaluation loop with agent performance scoring
- New CLI commands: pause, resume, status, backup, eval, performance, costs, notify, automate-candidates, contracts

## [Phase 1] — 2026-05-23
### Added
- Mission system (missions/approvals/memory SQLite tables)
- Safety controls (DRY_RUN, APPROVAL_MODE) in config
- BaseAgent abstract class with dry_run_guard
- SupremeOrchestrator with department routing
- ResearchAgent, ITGuardianAgent, JobScoutAgent, ExecutiveAgent, SEOAuditorAgent
- 12 CLI commands: briefing, missions, approvals, approve, reject, research, seo-audit, it-sop, it-incident, jobs, daily-summary, mission-create

## [Foundation] — 2026-03 (pre-phase)
### Existing
- LeadHunter agent (Google Maps + Nominatim scraping)
- AuditOffer agent (website auditor with OpenAI)
- Outreach agent (email draft generator)
- Core CLI: scrape, audit, generate-emails, export-leads, export-emails, schedule, dashboard
