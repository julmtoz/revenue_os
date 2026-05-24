"""Global kill switch — pause or resume all agent execution."""
from __future__ import annotations
from pathlib import Path

KILL_FILE = Path.home() / ".openclaw" / "workspace" / "revenue_os" / "data" / ".kill_switch"


def is_paused() -> bool:
    return KILL_FILE.exists()


def pause_all(reason: str = "manual") -> None:
    KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
    KILL_FILE.write_text(reason)


def resume_all() -> None:
    if KILL_FILE.exists():
        KILL_FILE.unlink()


def check_kill_switch() -> None:
    """Call this at the start of any agent run. Raises RuntimeError if paused."""
    if is_paused():
        reason = KILL_FILE.read_text().strip()
        raise RuntimeError(f"SYSTEM PAUSED: {reason}. Run `python cli.py resume` to continue.")
