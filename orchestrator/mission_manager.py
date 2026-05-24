"""Mission lifecycle management."""
from __future__ import annotations

import json
from typing import Any, Optional

from core.db import get_session, create_mission, update_mission, get_mission, list_missions
from core.logger import log_action


class MissionManager:
    def create(
        self,
        title: str,
        department: str,
        agent: Optional[str] = None,
        input_data: Optional[dict] = None,
        approval_required: bool = False,
        priority: int = 5,
    ) -> int:
        with get_session() as conn:
            mission_id = create_mission(
                conn,
                title=title,
                department=department,
                agent=agent,
                input_data=json.dumps(input_data) if input_data else None,
                approval_required=approval_required,
                priority=priority,
            )
        log_action(
            "orchestrator",
            "mission_created",
            {"mission_id": mission_id, "title": title, "department": department},
        )
        return mission_id

    def start(self, mission_id: int) -> None:
        with get_session() as conn:
            update_mission(conn, mission_id, status="running")
        log_action("orchestrator", "mission_started", {"mission_id": mission_id})

    def complete(self, mission_id: int, output: str, next_action: Optional[str] = None) -> None:
        with get_session() as conn:
            update_mission(conn, mission_id, status="completed", output=output, next_action=next_action)
        log_action("orchestrator", "mission_completed", {"mission_id": mission_id})

    def fail(self, mission_id: int, error: str) -> None:
        with get_session() as conn:
            update_mission(conn, mission_id, status="failed", error=error)
        log_action("orchestrator", "mission_failed", {"mission_id": mission_id, "error": error})

    def pause(self, mission_id: int) -> None:
        with get_session() as conn:
            update_mission(conn, mission_id, status="paused")

    def get(self, mission_id: int) -> Any:
        with get_session() as conn:
            return get_mission(conn, mission_id)

    def list(self, status: Optional[str] = None, department: Optional[str] = None) -> list:
        with get_session() as conn:
            return list_missions(conn, status=status, department=department)
