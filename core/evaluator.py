"""Post-mission evaluation — captures feedback and improvement signals."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from core.db import get_session, memory_set, memory_get, update_mission
from core.logger import log_action


def record_evaluation(mission_id: int, useful: bool, feedback: str = "", should_automate: bool = False) -> None:
    """Record Julio's evaluation of a completed mission."""
    with get_session() as conn:
        # Store evaluation in memory
        key = f"eval_mission_{mission_id}"
        data = {
            "mission_id": mission_id,
            "useful": useful,
            "feedback": feedback,
            "should_automate": should_automate,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        memory_set(conn, "evaluations", key, json.dumps(data))

        # Update agent performance score in memory
        mission = conn.execute("SELECT agent, department FROM missions WHERE id = ?", (mission_id,)).fetchone()
        if mission and mission["agent"]:
            agent = mission["agent"]
            score_key = f"agent_score_{agent}"
            existing_raw = memory_get(conn, "performance", score_key)
            existing = json.loads(existing_raw) if existing_raw else {"runs": 0, "useful": 0, "score": 5.0}
            existing["runs"] += 1
            if useful:
                existing["useful"] += 1
            existing["score"] = round((existing["useful"] / existing["runs"]) * 10, 1)
            memory_set(conn, "performance", score_key, json.dumps(existing))

    log_action("evaluator", "recorded", {"mission_id": mission_id, "useful": useful, "automate": should_automate})


def get_agent_performance(agent: str) -> dict:
    with get_session() as conn:
        raw = memory_get(conn, "performance", f"agent_score_{agent}")
    return json.loads(raw) if raw else {"runs": 0, "useful": 0, "score": 5.0}


def get_automation_candidates() -> list[dict]:
    """Return missions marked as should_automate=True for recurring workflow suggestions."""
    from core.db import get_connection
    conn = get_connection()
    try:
        rows = conn.execute("SELECT value FROM memory WHERE namespace='evaluations'").fetchall()
    finally:
        conn.close()
    candidates = []
    for row in rows:
        try:
            data = json.loads(row["value"])
            if data.get("should_automate"):
                candidates.append(data)
        except Exception:
            pass
    return candidates
