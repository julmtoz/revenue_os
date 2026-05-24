"""Track OpenAI API usage and costs per agent/mission."""
from __future__ import annotations
from core.db import get_session, memory_get, memory_set
from core.logger import log_action
import json
from datetime import datetime, timezone

OPENAI_COSTS = {
    "gpt-4.1-mini": {"input": 0.40 / 1_000_000, "output": 1.60 / 1_000_000},
    "gpt-4o-mini": {"input": 0.15 / 1_000_000, "output": 0.60 / 1_000_000},
    "gpt-4o": {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000},
    "gpt-4.1": {"input": 2.00 / 1_000_000, "output": 8.00 / 1_000_000},
}


def track_usage(agent: str, model: str, input_tokens: int, output_tokens: int, mission_id: int | None = None) -> float:
    """Record token usage and return cost in USD."""
    rates = OPENAI_COSTS.get(model, {"input": 2.50 / 1_000_000, "output": 10.00 / 1_000_000})
    cost = (input_tokens * rates["input"]) + (output_tokens * rates["output"])

    log_action(agent, "api_cost", {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
        "mission_id": mission_id,
    })

    # Accumulate daily cost
    today = datetime.now(timezone.utc).date().isoformat()
    with get_session() as conn:
        existing_raw = memory_get(conn, "api_costs", today)
        existing = json.loads(existing_raw) if existing_raw else {"total": 0.0, "by_model": {}}
        existing["total"] = round(existing["total"] + cost, 6)
        existing["by_model"][model] = round(existing["by_model"].get(model, 0.0) + cost, 6)
        memory_set(conn, "api_costs", today, json.dumps(existing))

    return cost


def get_daily_cost(date: str | None = None) -> dict:
    today = date or datetime.now(timezone.utc).date().isoformat()
    with get_session() as conn:
        raw = memory_get(conn, "api_costs", today)
    return json.loads(raw) if raw else {"total": 0.0, "by_model": {}}


def get_monthly_cost() -> dict:
    from core.db import get_connection
    conn = get_connection()
    try:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        rows = conn.execute(
            "SELECT key, value FROM memory WHERE namespace='api_costs' AND key LIKE ?",
            (f"{month}%",)
        ).fetchall()
    finally:
        conn.close()
    total = 0.0
    by_model: dict = {}
    for row in rows:
        try:
            data = json.loads(row["value"])
            total += data.get("total", 0.0)
            for model, cost in data.get("by_model", {}).items():
                by_model[model] = round(by_model.get(model, 0.0) + cost, 6)
        except Exception:
            pass
    return {"total": round(total, 6), "by_model": by_model}
