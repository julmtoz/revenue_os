"""Backup system for Ozen database, memory, and config."""
from __future__ import annotations
import shutil
from datetime import datetime, timezone
from pathlib import Path
from core.config import get_settings
from core.logger import log_action

BACKUP_DIR = Path.home() / ".openclaw" / "workspace" / "revenue_os" / "data" / "backups"


def backup_db() -> Path:
    """Copy the SQLite database to a timestamped backup file."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"revenue_os-{ts}.db"
    shutil.copy2(settings.db_path, dest)
    log_action("backup", "db_backup", {"path": str(dest)})
    return dest


def backup_config() -> Path:
    """Copy .env to a timestamped backup."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    env_path = Path(__file__).parents[1] / ".env"
    dest = BACKUP_DIR / f"env-{ts}.bak"
    if env_path.exists():
        shutil.copy2(env_path, dest)
    log_action("backup", "config_backup", {"path": str(dest)})
    return dest


def list_backups() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("*.db"), reverse=True)


def prune_backups(keep: int = 10) -> int:
    """Delete old backups keeping only the most recent `keep` files."""
    backups = list_backups()
    to_delete = backups[keep:]
    for f in to_delete:
        f.unlink()
    log_action("backup", "pruned", {"deleted": len(to_delete), "kept": keep})
    return len(to_delete)
