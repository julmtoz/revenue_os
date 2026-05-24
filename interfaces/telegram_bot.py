"""Telegram bot interface for Ozen — command center from your phone."""
from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parents[1]))

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

from core.config import get_settings
from core.logger import log_action

settings = get_settings()
OWNER_ID = int(settings.telegram_owner_id or 0)


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def owner_only(func):
    """Decorator — silently ignore messages from non-owners."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user or update.effective_user.id != OWNER_ID:
            return
        try:
            await func(update, context)
        except Exception as exc:
            log_action("telegram_bot", "handler_error", {"handler": func.__name__, "error": str(exc)})
            await update.message.reply_text(f"❌ Error: {exc}")
    wrapper.__name__ = func.__name__
    return wrapper


async def _reply(update: Update, text: str) -> None:
    """Send a reply, splitting into chunks if over Telegram's 4096-char limit."""
    chunk_size = 4000
    for i in range(0, len(text), chunk_size):
        await update.message.reply_text(
            text[i:i + chunk_size],
            parse_mode=ParseMode.HTML,
        )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

@owner_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, (
        "👋 <b>Ozen is online.</b>\n\n"
        "Commands:\n"
        "/briefing — daily briefing\n"
        "/status — system status\n"
        "/missions — list missions\n"
        "/approvals — pending approvals\n"
        "/approve &lt;id&gt; — approve action\n"
        "/reject &lt;id&gt; — reject action\n"
        "/run &lt;agent&gt; &lt;args&gt; — run an agent\n"
        "/research &lt;query&gt; — web research\n"
        "/seo &lt;url&gt; — SEO audit\n"
        "/sop &lt;topic&gt; — generate IT SOP\n"
        "/jobs &lt;role&gt; — scan job boards\n"
        "/scrape &lt;city&gt; &lt;niche&gt; — find leads\n"
        "/costs — API cost breakdown\n"
        "/pause &lt;reason&gt; — kill switch\n"
        "/resume — resume all agents\n"
        "/help — show this menu"
    ))


@owner_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


@owner_only
async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Generating briefing...")
    from agents.executive.executive_agent import ExecutiveAgent
    result = ExecutiveAgent().run(task="briefing")
    await _reply(update, f"<pre>{result.output}</pre>")
    log_action("telegram_bot", "briefing", {})


@owner_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from core.kill_switch import is_paused
    from core.cost_tracker import get_daily_cost, get_monthly_cost
    paused = is_paused()
    daily = get_daily_cost()
    monthly = get_monthly_cost()
    text = (
        f"{'🔴 PAUSED' if paused else '🟢 ACTIVE'}\n"
        f"DRY_RUN: <code>{settings.dry_run}</code> | APPROVAL_MODE: <code>{settings.approval_mode}</code>\n"
        f"Cost today: <code>${daily['total']:.4f}</code> | month: <code>${monthly['total']:.4f}</code>"
    )
    await _reply(update, text)


@owner_only
async def cmd_missions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from core.db import get_session, list_missions
    with get_session() as conn:
        missions = list_missions(conn)
    if not missions:
        await _reply(update, "No missions yet.")
        return
    lines = ["<b>Missions:</b>"]
    for m in missions[-15:]:  # last 15
        icon = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌", "paused": "⏸"}.get(m["status"], "•")
        lines.append(f"{icon} <code>[{m['id']}]</code> {m['title']} <i>({m['department']})</i>")
    await _reply(update, "\n".join(lines))


@owner_only
async def cmd_approvals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from core.db import get_session, list_approvals
    with get_session() as conn:
        approvals = list_approvals(conn, status="pending")
    if not approvals:
        await _reply(update, "✅ No pending approvals.")
        return
    lines = ["<b>Pending Approvals:</b>"]
    for a in approvals:
        lines.append(f"⏳ <code>[{a['id']}]</code> {a['action']} — mission #{a['mission_id']}")
        lines.append(f"   Use: /approve {a['id']} or /reject {a['id']}")
    await _reply(update, "\n".join(lines))


@owner_only
async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await _reply(update, "Usage: /approve &lt;id&gt;")
        return
    from orchestrator.approval_manager import ApprovalManager
    ApprovalManager().approve(int(args[0]))
    await _reply(update, f"✅ Approved #{args[0]}")
    log_action("telegram_bot", "approved", {"id": args[0]})


@owner_only
async def cmd_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await _reply(update, "Usage: /reject &lt;id&gt; [reason]")
        return
    reason = " ".join(args[1:]) if len(args) > 1 else None
    from orchestrator.approval_manager import ApprovalManager
    ApprovalManager().reject(int(args[0]), reason=reason)
    await _reply(update, f"❌ Rejected #{args[0]}")


@owner_only
async def cmd_research(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args or [])
    if not query:
        await _reply(update, "Usage: /research &lt;query&gt;")
        return
    await update.message.reply_text(f"🔍 Researching: {query}...")
    from agents.research.research_agent import ResearchAgent
    result = ResearchAgent().run(query=query)
    await _reply(update, f"<pre>{result.output}</pre>")


@owner_only
async def cmd_seo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = " ".join(context.args or [])
    if not url:
        await _reply(update, "Usage: /seo &lt;url&gt;")
        return
    await update.message.reply_text(f"🔎 Auditing {url}...")
    from agents.seo_auditor.seo_auditor_agent import SEOAuditorAgent
    result = SEOAuditorAgent().run(url=url)
    await _reply(update, f"<pre>{result.output}</pre>")


@owner_only
async def cmd_sop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    topic = " ".join(context.args or [])
    if not topic:
        await _reply(update, "Usage: /sop &lt;topic&gt; (e.g. /sop new device setup)")
        return
    from agents.it_guardian.it_guardian_agent import ITGuardianAgent
    result = ITGuardianAgent().run(task="sop", topic=topic)
    await _reply(update, f"<pre>{result.output}</pre>")


@owner_only
async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = " ".join(context.args or []) or "IT Systems Administrator"
    await update.message.reply_text(f"💼 Scanning jobs for: {role}...")
    from agents.job_scout.job_scout_agent import JobScoutAgent
    result = JobScoutAgent().run(role=role, location="New Jersey")
    await _reply(update, f"<pre>{result.output}</pre>")


@owner_only
async def cmd_scrape(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args or []
    city = args[0] if len(args) > 0 else settings.default_city
    niche = args[1] if len(args) > 1 else settings.default_niche
    await update.message.reply_text(f"🕷 Scraping {niche} leads in {city}...")
    from agents.lead_hunter.lead_hunter import scrape_and_store
    result = scrape_and_store(city, niche, limit=settings.max_leads_per_run)
    fallback_note = " (fallback used)" if result.fallback_used else ""
    await _reply(update, f"✅ Stored <b>{len(result.lead_ids)}</b> leads from {city} / {niche}{fallback_note}")
    log_action("telegram_bot", "scrape", {"city": city, "niche": niche, "count": len(result.lead_ids)})


@owner_only
async def cmd_costs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from core.cost_tracker import get_daily_cost, get_monthly_cost
    daily = get_daily_cost()
    monthly = get_monthly_cost()
    lines = [f"<b>API Costs</b>", f"Today: <code>${daily['total']:.4f}</code>"]
    for model, cost in daily.get("by_model", {}).items():
        lines.append(f"  {model}: <code>${cost:.4f}</code>")
    lines.append(f"Month: <code>${monthly['total']:.4f}</code>")
    await _reply(update, "\n".join(lines))


@owner_only
async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reason = " ".join(context.args or []) or "manual via Telegram"
    from core.kill_switch import pause_all
    pause_all(reason)
    await _reply(update, f"🔴 <b>SYSTEM PAUSED</b>\nReason: {reason}\nSend /resume to restart.")
    log_action("telegram_bot", "pause", {"reason": reason})


@owner_only
async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from core.kill_switch import resume_all, is_paused
    if not is_paused():
        await _reply(update, "System is already active.")
        return
    resume_all()
    await _reply(update, "🟢 <b>SYSTEM RESUMED</b> — agents are active.")
    log_action("telegram_bot", "resume", {})


@owner_only
async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generic /run <agent> [args] dispatcher."""
    args = context.args or []
    if not args:
        await _reply(update, (
            "Usage: /run &lt;agent&gt; [args]\n\n"
            "Agents:\n"
            "  research &lt;query&gt;\n"
            "  seo &lt;url&gt;\n"
            "  sop &lt;topic&gt;\n"
            "  jobs &lt;role&gt;\n"
            "  scrape &lt;city&gt; &lt;niche&gt;\n"
            "  briefing\n"
            "  summary"
        ))
        return

    agent_name = args[0].lower()
    rest = args[1:]

    dispatch = {
        "research": lambda: cmd_research_direct(update, " ".join(rest)),
        "seo": lambda: cmd_seo_direct(update, " ".join(rest)),
        "sop": lambda: cmd_sop_direct(update, " ".join(rest)),
        "jobs": lambda: cmd_jobs_direct(update, " ".join(rest)),
        "scrape": lambda: cmd_scrape_direct(update, rest),
        "briefing": lambda: cmd_briefing(update, context),
        "summary": lambda: cmd_summary(update, context),
    }

    handler = dispatch.get(agent_name)
    if not handler:
        await _reply(update, f"Unknown agent: {agent_name}")
        return
    await handler()


async def cmd_research_direct(update: Update, query: str) -> None:
    if not query:
        await _reply(update, "Provide a query.")
        return
    await update.message.reply_text(f"🔍 Researching: {query}...")
    from agents.research.research_agent import ResearchAgent
    result = ResearchAgent().run(query=query)
    await _reply(update, f"<pre>{result.output}</pre>")


async def cmd_seo_direct(update: Update, url: str) -> None:
    if not url:
        await _reply(update, "Provide a URL.")
        return
    await update.message.reply_text(f"🔎 Auditing {url}...")
    from agents.seo_auditor.seo_auditor_agent import SEOAuditorAgent
    result = SEOAuditorAgent().run(url=url)
    await _reply(update, f"<pre>{result.output}</pre>")


async def cmd_sop_direct(update: Update, topic: str) -> None:
    if not topic:
        await _reply(update, "Provide a topic.")
        return
    from agents.it_guardian.it_guardian_agent import ITGuardianAgent
    result = ITGuardianAgent().run(task="sop", topic=topic)
    await _reply(update, f"<pre>{result.output}</pre>")


async def cmd_jobs_direct(update: Update, role: str) -> None:
    role = role or "IT Systems Administrator"
    await update.message.reply_text(f"💼 Scanning: {role}...")
    from agents.job_scout.job_scout_agent import JobScoutAgent
    result = JobScoutAgent().run(role=role, location="New Jersey")
    await _reply(update, f"<pre>{result.output}</pre>")


async def cmd_scrape_direct(update: Update, args: list) -> None:
    city = args[0] if args else settings.default_city
    niche = args[1] if len(args) > 1 else settings.default_niche
    await update.message.reply_text(f"🕷 Scraping {niche} in {city}...")
    from agents.lead_hunter.lead_hunter import scrape_and_store
    result = scrape_and_store(city, niche, limit=settings.max_leads_per_run)
    await _reply(update, f"✅ Stored <b>{len(result.lead_ids)}</b> leads from {city} / {niche}")


@owner_only
async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from orchestrator.supreme_orchestrator import SupremeOrchestrator
    summary = SupremeOrchestrator().daily_summary()
    await _reply(update, f"<pre>{summary}</pre>")


@owner_only
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, "Unknown command. Send /help for the menu.")


# ---------------------------------------------------------------------------
# Bot entry point
# ---------------------------------------------------------------------------

def run_bot() -> None:
    token = settings.telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set in .env")
    if not OWNER_ID:
        raise RuntimeError("TELEGRAM_OWNER_ID not set in .env")

    app = Application.builder().token(token).build()

    handlers = [
        ("start", cmd_start),
        ("help", cmd_help),
        ("briefing", cmd_briefing),
        ("status", cmd_status),
        ("missions", cmd_missions),
        ("approvals", cmd_approvals),
        ("approve", cmd_approve),
        ("reject", cmd_reject),
        ("research", cmd_research),
        ("seo", cmd_seo),
        ("sop", cmd_sop),
        ("jobs", cmd_jobs),
        ("scrape", cmd_scrape),
        ("costs", cmd_costs),
        ("pause", cmd_pause),
        ("resume", cmd_resume),
        ("run", cmd_run),
        ("summary", cmd_summary),
    ]

    for name, handler in handlers:
        app.add_handler(CommandHandler(name, handler))

    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    print(f"Ozen Telegram bot running (owner: {OWNER_ID})")
    log_action("telegram_bot", "started", {"owner_id": OWNER_ID})
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
