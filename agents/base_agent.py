"""Base agent class for all Ozen agents."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Optional

from core.config import get_settings
from core.db import get_session, update_mission
from core.logger import log_action


class AgentResult:
    def __init__(
        self,
        success: bool,
        output: str,
        data: Any = None,
        next_action: Optional[str] = None,
    ) -> None:
        self.success = success
        self.output = output
        self.data = data
        self.next_action = next_action


class BaseAgent(ABC):
    name: str = "base"
    department: str = "general"
    description: str = ""
    autonomy_level: int = 5  # 1=fully manual, 5=semi-auto, 10=fully auto

    def __init__(self) -> None:
        self.settings = get_settings()

    def run(self, mission_id: Optional[int] = None, max_retries: int = 1, **kwargs: Any) -> AgentResult:
        from core.kill_switch import check_kill_switch
        check_kill_switch()
        start = time.time()
        log_action(self.name, "start", {"mission_id": mission_id, "kwargs": str(kwargs)[:200]})
        last_error: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    log_action(self.name, "retry", {"attempt": attempt, "mission_id": mission_id})
                    time.sleep(2)
                result = self.execute(mission_id=mission_id, **kwargs)
                elapsed = round(time.time() - start, 2)
                log_action(
                    self.name,
                    "complete",
                    {"mission_id": mission_id, "elapsed": elapsed, "success": result.success, "attempts": attempt + 1},
                )
                if mission_id:
                    with get_session() as conn:
                        update_mission(
                            conn,
                            mission_id,
                            status="completed" if result.success else "failed",
                            output=result.output,
                            next_action=result.next_action,
                        )
                return result
            except RuntimeError:
                # Kill switch or config error — do not retry
                raise
            except Exception as exc:
                last_error = exc
                log_action(self.name, "attempt_error", {"attempt": attempt, "error": str(exc)})
        log_action(self.name, "error", {"mission_id": mission_id, "error": str(last_error), "attempts": max_retries + 1})
        if mission_id:
            with get_session() as conn:
                update_mission(conn, mission_id, status="failed", error=str(last_error))
        return AgentResult(success=False, output=f"Failed after {max_retries + 1} attempts: {last_error}")

    @abstractmethod
    def execute(self, mission_id: Optional[int] = None, **kwargs: Any) -> AgentResult:
        """Implement agent logic here."""
        ...

    def requires_approval(self, action: str) -> bool:
        """Check if action requires approval based on safety config."""
        s = self.settings
        approval_map: dict[str, bool] = {
            "send_email": s.approval_mode or not s.allow_external_send,
            "send_sms": s.approval_mode or not s.allow_external_send,
            "delete_file": not s.allow_file_delete,
            "edit_website": not s.allow_website_edit,
            "apply_job": not s.allow_job_apply,
        }
        return approval_map.get(action, s.approval_mode)

    def dry_run_guard(self, action: str, payload: str) -> bool:
        """Returns True if action should be skipped due to DRY_RUN. Logs the skipped action."""
        if self.settings.dry_run:
            log_action(
                self.name,
                f"dry_run_skip:{action}",
                {"payload_preview": payload[:200]},
            )
            return True
        return False
