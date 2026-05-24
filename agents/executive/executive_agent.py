"""Executive Assistant Agent — daily briefing, priority management."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from agents.base_agent import BaseAgent, AgentResult
from core.db import get_session, list_missions, list_approvals
from core.logger import log_action


class ExecutiveAgent(BaseAgent):
    name = "executive_assistant"
    department = "productivity"
    description = "Daily briefing, priorities, open loops, mission status."

    def execute(
        self,
        mission_id: Optional[int] = None,
        task: str = "briefing",
        **kwargs: Any,
    ) -> AgentResult:
        if task == "briefing":
            return self._daily_briefing()
        elif task == "priorities":
            return self._prioritize()
        return AgentResult(success=False, output=f"Unknown task: {task}")

    def _daily_briefing(self) -> AgentResult:
        now = datetime.now()

        with get_session() as conn:
            all_missions = list_missions(conn)
            pending_approvals = list_approvals(conn, status="pending")
            leads_row = conn.execute(
                "SELECT COUNT(*) as c, status FROM leads GROUP BY status"
            ).fetchall()
            emails_row = conn.execute(
                "SELECT COUNT(*) as c FROM emails WHERE status = 'draft'"
            ).fetchone()

        mission_status: dict[str, int] = {}
        for m in all_missions:
            s = m["status"]
            mission_status[s] = mission_status.get(s, 0) + 1

        leads_by_status: dict[str, int] = {row["status"]: row["c"] for row in leads_row}

        lines = [
            f"OZEN DAILY BRIEFING — {now.strftime('%A, %B %d %Y')}",
            "",
            "MISSIONS",
            (
                f"  Pending: {mission_status.get('pending', 0)} | "
                f"Running: {mission_status.get('running', 0)} | "
                f"Done: {mission_status.get('completed', 0)} | "
                f"Failed: {mission_status.get('failed', 0)}"
            ),
            "",
            "APPROVALS NEEDED",
            f"  {len(pending_approvals)} action(s) waiting for your approval",
        ]

        if pending_approvals:
            for a in pending_approvals[:3]:
                lines.append(f"  -> [{a['id']}] {a['action']}")

        email_draft_count = emails_row["c"] if emails_row else 0
        lines += [
            "",
            "REVENUE PIPELINE",
            (
                f"  Qualified: {leads_by_status.get('qualified', 0)} | "
                f"Reviewed: {leads_by_status.get('reviewed', 0)} | "
                f"Emailed: {leads_by_status.get('emailed', 0)}"
            ),
            f"  Email drafts ready: {email_draft_count}",
            "",
            "RECOMMENDED FOCUS TODAY",
        ]

        # Smart recommendations
        if leads_by_status.get("qualified", 0) > 0:
            lines.append(
                f"  1. Generate emails for {leads_by_status['qualified']} qualified leads"
            )
        if pending_approvals:
            lines.append(f"  2. Review {len(pending_approvals)} pending approvals")
        if mission_status.get("failed", 0) > 0:
            lines.append(f"  3. Investigate {mission_status['failed']} failed mission(s)")
        lines.append("  -> Run: python cli.py briefing for full details")

        return AgentResult(
            success=True,
            output="\n".join(lines),
            next_action="Review and act on top priorities",
        )

    def _prioritize(self) -> AgentResult:
        with get_session() as conn:
            missions = list_missions(conn, status="pending")

        if not missions:
            return AgentResult(success=True, output="No pending missions to prioritize.")

        lines = ["PENDING MISSIONS BY PRIORITY", ""]
        for m in missions[:20]:
            lines.append(
                f"  [{m['priority']:2d}] [{m['id']}] {m['department'].upper()} — {m['title']}"
            )

        return AgentResult(
            success=True,
            output="\n".join(lines),
            next_action="Start highest-priority missions first",
        )
