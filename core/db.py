"""Database helpers for revenue_os."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Mapping, Optional

from .config import get_settings

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY,
        name TEXT,
        website TEXT,
        phone TEXT,
        email TEXT,
        city TEXT,
        category TEXT,
        source TEXT,
        score REAL,
        status TEXT,
        notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS emails (
        id INTEGER PRIMARY KEY,
        lead_id INTEGER,
        subject TEXT,
        body TEXT,
        step INTEGER,
        status TEXT,
        sendability TEXT DEFAULT 'needs_edit',
        notes TEXT,
        sent_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lead_id) REFERENCES leads(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audits (
        id INTEGER PRIMARY KEY,
        lead_id INTEGER,
        summary TEXT,
        offer_angle TEXT,
        file_path TEXT,
        approved_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lead_id) REFERENCES leads(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY,
        agent TEXT,
        action TEXT,
        metadata TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS missions (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        department TEXT NOT NULL,
        agent TEXT,
        status TEXT DEFAULT 'pending',
        priority INTEGER DEFAULT 5,
        input TEXT,
        output TEXT,
        next_action TEXT,
        approval_required INTEGER DEFAULT 0,
        approved INTEGER DEFAULT 0,
        error TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS approvals (
        id INTEGER PRIMARY KEY,
        mission_id INTEGER,
        action TEXT NOT NULL,
        payload TEXT,
        status TEXT DEFAULT 'pending',
        reason TEXT,
        decided_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (mission_id) REFERENCES missions(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS memory (
        id INTEGER PRIMARY KEY,
        namespace TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(namespace, key)
    );
    """,
]


def _ensure_email_columns(conn: sqlite3.Connection) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(emails)")}
    if "sendability" not in columns:
        conn.execute("ALTER TABLE emails ADD COLUMN sendability TEXT DEFAULT 'needs_edit'")
    if "notes" not in columns:
        conn.execute("ALTER TABLE emails ADD COLUMN notes TEXT")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        conn.executescript(statement)
    _ensure_email_columns(conn)


def get_connection() -> sqlite3.Connection:
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    _ensure_schema(conn)
    return conn


def ensure_db_ready() -> None:
    conn = get_connection()
    conn.close()


def init_db() -> None:
    conn = get_connection()
    with conn:
        _ensure_schema(conn)


def upsert_lead(conn: sqlite3.Connection, lead: Mapping[str, object]) -> int:
    """Insert or update a lead by (name, city). Returns lead id."""
    existing = conn.execute(
        "SELECT id FROM leads WHERE name = ? AND city = ?",
        (lead.get("name"), lead.get("city")),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE leads SET website=:website, phone=:phone, email=:email, category=:category, source=:source, score=:score, status=:status, notes=:notes, updated_at=CURRENT_TIMESTAMP WHERE id=:id",
            {**lead, "id": existing["id"]},
        )
        return int(existing["id"])
    cursor = conn.execute(
        """
        INSERT INTO leads (name, website, phone, email, city, category, source, score, status, notes)
        VALUES (:name, :website, :phone, :email, :city, :category, :source, :score, :status, :notes)
        """,
        lead,
    )
    return int(cursor.lastrowid)


@contextmanager
def get_session() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Mission helpers
# ---------------------------------------------------------------------------

def create_mission(
    conn: sqlite3.Connection,
    title: str,
    department: str,
    agent: Optional[str] = None,
    input_data: Optional[str] = None,
    approval_required: bool = False,
    priority: int = 5,
) -> int:
    """Insert a new mission row and return its id."""
    cursor = conn.execute(
        """
        INSERT INTO missions (title, department, agent, input, approval_required, priority)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (title, department, agent, input_data, 1 if approval_required else 0, priority),
    )
    return int(cursor.lastrowid)


def update_mission(conn: sqlite3.Connection, mission_id: int, **kwargs: Any) -> None:
    """Update any fields on a mission row plus updated_at timestamp."""
    if not kwargs:
        return
    kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [mission_id]
    conn.execute(f"UPDATE missions SET {set_clause} WHERE id = ?", values)


def get_mission(conn: sqlite3.Connection, mission_id: int) -> Optional[sqlite3.Row]:
    """Return a single mission row or None."""
    return conn.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()


def list_missions(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    department: Optional[str] = None,
) -> list:
    """Return missions filtered by optional status and/or department."""
    query = "SELECT * FROM missions WHERE 1=1"
    params: list[Any] = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if department:
        query += " AND department = ?"
        params.append(department)
    query += " ORDER BY priority DESC, created_at DESC"
    return conn.execute(query, params).fetchall()


# ---------------------------------------------------------------------------
# Approval helpers
# ---------------------------------------------------------------------------

def create_approval(
    conn: sqlite3.Connection,
    mission_id: Optional[int],
    action: str,
    payload: Optional[str] = None,
) -> int:
    """Insert a new approval request and return its id."""
    cursor = conn.execute(
        "INSERT INTO approvals (mission_id, action, payload) VALUES (?, ?, ?)",
        (mission_id, action, payload),
    )
    return int(cursor.lastrowid)


def resolve_approval(
    conn: sqlite3.Connection,
    approval_id: int,
    approved: bool,
    reason: Optional[str] = None,
) -> None:
    """Mark an approval as approved or rejected."""
    status = "approved" if approved else "rejected"
    decided_at = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE approvals SET status = ?, reason = ?, decided_at = ? WHERE id = ?",
        (status, reason, decided_at, approval_id),
    )


def list_approvals(conn: sqlite3.Connection, status: str = "pending") -> list:
    """Return approvals filtered by status."""
    return conn.execute(
        "SELECT * FROM approvals WHERE status = ? ORDER BY created_at ASC",
        (status,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Memory helpers
# ---------------------------------------------------------------------------

def memory_set(conn: sqlite3.Connection, namespace: str, key: str, value: str) -> None:
    """Upsert a key-value pair in the memory table."""
    conn.execute(
        """
        INSERT INTO memory (namespace, key, value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(namespace, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (namespace, key, value, datetime.now(timezone.utc).isoformat()),
    )


def memory_get(conn: sqlite3.Connection, namespace: str, key: str) -> Optional[str]:
    """Retrieve a value from the memory table, or None if not found."""
    row = conn.execute(
        "SELECT value FROM memory WHERE namespace = ? AND key = ?",
        (namespace, key),
    ).fetchone()
    return row["value"] if row else None
