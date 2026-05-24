"""Department and agent routing."""
from __future__ import annotations

from typing import Optional

from core.models import DEPARTMENTS

DEPARTMENT_AGENTS: dict[str, list[str]] = {
    "revenue": ["lead_hunter", "audit_offer", "outreach"],
    "it_ops": ["it_guardian", "documentation", "network_watch"],
    "seo_marketing": ["seo_auditor", "local_seo", "content"],
    "job_acquisition": ["job_scout", "resume_tailor", "interview_prep"],
    "productivity": ["executive_assistant"],
    "finance": ["finance_command"],
    "fitness": ["performance_coach"],
    "research": ["research"],
}

_KEYWORD_MAP: dict[str, list[str]] = {
    "revenue": ["lead", "roofing", "outreach", "email", "crm", "prospect"],
    "it_ops": ["sop", "network", "device", "incident", "inventory", "ticket", "unifi"],
    "seo_marketing": ["seo", "audit", "keyword", "backlink", "content", "ranking"],
    "job_acquisition": ["job", "resume", "career", "interview", "salary", "apply"],
    "productivity": ["briefing", "plan", "focus", "task", "priority", "organize"],
    "finance": ["credit", "debt", "budget", "expense", "cash", "invest"],
    "fitness": ["workout", "nutrition", "mma", "weight", "recovery", "sleep"],
    "research": ["research", "compare", "analyze", "investigate", "find"],
}


def route(title: str, department: Optional[str] = None) -> tuple[str, str]:
    """Infer department and agent from mission title keywords if not provided.

    Returns a (department, agent) tuple.
    """
    title_lower = title.lower()

    if not department:
        for dept, keywords in _KEYWORD_MAP.items():
            if any(kw in title_lower for kw in keywords):
                department = dept
                break
        if not department:
            department = "research"

    agents = DEPARTMENT_AGENTS.get(department, ["research"])
    agent = agents[0]

    return department, agent
