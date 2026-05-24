"""Logging utilities writing to console, JSONL, and database."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from rich.logging import RichHandler

from .config import get_settings
from .db import get_connection

_logger: logging.Logger | None = None


def get_logger() -> logging.Logger:
    global _logger
    if _logger:
        return _logger
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=True)],
    )
    _logger = logging.getLogger("revenue_os")
    _logger.setLevel(logging.INFO)
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    return _logger


def _jsonl_path() -> Path:
    settings = get_settings()
    filename = f"actions-{datetime.now(timezone.utc).date()}.jsonl"
    return settings.log_dir / filename


def log_action(agent: str, action: str, metadata: Dict[str, Any]) -> None:
    logger = get_logger()
    record = {
        "agent": agent,
        "action": action,
        "metadata": metadata,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("[%s] %s", agent, action)

    jsonl_path = _jsonl_path()
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    conn = None
    try:
        conn = get_connection()
        with conn:
            conn.execute(
                "INSERT INTO logs(agent, action, metadata) VALUES (?, ?, ?)",
                (agent, action, json.dumps(metadata, ensure_ascii=False)),
            )
    except Exception as exc:
        logger.warning('Failed to persist log entry: %s', exc)
    finally:
        if conn is not None:
            conn.close()
