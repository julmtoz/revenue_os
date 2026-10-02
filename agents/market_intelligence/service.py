"""Persistent market-intelligence evidence and scoring."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.db import get_session
from core.logger import log_action


def _market_id(conn, niche: str) -> int:
    clean = niche.strip()
    conn.execute(
        """
        INSERT INTO markets (niche, updated_at)
        VALUES (?, CURRENT_TIMESTAMP)
        ON CONFLICT(niche) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        """,
        (clean,),
    )
    row = conn.execute("SELECT id FROM markets WHERE niche = ?", (clean,)).fetchone()
    if not row:
        raise RuntimeError(f"Could not create market record for {clean}")
    return int(row["id"])


def ingest_evidence_batch(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    inserted = 0
    markets_touched: set[str] = set()

    with get_session() as conn:
        for item in items:
            if item.get("success") is False:
                continue
            niche = str(item.get("niche") or "").strip()
            signal_type = str(item.get("signal_type") or "general").strip() or "general"
            query = str(item.get("query") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if not niche or not query:
                continue

            market_id = _market_id(conn, niche)
            markets_touched.add(niche)
            results = item.get("results") or []

            if not results:
                results = [{}]

            for result in results:
                result = result or {}
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO market_evidence (
                        market_id,
                        signal_type,
                        query,
                        source_url,
                        source_title,
                        source_description,
                        summary
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        market_id,
                        signal_type,
                        query,
                        str(result.get("url") or "").strip(),
                        str(result.get("title") or "").strip() or None,
                        str(result.get("description") or "").strip() or None,
                        summary or None,
                    ),
                )
                if cursor.rowcount:
                    inserted += 1

    log_action(
        "market_intelligence",
        "ingest_evidence_batch",
        {"markets": sorted(markets_touched), "inserted": inserted},
    )
    return {
        "inserted": inserted,
        "markets_touched": sorted(markets_touched),
    }


def shortlist(limit: int = 5) -> list[dict[str, Any]]:
    with get_session() as conn:
        rows = conn.execute(
            """
            SELECT
                m.id,
                m.niche,
                m.status,
                COUNT(e.id) AS evidence_count,
                COUNT(DISTINCT NULLIF(e.source_url, '')) AS source_count,
                COUNT(DISTINCT e.signal_type) AS signal_type_count,
                ROUND(
                    COUNT(DISTINCT NULLIF(e.source_url, '')) * 2.0
                    + COUNT(e.id) * 0.5
                    + COUNT(DISTINCT e.signal_type) * 3.0,
                    2
                ) AS score,
                MAX(e.created_at) AS latest_evidence_at
            FROM markets m
            LEFT JOIN market_evidence e ON e.market_id = m.id
            GROUP BY m.id, m.niche, m.status
            ORDER BY
                score DESC,
                source_count DESC,
                evidence_count DESC,
                m.niche ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_evidence(niche: str, limit: int = 100) -> list[dict[str, Any]]:
    with get_session() as conn:
        rows = conn.execute(
            """
            SELECT
                e.id,
                m.niche,
                e.signal_type,
                e.query,
                e.source_url,
                e.source_title,
                e.source_description,
                e.summary,
                e.created_at
            FROM market_evidence e
            JOIN markets m ON m.id = e.market_id
            WHERE m.niche = ?
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT ?
            """,
            (niche.strip(), limit),
        ).fetchall()
    return [dict(row) for row in rows]

