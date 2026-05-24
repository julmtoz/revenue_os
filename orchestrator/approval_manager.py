"""Approval gate management."""
from __future__ import annotations

from typing import Optional

from core.db import get_session, create_approval, resolve_approval, list_approvals
from core.logger import log_action


class ApprovalManager:
    def request(
        self,
        mission_id: Optional[int],
        action: str,
        payload: Optional[str] = None,
    ) -> int:
        with get_session() as conn:
            approval_id = create_approval(conn, mission_id=mission_id, action=action, payload=payload)
        log_action(
            "approval_manager",
            "approval_requested",
            {"approval_id": approval_id, "action": action},
        )
        return approval_id

    def approve(self, approval_id: int, reason: Optional[str] = None) -> None:
        with get_session() as conn:
            resolve_approval(conn, approval_id, approved=True, reason=reason)
        log_action("approval_manager", "approved", {"approval_id": approval_id})

    def reject(self, approval_id: int, reason: Optional[str] = None) -> None:
        with get_session() as conn:
            resolve_approval(conn, approval_id, approved=False, reason=reason)
        log_action("approval_manager", "rejected", {"approval_id": approval_id})

    def list_pending(self) -> list:
        with get_session() as conn:
            return list_approvals(conn, status="pending")
