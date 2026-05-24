"""CLI entrypoint for revenue_os."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import typer

from agents.audit_offer.audit import generate_audit
from agents.lead_hunter.lead_hunter import ScrapeResult, scrape_and_store
from agents.outreach.generator import generate_email_drafts
from agents.research.research_agent import ResearchAgent
from agents.it_guardian.it_guardian_agent import ITGuardianAgent
from agents.job_scout.job_scout_agent import JobScoutAgent
from agents.executive.executive_agent import ExecutiveAgent
from agents.seo_auditor.seo_auditor_agent import SEOAuditorAgent
from core.config import get_settings, has_openai_api_key
from core.db import ensure_db_ready, get_session, init_db, list_missions, list_approvals
from core.logger import get_logger
from core.models import DEPARTMENTS
from core.scheduler import start_scheduler
from orchestrator.supreme_orchestrator import SupremeOrchestrator
from orchestrator.mission_manager import MissionManager
from orchestrator.approval_manager import ApprovalManager

app = typer.Typer(help="Revenue OS CLI")
logger = get_logger()


def _timestamped_path(prefix: str, ext: str) -> Path:
    settings = get_settings()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return settings.export_dir / f"{prefix}-{ts}.{ext}"


def _handle_runtime_error(exc: RuntimeError) -> None:
    typer.secho(f"Error: {exc}", fg="red")
    raise typer.Exit(code=1)


@app.command("init-db")
def init_db_cmd() -> None:
    """Create SQLite tables."""
    init_db()
    typer.echo("Database initialized.")


@app.command()
def scrape(
    city: Optional[str] = typer.Option(None, help="City to target"),
    niche: Optional[str] = typer.Option(None, help="Business niche"),
    limit: int = typer.Option(25, help="Max leads to capture"),
) -> None:
    settings = get_settings()
    city = city or settings.default_city
    niche = niche or settings.default_niche
    result: ScrapeResult = scrape_and_store(city, niche, limit=limit)
    typer.echo(f"Stored {len(result.lead_ids)} leads from {city} / {niche}.")
    if result.fallback_used:
        typer.secho(
            "Playwright scraping failed – stored fallback_stub leads instead (source=fallback_stub).",
            fg="yellow",
        )


@app.command("export-leads")
def export_leads(status: Optional[str] = typer.Option(None, help="Filter by status")) -> None:
    with get_session() as conn:
        query = "SELECT * FROM leads"
        params: tuple[object, ...] = tuple()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        cursor = conn.execute(query, params) if params else conn.execute(query)
        rows = cursor.fetchall()
        if not rows:
            typer.echo("No leads found.")
            return
        df = pd.DataFrame(rows)
    priority_cols = ["id", "name", "city", "category", "score", "status", "source", "phone", "website", "notes"]
    existing = [col for col in priority_cols if col in df.columns]
    ordered_cols = existing + [col for col in df.columns if col not in existing]
    df = df[ordered_cols]
    sort_cols = [col for col in ("status", "score") if col in df.columns]
    if sort_cols:
        asc = [True if col == "status" else False for col in sort_cols]
        df = df.sort_values(by=sort_cols, ascending=asc)
    path = _timestamped_path("leads", "csv")
    df.to_csv(path, index=False)
    typer.echo(f"Exported {len(df)} leads to {path}.")


@app.command("generate-emails")
def generate_emails(
    limit: int = typer.Option(20),
    status: str = typer.Option("qualified", help="Lead status to target (qualified/reviewed/interested/audit_ready)"),
    mock: bool = typer.Option(False, "--mock", help="Generate deterministic local drafts without calling OpenAI"),
) -> None:
    try:
        created = generate_email_drafts(limit=limit, status=status, mock=mock)
    except (RuntimeError, ValueError) as exc:
        _handle_runtime_error(exc)
    typer.echo(f"Generated {created} email drafts.")


@app.command("export-emails")
def export_emails(status: Optional[str] = typer.Option(None)) -> None:
    with get_session() as conn:
        base_query = """
            SELECT
                emails.id AS email_id,
                emails.lead_id,
                leads.name AS lead_name,
                leads.status AS lead_status,
                emails.sendability,
                emails.subject,
                emails.body,
                emails.notes,
                emails.status AS email_status,
                emails.step,
                emails.sent_at,
                emails.created_at
            FROM emails
            JOIN leads ON leads.id = emails.lead_id
        """
        params: tuple[object, ...] = tuple()
        if status:
            base_query += " WHERE emails.status = ?"
            params = (status,)
        cursor = conn.execute(base_query, params) if params else conn.execute(base_query)
        rows = cursor.fetchall()
        if not rows:
            typer.echo("No emails found.")
            return
        df = pd.DataFrame(rows)
    priority_cols = ["email_id", "lead_id", "lead_name", "lead_status", "sendability", "subject", "body", "notes", "email_status", "step", "sent_at", "created_at"]
    existing = [col for col in priority_cols if col in df.columns]
    df = df[existing + [col for col in df.columns if col not in existing]]
    path = _timestamped_path("emails", "csv")
    df.to_csv(path, index=False)
    typer.echo(f"Exported {len(df)} emails to {path}.")


@app.command()
def audit(
    lead_id_arg: Optional[int] = typer.Argument(None),
    lead_id: Optional[int] = typer.Option(None, "--lead-id", help="Lead ID to audit"),
    mock: bool = typer.Option(False, "--mock", help="Generate a deterministic local audit without calling OpenAI"),
) -> None:
    resolved_lead_id = lead_id if lead_id is not None else lead_id_arg
    if resolved_lead_id is None:
        _handle_runtime_error(RuntimeError("Provide a lead ID either as `audit 6` or `audit --lead-id 6`."))
    try:
        path = generate_audit(resolved_lead_id, mock=mock)
    except (RuntimeError, ValueError) as exc:
        _handle_runtime_error(exc)
    typer.echo(f"Audit generated at {path}.")


@app.command()
def schedule() -> None:
    typer.echo("Starting scheduler (Ctrl+C to stop)...")
    start_scheduler()


@app.command()
def dashboard(port: int = typer.Option(8501, help="Local port for the dashboard")) -> None:
    """Launch the local read-only dashboard."""
    if importlib.util.find_spec("streamlit") is None:
        _handle_runtime_error(
            RuntimeError("Streamlit is not installed. Run `pip install -r requirements.txt` first.")
        )

    dashboard_path = Path(__file__).with_name("dashboard.py")
    if not dashboard_path.exists():
        _handle_runtime_error(RuntimeError(f"Dashboard file is missing: {dashboard_path}"))

    env = dict(os.environ)
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    env["STREAMLIT_SERVER_HEADLESS"] = "true"

    typer.echo(f"Launching dashboard at http://localhost:{port}")
    raise typer.Exit(
        code=subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(dashboard_path),
                "--server.port",
                str(port),
                "--server.address",
                "127.0.0.1",
                "--browser.gatherUsageStats",
                "false",
                "--server.fileWatcherType",
                "none",
            ],
            cwd=str(Path(__file__).parent),
            env=env,
        )
    )


@app.command()
def preflight() -> None:
    """Check whether the local env is ready to run the CLI."""
    settings = get_settings()
    issues: list[str] = []

    try:
        ensure_db_ready()
    except Exception as exc:  # pragma: no cover - defensive guard
        issues.append(f"Database: {exc}")

    required_dirs = [settings.export_dir, settings.export_dir / "audits", settings.log_dir]
    for directory in required_dirs:
        if not directory.exists():
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as exc:  # pragma: no cover
                issues.append(f"Directory {directory}: {exc}")

    if not has_openai_api_key():
        issues.append("OPENAI_API_KEY is missing. Add it to .env or export it in your shell.")

    # Check system PATH first, then the active venv's bin dir
    playwright_cli = shutil.which("playwright") or shutil.which(
        "playwright", path=str(Path(sys.executable).parent)
    )
    if not playwright_cli:
        issues.append("Playwright CLI not found. Install with `pip install playwright` and run `playwright install chromium`.")
    else:
        cache_candidates = [
            Path.home() / "Library" / "Caches" / "ms-playwright",
            Path.home() / ".cache" / "ms-playwright",
        ]
        if not any(path.exists() for path in cache_candidates):
            issues.append("Playwright browsers not detected. Run `playwright install chromium`.")

    if importlib.util.find_spec("streamlit") is None:
        issues.append("Streamlit is not installed. Dashboard command needs `pip install -r requirements.txt`.")

    if issues:
        typer.secho("Preflight checks failed:", fg="red")
        for item in issues:
            typer.echo(f"- {item}")
        raise typer.Exit(code=1)

    typer.secho("Preflight OK: database ready, folders created, OpenAI key present, Playwright detected.", fg="green")


@app.command()
def briefing() -> None:
    """Daily briefing — mission status, approvals, priorities."""
    agent = ExecutiveAgent()
    result = agent.run(task="briefing")
    typer.echo(result.output)


@app.command("mission-create")
def mission_create(
    title: str = typer.Argument(..., help="Mission title"),
    department: Optional[str] = typer.Option(None, help=f"Department: {', '.join(DEPARTMENTS)}"),
    priority: int = typer.Option(5, help="Priority 1-10"),
) -> None:
    """Create a new mission."""
    orchestrator = SupremeOrchestrator()
    mission_id = orchestrator.dispatch(title=title, department=department, priority=priority)
    typer.echo(f"Mission #{mission_id} created: {title}")


@app.command("missions")
def missions_list(
    status: Optional[str] = typer.Option(None, help="Filter by status"),
    department: Optional[str] = typer.Option(None, help="Filter by department"),
) -> None:
    """List all missions."""
    with get_session() as conn:
        missions = list_missions(conn, status=status, department=department)
    if not missions:
        typer.echo("No missions found.")
        return
    for m in missions:
        typer.echo(f"[{m['id']}] {m['status'].upper()} | {m['department']} | {m['title']}")


@app.command("approvals")
def approvals_list() -> None:
    """List pending approvals."""
    with get_session() as conn:
        approvals = list_approvals(conn, status="pending")
    if not approvals:
        typer.echo("No pending approvals.")
        return
    for a in approvals:
        typer.echo(f"[{a['id']}] {a['action']} | Mission: {a['mission_id']} | {a['created_at']}")


@app.command("approve")
def approve_action(
    approval_id: int = typer.Argument(...),
    reason: Optional[str] = typer.Option(None),
) -> None:
    """Approve a pending action."""
    manager = ApprovalManager()
    manager.approve(approval_id, reason=reason)
    typer.echo(f"Approved #{approval_id}")


@app.command("reject")
def reject_action(
    approval_id: int = typer.Argument(...),
    reason: Optional[str] = typer.Option(None),
) -> None:
    """Reject a pending action."""
    manager = ApprovalManager()
    manager.reject(approval_id, reason=reason)
    typer.echo(f"Rejected #{approval_id}")


@app.command("research")
def research_cmd(
    query: str = typer.Argument(..., help="What to research"),
) -> None:
    """Run the Research Agent."""
    agent = ResearchAgent()
    result = agent.run(query=query)
    typer.echo(result.output)


@app.command("seo-audit")
def seo_audit(url: str = typer.Argument(..., help="URL to audit")) -> None:
    """Run SEO audit on a website."""
    agent = SEOAuditorAgent()
    result = agent.run(url=url)
    typer.echo(result.output)


@app.command("it-sop")
def it_sop(
    topic: str = typer.Argument(..., help="SOP topic (e.g. 'new device', 'wifi issue')")
) -> None:
    """Generate an IT SOP document."""
    agent = ITGuardianAgent()
    result = agent.run(task="sop", topic=topic)
    typer.echo(result.output)


@app.command("it-incident")
def it_incident(
    description: str = typer.Argument(..., help="Incident description")
) -> None:
    """Create an IT incident report."""
    agent = ITGuardianAgent()
    result = agent.run(task="incident", topic=description)
    typer.echo(result.output)


@app.command("jobs")
def jobs_scan(
    role: str = typer.Option("IT Systems Administrator", help="Job role to search"),
    location: str = typer.Option("New Jersey", help="Location"),
) -> None:
    """Scan for IT job opportunities."""
    agent = JobScoutAgent()
    result = agent.run(role=role, location=location)
    typer.echo(result.output)


@app.command("daily-summary")
def daily_summary() -> None:
    """Print Ozen system summary."""
    orchestrator = SupremeOrchestrator()
    typer.echo(orchestrator.daily_summary())


@app.command("pause")
def pause_system(reason: str = typer.Option("manual", help="Reason for pausing")) -> None:
    """Pause all agent execution (kill switch)."""
    from core.kill_switch import pause_all
    from core.notifier import notify_kill_switch
    pause_all(reason)
    notify_kill_switch(activated=True, reason=reason)
    typer.secho(f"SYSTEM PAUSED: {reason}", fg="red")


@app.command("resume")
def resume_system() -> None:
    """Resume all agent execution."""
    from core.kill_switch import resume_all, is_paused
    from core.notifier import notify_kill_switch
    if not is_paused():
        typer.echo("System is not paused.")
        return
    resume_all()
    notify_kill_switch(activated=False)
    typer.secho("System resumed. Agents are active.", fg="green")


@app.command("status")
def system_status() -> None:
    """Show system status: kill switch, config, costs."""
    from core.kill_switch import is_paused
    from core.cost_tracker import get_daily_cost, get_monthly_cost
    settings = get_settings()
    paused = is_paused()
    daily = get_daily_cost()
    monthly = get_monthly_cost()

    typer.echo(f"System: {'PAUSED' if paused else 'ACTIVE'}")
    typer.echo(f"DRY_RUN: {settings.dry_run} | APPROVAL_MODE: {settings.approval_mode}")
    typer.echo(f"API Cost Today: ${daily['total']:.4f} | This Month: ${monthly['total']:.4f}")
    typer.echo(f"Telegram: {'configured' if settings.telegram_bot_token else 'not set'}")


@app.command("backup")
def backup_cmd() -> None:
    """Backup database and config."""
    from core.backup import backup_db, backup_config, prune_backups
    db_path = backup_db()
    cfg_path = backup_config()
    pruned = prune_backups(keep=10)
    typer.echo(f"DB backup: {db_path}")
    typer.echo(f"Config backup: {cfg_path}")
    if pruned:
        typer.echo(f"Pruned {pruned} old backup(s).")


@app.command("eval")
def evaluate_mission(
    mission_id: int = typer.Argument(...),
    useful: bool = typer.Option(True, help="Was this mission useful?"),
    feedback: str = typer.Option("", help="Optional feedback"),
    automate: bool = typer.Option(False, "--automate", help="Should this become a recurring workflow?"),
) -> None:
    """Evaluate a completed mission."""
    from core.evaluator import record_evaluation
    record_evaluation(mission_id, useful=useful, feedback=feedback, should_automate=automate)
    typer.echo(f"Evaluation recorded for mission #{mission_id}")
    if automate:
        typer.secho("Marked as automation candidate.", fg="cyan")


@app.command("performance")
def agent_performance() -> None:
    """Show agent performance scores."""
    from core.evaluator import get_agent_performance
    agents = ["lead_hunter", "research", "seo_auditor", "it_guardian", "job_scout", "executive_assistant", "audit_offer", "outreach"]
    typer.echo("Agent Performance Scores:")
    for agent in agents:
        perf = get_agent_performance(agent)
        typer.echo(f"  {agent}: {perf['score']}/10 ({perf['useful']}/{perf['runs']} useful)")


@app.command("costs")
def show_costs() -> None:
    """Show API cost breakdown."""
    from core.cost_tracker import get_daily_cost, get_monthly_cost
    daily = get_daily_cost()
    monthly = get_monthly_cost()
    typer.echo(f"Today: ${daily['total']:.4f}")
    for model, cost in daily.get("by_model", {}).items():
        typer.echo(f"  {model}: ${cost:.4f}")
    typer.echo(f"This Month: ${monthly['total']:.4f}")


@app.command("notify")
def send_notification(message: str = typer.Argument(...)) -> None:
    """Send a message to yourself via Telegram."""
    from core.notifier import send_telegram
    ok = send_telegram(message)
    typer.echo("Sent." if ok else "Failed — check TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_ID in .env")


@app.command("automate-candidates")
def automate_candidates() -> None:
    """Show missions marked as candidates for automation."""
    from core.evaluator import get_automation_candidates
    candidates = get_automation_candidates()
    if not candidates:
        typer.echo("No automation candidates yet. Run eval --automate on missions that should repeat.")
        return
    typer.echo("Automation Candidates:")
    for c in candidates:
        typer.echo(f"  Mission #{c['mission_id']}: {c.get('feedback', 'no feedback')}")


@app.command("contracts")
def list_contracts() -> None:
    """List all agent contracts."""
    import yaml
    contracts_dir = Path(__file__).parent / "agents" / "contracts"
    if not contracts_dir.exists():
        typer.echo("No contracts directory found.")
        return
    for contract_file in sorted(contracts_dir.glob("*.yaml")):
        try:
            with open(contract_file) as f:
                c = yaml.safe_load(f)
            typer.echo(f"  {c.get('name','?')} [{c.get('department','?')}] — autonomy {c.get('autonomy_level','?')}/10: {c.get('purpose','')}")
        except Exception:
            typer.echo(f"  {contract_file.name} (parse error)")


if __name__ == "__main__":
    app()
