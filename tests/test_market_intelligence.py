from dataclasses import replace

from agents.market_intelligence.service import (
    ingest_evidence_batch,
    list_evidence,
    shortlist,
)
from core import config


def _use_temp_db(tmp_path, monkeypatch):
    base = config.get_settings()
    export_dir = tmp_path / "exports"
    log_dir = tmp_path / "logs"
    export_dir.mkdir()
    log_dir.mkdir()
    monkeypatch.setattr(
        config,
        "_cached_settings",
        replace(
            base,
            db_path=tmp_path / "dge-test.db",
            export_dir=export_dir,
            log_dir=log_dir,
        ),
    )


def test_market_evidence_persists_deduplicates_and_scores(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    items = [
        {
            "niche": "roofing",
            "signal_type": "demand_spend",
            "query": "roofing ads demand",
            "summary": "Active paid demand.",
            "results": [{"url": "https://a.example", "title": "A", "description": "ads"}],
        },
        {
            "niche": "roofing",
            "signal_type": "hiring",
            "query": "roofing marketing hiring",
            "summary": "Hiring signal.",
            "results": [{"url": "https://b.example", "title": "B", "description": "jobs"}],
        },
        {
            "niche": "roofing",
            "signal_type": "competition",
            "query": "roofing agencies",
            "summary": "Competitive spend.",
            "results": [{"url": "https://c.example", "title": "C", "description": "agency"}],
        },
    ]

    first = ingest_evidence_batch(items)
    second = ingest_evidence_batch(items)

    assert first["inserted"] == 3
    assert second["inserted"] == 0

    markets = shortlist(limit=5)
    assert markets[0]["niche"] == "roofing"
    assert markets[0]["evidence_count"] == 3
    assert markets[0]["source_count"] == 3
    assert markets[0]["signal_type_count"] == 3
    assert markets[0]["score"] == 16.5

    evidence = list_evidence("roofing")
    assert len(evidence) == 3
