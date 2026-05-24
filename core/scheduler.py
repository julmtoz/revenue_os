"""Optional APScheduler jobs."""
from __future__ import annotations

import traceback

from apscheduler.schedulers.blocking import BlockingScheduler

from agents.lead_hunter.lead_hunter import scrape_and_store
from agents.outreach.generator import generate_email_drafts
from core.config import get_settings
from core.logger import log_action


def _safe(fn):
    """Wrap a job callable so exceptions are logged instead of silently dropped."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            log_action("scheduler", "job_error", {
                "job": fn.__name__,
                "error": str(exc),
                "trace": traceback.format_exc(limit=5),
            })
    wrapper.__name__ = fn.__name__
    return wrapper


def _job_scrape(city: str, niche: str) -> None:
    result = scrape_and_store(city, niche, limit=25)
    log_action("scheduler", "scrape_complete", {
        "city": city,
        "niche": niche,
        "count": len(result.lead_ids),
        "fallback": result.fallback_used,
    })


def _job_generate_emails(cap: int) -> None:
    # Target all workable statuses (qualified, reviewed, interested, audit_ready)
    n = generate_email_drafts(limit=cap, status="qualified")
    log_action("scheduler", "emails_complete", {"count": n})


def start_scheduler() -> None:
    settings = get_settings()
    scheduler = BlockingScheduler()

    scheduler.add_job(
        _safe(_job_scrape),
        "cron",
        args=[settings.default_city, settings.default_niche],
        hour="8,14",
        id="lead_scrape",
        replace_existing=True,
    )

    scheduler.add_job(
        _safe(_job_generate_emails),
        "cron",
        args=[settings.daily_outreach_cap],
        hour="9",
        id="generate_emails",
        replace_existing=True,
    )

    scheduler.start()
