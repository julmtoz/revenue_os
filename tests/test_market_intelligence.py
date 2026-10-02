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


def test_failed_research_does_not_create_scored_evidence(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    assert ingest_evidence_batch([{
        "niche": "roofing", "signal_type": "hiring", "query": "roofing hiring",
        "success": False, "results": [], "summary": "Search unavailable",
    }])["inserted"] == 0
    assert shortlist() == []


def test_mock_pipeline_scopes_drafts_and_never_marks_sent(tmp_path, monkeypatch):
    from agents.lead_hunter.lead_hunter import scrape_and_store
    from agents.outreach.generator import generate_email_drafts
    from core.db import get_session

    _use_temp_db(tmp_path, monkeypatch)
    own = scrape_and_store("Newark", "roofing", limit=1, mock=True)
    other = scrape_and_store("Trenton", "plumbing", limit=1, mock=True)
    assert generate_email_drafts(limit=1, mock=True, lead_ids=own.lead_ids) == 1
    assert generate_email_drafts(limit=1, mock=True, lead_ids=own.lead_ids) == 0
    assert generate_email_drafts(limit=1, mock=True, lead_ids=[]) == 0
    with get_session() as conn:
        drafts = conn.execute("SELECT * FROM emails").fetchall()
        assert len(drafts) == 1
        assert drafts[0]["lead_id"] == own.lead_ids[0]
        assert drafts[0]["sendability"] == "do_not_send"
        assert drafts[0]["sent_at"] is None
        assert conn.execute("SELECT status FROM leads WHERE id=?", other.lead_ids).fetchone()["status"] == "qualified"
        assert not conn.execute("SELECT 1 FROM leads WHERE status='emailed'").fetchone()


def test_research_cache_keeps_all_results_and_distinct_long_queries(tmp_path, monkeypatch):
    from agents.research.research_agent import ResearchAgent

    _use_temp_db(tmp_path, monkeypatch)
    agent = ResearchAgent()
    results = [{"url": f"https://example.invalid/{i}", "title": str(i)} for i in range(10)]
    calls = []
    def search(query):
        calls.append(query)
        return results
    monkeypatch.setattr(agent, "_brave_search", search)
    query = "a" * 110
    assert agent.execute(query=query).data == results
    assert agent.execute(query=query).data == results
    agent.execute(query=query + "b")
    assert calls == [query, query + "b"]
