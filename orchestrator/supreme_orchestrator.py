"""Supreme Orchestrator — coordinates all departments and agents."""
from __future__ import annotations

import json
from typing import Any, Optional

from orchestrator.mission_manager import MissionManager
from orchestrator.approval_manager import ApprovalManager
from orchestrator.router import route
from core.logger import log_action
from core.config import get_settings


class SupremeOrchestrator:
    """Central coordinator for all Ozen agent operations."""

    def __init__(self) -> None:
        self.missions = MissionManager()
        self.approvals = ApprovalManager()
        self.settings = get_settings()

    def dispatch(
        self,
        title: str,
        department: Optional[str] = None,
        input_data: Optional[dict] = None,
        priority: int = 5,
        approval_required: Optional[bool] = None,
    ) -> int:
        dept, agent = route(title, department)
        needs_approval = (
            approval_required if approval_required is not None else self.settings.approval_mode
        )

        mission_id = self.missions.create(
            title=title,
            department=dept,
            agent=agent,
            input_data=input_data,
            approval_required=needs_approval,
            priority=priority,
        )
        log_action(
            "orchestrator",
            "dispatched",
            {
                "mission_id": mission_id,
                "department": dept,
                "agent": agent,
                "dry_run": self.settings.dry_run,
            },
        )
        return mission_id

    def daily_summary(self) -> str:
        all_missions = self.missions.list()
        completed = [m for m in all_missions if m["status"] == "completed"]
        failed = [m for m in all_missions if m["status"] == "failed"]
        pending = [m for m in all_missions if m["status"] == "pending"]
        running = [m for m in all_missions if m["status"] == "running"]
        approvals = self.approvals.list_pending()

        lines = [
            "=== OZEN DAILY SUMMARY ===",
            (
                f"Missions: {len(all_missions)} total | {len(completed)} done | "
                f"{len(running)} running | {len(pending)} pending | {len(failed)} failed"
            ),
            f"Approvals waiting: {len(approvals)}",
        ]
        if approvals:
            lines.append("\nPending Approvals:")
            for a in approvals[:5]:
                lines.append(f"  [{a['id']}] {a['action']} — mission {a['mission_id']}")
        if failed:
            lines.append("\nFailed Missions:")
            for m in failed[-3:]:
                lines.append(f"  [{m['id']}] {m['title']}: {m['error'] or 'unknown error'}")
        return "\n".join(lines)
